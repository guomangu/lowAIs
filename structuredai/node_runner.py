"""Single-node step dispatcher, integration tagger & circuit-breaker failure handler."""

import time

from structuredai.error_distiller import StagnationTracker, distill_error
from structuredai.pass_critique import run_critique, run_rebalance
from structuredai.passes import run_draft, run_extract, run_synthesis
from structuredai.telemetry import append_error_md, append_event
from structuredai.time_budget import TimeBudgetManager


class NodeRunner:
    """Executes one state transition for a selected node and handles failures."""

    def __init__(self, eng) -> None:
        self.eng = eng
        self.stag = StagnationTracker()
        self.locked_since_int = 0
        self.green_steps = 0

    def step(self, state: dict, tbm: TimeBudgetManager, ctx: dict, rel: str, notes: list[str]) -> None:
        """Advance node by one state and record event/duration."""
        node, t0 = state["nodes"][rel], time.monotonic()
        prev_st, hint = node["state"], " | ".join(notes)
        try:
            if prev_st == "NEEDS_REVERIFY":
                ok, out = ctx["adapter"].test_targeted(rel, node.get("test_path", ""))
                node["state"] = "6_LOCKED" if ok else "4_REBALANCE"
                if not ok:
                    node["last_error"] = distill_error(out)
            elif prev_st in {"0_ARCHITECT", "1_DRAFT"}:
                node["state"] = run_draft(ctx, rel, node, node.pop("temp_override", None), hint)
            elif prev_st == "2_EXTRACT":
                node["state"] = run_extract(ctx, rel, node)
            elif prev_st == "3_CRITIQUE":
                node["state"] = run_critique(ctx, rel, node)
            elif prev_st == "4_REBALANCE":
                node["state"] = run_rebalance(ctx, rel, node, node.pop("temp_override", None))
            elif prev_st == "5_SYNTHESIS":
                node["state"] = run_synthesis(ctx, rel, node, node.pop("temp_override", None), hint)
        except (RuntimeError, ValueError, TypeError, KeyError, OSError, PermissionError) as exc:
            self._handle_failure(tbm, node, rel, prev_st, str(exc))
        else:
            if node["state"] != prev_st and prev_st != "4_REBALANCE":
                node["retries"] = 0
                node["last_error"] = ""
        if node["state"] == "6_LOCKED" and prev_st == "5_SYNTHESIS":
            self._maybe_integration_tag(state, ctx, node["state"])
        node["time_spent_seconds"] = float(node.get("time_spent_seconds", 0.0)) + (time.monotonic() - t0)
        append_event(self.eng.sdir / "events.jsonl", {"node": rel, "from": prev_st, "to": node["state"], "horizon": tbm.current_horizon()}, self.eng.cfg.max_events_log_mb)

    def _maybe_integration_tag(self, state: dict, ctx: dict, new_st: str) -> None:
        if new_st != "6_LOCKED":
            return
        self.locked_since_int += 1
        if self.locked_since_int >= self.eng.cfg.integration_interval:
            if ctx["adapter"].test_suite()[0] and ctx["adapter"].build_check()[0]:
                self.green_steps += 1
                state["time_budget"]["last_green_tag"] = self.eng.git.tag_green_step(self.green_steps)
            self.locked_since_int = 0

    def _handle_failure(self, tbm: TimeBudgetManager, node: dict, rel: str, prev_st: str, msg: str) -> None:
        cfg = self.eng.cfg
        node["retries"] = int(node.get("retries", 0)) + 1
        node["last_error"] = msg[:500]
        code_txt = (cfg.target_dir / rel).read_text(encoding="utf-8", errors="ignore") if (cfg.target_dir / rel).is_file() else ""
        brk, tmp, shint = self.stag.record_and_advise(node, code_txt, msg) if cfg.enable_stagnation else (False, None, "")
        if tmp:
            node["temp_override"] = tmp
        if shint:
            node["last_error"] = f"{shint}\n{node['last_error']}"
        if brk or node["retries"] >= cfg.max_retries or tbm.node_exceeded_cap(node.get("time_spent_seconds", 0.0)):
            node["state"] = "FAILED_MANUAL_REVIEW"
            self.eng.git.rollback_paths([rel, node.get("test_path", "")])
            append_error_md(self.eng.sdir / "ERRORS.md", rel, prev_st, msg, self.eng.git.head_sha())
