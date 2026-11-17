"""Main state machine loop coordinating multi-day execution, steering & safe freeze."""

import time

from structuredai.config import Config
from structuredai.git_tx import GitTx
from structuredai.graph_ops import next_actionable_node
from structuredai.llm_client import LLMClient
from structuredai.node_runner import NodeRunner
from structuredai.security_gate import PathJail
from structuredai.stack_adapter import StackAdapter, build_deps_reality
from structuredai.stack_detector import detect_project_mode, detect_stack
from structuredai.state_store import (
    apply_steering,
    atomic_write_json,
    index_brownfield,
    init_architect_with_retries,
    load_or_init_state,
)
from structuredai.steering import ensure_steering_file, read_steering
from structuredai.sys_probes import free_disk_mb
from structuredai.telemetry import render_dashboard, write_run_report
from structuredai.time_budget import TimeBudgetManager
from structuredai.watchdog import Watchdog


class OrchestratorEngine:
    """Executes the persistent multi-day loop with crash safety and safe H4 freeze."""

    def __init__(self, cfg: Config, watchdog: Watchdog) -> None:
        self.cfg, self.wd = cfg, watchdog
        self.sdir = cfg.target_dir / cfg.state_dir_name
        self.state_path = self.sdir / "state.json"
        self.meta_dir = (self.sdir / "tree") if cfg.metadata_storage == "shadow" else cfg.target_dir
        self.git = GitTx(cfg.target_dir, cfg.git_work_branch, cfg.git_auto_commit, cfg.max_green_tags_keep)
        self.llm, self.runner = LLMClient(cfg), NodeRunner(self)
        self.stop_flag, self.cycles, self.tps_avg = False, 0, 0.0

    def bootstrap(self) -> tuple[dict, TimeBudgetManager, dict]:
        """Initialize workspace, steering, stack adapter, brownfield reality & state."""
        self.cfg.target_dir.mkdir(parents=True, exist_ok=True)
        self.sdir.mkdir(parents=True, exist_ok=True)
        ensure_steering_file(self.sdir / "STEERING.md")
        self.git.ensure_ready(self.cfg.state_dir_name)
        spec_txt = self.cfg.spec_path.read_text(encoding="utf-8") if self.cfg.spec_path.is_file() else "REQ-01: Build core module."
        mode = detect_project_mode(self.cfg.target_dir, self.cfg.project_mode)
        stack = detect_stack(self.cfg.target_dir, spec_txt, self.cfg)
        deps_md, pkgs = build_deps_reality(self.cfg.target_dir, stack["name"])
        (self.sdir / "DEPS_REALITY.md").write_text(deps_md, encoding="utf-8")
        state = load_or_init_state(self.cfg, self.state_path, mode, stack["name"])
        tbm = TimeBudgetManager(self.cfg.run_duration_sec, self.cfg.time_profile, self.cfg.time_accounting_mode, self.cfg.freeze_ratio, self.cfg.node_cap_ratio, self.cfg.heartbeat_sec, float(state["time_budget"].get("elapsed_active_seconds", 0.0)))
        exports: dict[str, set[str]] = {}
        if mode == "brownfield":
            index_brownfield(self.cfg, self.meta_dir, stack.get("code_exts", [".py"]), exports)
        ctx = {"cfg": self.cfg, "llm": self.llm, "jail": PathJail(self.cfg.target_dir, self.cfg.state_dir_name), "git": self.git, "adapter": StackAdapter(self.cfg.target_dir, stack, self.cfg), "stack": stack, "meta_dir": self.meta_dir, "nodes": state["nodes"], "deps_md": deps_md, "installed_pkgs": pkgs, "exports": exports, "spec_text": spec_txt}
        return state, tbm, ctx

    def run(self) -> None:
        """Main bounded loop with live STEERING.md checks and watchdog monitoring."""
        state, tbm, ctx = self.bootstrap()
        self.wd.ensure_llm_ready()
        if not state["nodes"]:
            init_architect_with_retries(ctx, state, self.state_path)
        reason = "TIME_BUDGET_COMPLETE"
        while not self.stop_flag:
            elapsed = tbm.tick(paused=False)
            state["time_budget"]["elapsed_active_seconds"] = elapsed
            rss, _, low_disk = self.wd.check_health(self.llm.consecutive_anomalies >= 3)
            if low_disk:
                reason = "LOW_DISK_GUARD"; break
            st_dir = read_steering(self.sdir / "STEERING.md")
            if st_dir.status == "STOP":
                reason = "HUMAN_STEERING_STOP"; break
            if st_dir.status == "PAUSE":
                tbm.tick(paused=True); time.sleep(2); continue
            apply_steering(state["nodes"], st_dir, self.sdir / "STEERING.md")
            if tbm.is_frozen():
                reason = "FREEZE_WINDOW_REACHED"; break
            rel = next_actionable_node(state["nodes"])
            if not rel:
                reason = "ALL_NODES_RESOLVED"; break
            self.runner.step(state, tbm, ctx, rel, st_dir.notes.get(rel, []))
            self.cycles += 1
            atomic_write_json(self.state_path, state)
            if self.cycles % self.cfg.dashboard_refresh_cycles == 0:
                render_dashboard(self.sdir / "DASHBOARD.md", state, self.cfg, tbm.current_horizon(), elapsed, rss, free_disk_mb(self.cfg.target_dir), self.wd.restarts, self.llm.avg_tps)
            time.sleep(self.cfg.cooldown_ms / 1000.0)
        self._finalize(state, tbm, ctx, reason)

    def _finalize(self, state: dict, tbm: TimeBudgetManager, ctx: dict, reason: str) -> None:
        last_tag = state["time_budget"].get("last_green_tag")
        if last_tag and not ctx["adapter"].test_suite()[0]:
            self.git.reset_to_tag(last_tag)
        write_run_report(self.sdir / "RUN_REPORT.md", state, self.cfg, tbm.tick(), reason)
        render_dashboard(self.sdir / "DASHBOARD.md", state, self.cfg, "H4_FROZEN", tbm.tick(), 0.0, free_disk_mb(self.cfg.target_dir), self.wd.restarts, self.llm.avg_tps)
        atomic_write_json(self.state_path, state)
