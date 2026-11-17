"""Atomic state persistence, steering application & brownfield indexing helpers."""

import json
import os
from pathlib import Path
import time

from structuredai.ast_reality import extract_symbols, format_reality_md, legacy_outline
from structuredai.config import Config
from structuredai.steering import SteeringDirectives, consume_directives


def atomic_write_json(path: Path, data: dict) -> None:
    """Persist state.json atomically via temp file + fsync + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)
        fp.flush()
        os.fsync(fp.fileno())
    os.replace(tmp, path)


def load_or_init_state(cfg: Config, state_path: Path, mode: str, stack_name: str) -> dict:
    """Load resumable state.json or initialize a fresh schema v3 state."""
    if cfg.resume_mode != "fresh" and state_path.is_file():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {
        "schema_version": 3, "run_id": f"run_{int(time.time())}",
        "mode": mode, "stack": stack_name,
        "time_budget": {"elapsed_active_seconds": 0.0, "last_green_tag": None},
        "nodes": {},
    }


def apply_steering(nodes: dict, d: SteeringDirectives, steering_path: Path) -> None:
    """Apply live human PRIORITY / RETRY / SKIP commands from STEERING.md."""
    done: list[str] = []
    for p in d.priorities:
        if p in nodes:
            nodes[p]["priority_boost"] = 50
            done.append(f"PRIORITY: {p}")
    for p in d.retries:
        if p in nodes:
            nodes[p].update({"state": "1_DRAFT", "retries": 0, "last_error": ""})
            done.append(f"RETRY: {p}")
    for p in d.skips:
        if p in nodes:
            nodes[p]["state"] = "SKIPPED"
            done.append(f"SKIP: {p}")
    consume_directives(steering_path, done)


def index_brownfield(cfg: Config, meta_dir: Path, code_exts: list[str], exports: dict[str, set[str]]) -> None:
    """Scan existing files deterministically without LLM to seed REALITY.md & legacy outlines."""
    for p in cfg.target_dir.rglob("*"):
        if not p.is_file() or p.suffix not in code_exts:
            continue
        rel = str(p.relative_to(cfg.target_dir))
        if rel.startswith((cfg.state_dir_name, ".git", ".venv", "node_modules", "target")):
            continue
        if p.stat().st_size > cfg.max_ingest_bytes:
            continue
        txt = p.read_text(encoding="utf-8", errors="ignore")
        syms = extract_symbols(txt, p.suffix)
        exports[rel] = set(syms.get("exports", []))
        rpath = meta_dir / rel / "REALITY.md"
        if not rpath.exists():
            rpath.parent.mkdir(parents=True, exist_ok=True)
            extra = legacy_outline(p, cfg.max_ingest_bytes) if len(txt.splitlines()) > cfg.max_lines_per_file else "Existing module"
            rpath.write_text(format_reality_md(rel, len(txt.splitlines()), syms, extra), encoding="utf-8")
