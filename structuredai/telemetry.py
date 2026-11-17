"""Telemetry writers: rotating events.jsonl, live DASHBOARD.md, ERRORS.md & RUN_REPORT.md."""

import gzip
import json
import os
from pathlib import Path
import shutil
import time

from structuredai.config import Config


def append_event(events_path: Path, event: dict, max_mb: int = 50) -> None:
    """Append WAL JSONL event and gzip-rotate if file exceeds max_mb."""
    events_path.parent.mkdir(parents=True, exist_ok=True)
    if events_path.exists() and events_path.stat().st_size >= max_mb * 1024 * 1024:
        gz_path = events_path.with_name(f"events.{int(time.time())}.jsonl.gz")
        with events_path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
            shutil.copyfileobj(src, dst)
        events_path.write_text("", encoding="utf-8")
    payload = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **event}
    with events_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        fp.write(content)
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(tmp, path)


def render_dashboard(
    dash_path: Path, state: dict, cfg: Config, horizon: str, elapsed_s: float, rss_mb: float, free_mb: float, restarts: int, tps: float
) -> None:
    """Update .orchestrator/DASHBOARD.md for live Zed Markdown Preview."""
    nodes = state.get("nodes", {})
    counts: dict[str, int] = {}
    for info in nodes.values():
        st = info.get("state", "UNKNOWN")
        counts[st] = counts.get(st, 0) + 1
    tb = state.get("time_budget", {})
    pct = min(100.0, 100.0 * elapsed_s / max(1, cfg.run_duration_sec))
    tot_h, tot_m = int(cfg.run_duration_sec // 3600), int((cfg.run_duration_sec % 3600) // 60)
    lines = [
        f"# StructuredAI — Live Dashboard (`{state.get('run_id', '')}`)",
        "",
        f"- **Horizon Actif** : `{horizon}` | **Temps Actif** : `{int(elapsed_s//3600)}h {int((elapsed_s%3600)//60):02d}m / {tot_h}h {tot_m:02d}m` ({pct:.1f}%)",
        f"- **Modèle IA** : `{cfg.llm_model}` (`{cfg.llm_provider}`) | **Débit moyen** : `{tps:.1f} tok/s`",
        f"- **Ressources** : `{rss_mb:.0f} Mo / {cfg.ram_limit_mb} Mo` RAM | Disque libre : `{free_mb/1024:.1f} Go` | Restarts : `{restarts}`",
        f"- **Nœuds** : `6_LOCKED={counts.get('6_LOCKED', 0)}` | `NEEDS_REVERIFY={counts.get('NEEDS_REVERIFY', 0)}` | `FAILED={counts.get('FAILED_MANUAL_REVIEW', 0)}` | `TOTAL={len(nodes)}`",
        f"- **Dernier Tag Vert** : `{tb.get('last_green_tag', 'aucun')}` | **Stack** : `{state.get('stack', cfg.target_stack)}`",
        "",
        "## État des Modules",
        *[f"- `{k}` : **{v.get('state')}** (essais: {v.get('retries', 0)})" for k, v in sorted(nodes.items())[:30]],
    ]
    _atomic_write_text(dash_path, "\n".join(lines) + "\n")


def append_error_md(err_path: Path, node_name: str, last_state: str, reason: str, git_sha: str) -> None:
    """Log circuit-broken node details to .orchestrator/ERRORS.md."""
    err_path.parent.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    block = (
        f"\n## [FAILED_MANUAL_REVIEW] {node_name}\n"
        f"- **Horodatage** : {ts} | **État** : `{last_state}` | **Git** : `{git_sha}`\n"
        f"- **Cause distillée** : `{reason[:300]}`\n"
    )
    with err_path.open("a", encoding="utf-8") as fp:
        fp.write(block)


def write_run_report(report_path: Path, state: dict, cfg: Config, elapsed_s: float, reason: str) -> None:
    """Write final RUN_REPORT.md upon entering FROZEN."""
    nodes = state.get("nodes", {})
    locked = [k for k, v in nodes.items() if v.get("state") == "6_LOCKED"]
    failed = [k for k, v in nodes.items() if v.get("state") == "FAILED_MANUAL_REVIEW"]
    lines = [
        f"# StructuredAI — Rapport Final (`{state.get('run_id', '')}`)",
        "",
        f"- **Motif de clôture** : `{reason}` | **Durée active** : `{elapsed_s:.0f}s`",
        f"- **Dernier Tag Vert** : `{state.get('time_budget', {}).get('last_green_tag', 'aucun')}`",
        f"- **Modules Verrouillés (`6_LOCKED`)** : {len(locked)} / {len(nodes)}",
        f"- **Modules en Revue Manuelle** : {len(failed)}",
        "",
        "## Commandes d'inspection",
        f"- `git -C {cfg.target_dir} diff main..{cfg.git_work_branch}`",
    ]
    _atomic_write_text(report_path, "\n".join(lines) + "\n")
