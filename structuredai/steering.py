"""Live human steering integration via .orchestrator/STEERING.md (editable in Zed)."""

from dataclasses import dataclass, field
from pathlib import Path
import re

STEERING_TEMPLATE = """# StructuredAI — Pilotage en Direct (Éditable dans Zed)
# Modifiez ce fichier à tout moment : l'agent le lit au début de chaque cycle.
# Valeurs de STATUS : RUN | PAUSE | STOP

STATUS: RUN

# Directives ponctuelles (décommentez ou utilisez les tâches Zed) :
# PRIORITY: src/exemple.py
# RETRY: src/exemple.py
# SKIP: src/exemple.py
# NOTE [src/exemple.py]: Précision technique pour le prochain essai.
"""


@dataclass
class SteeringDirectives:
    status: str = "RUN"
    priorities: list[str] = field(default_factory=list)
    retries: list[str] = field(default_factory=list)
    skips: list[str] = field(default_factory=list)
    notes: dict[str, list[str]] = field(default_factory=dict)


def ensure_steering_file(path: Path) -> None:
    """Create STEERING.md template if not yet present."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(STEERING_TEMPLATE, encoding="utf-8")


def read_steering(path: Path) -> SteeringDirectives:
    """Parse active human directives from STEERING.md."""
    ensure_steering_file(path)
    d = SteeringDirectives()
    for raw in path.read_text(encoding="utf-8").splitlines():
        ln = raw.strip()
        if not ln or ln.startswith("#"):
            continue
        if ln.upper().startswith("STATUS:"):
            val = ln.split(":", 1)[1].strip().upper()
            if val in {"RUN", "PAUSE", "STOP"}:
                d.status = val
        elif ln.upper().startswith("PRIORITY:"):
            d.priorities.append(ln.split(":", 1)[1].strip())
        elif ln.upper().startswith("RETRY:"):
            d.retries.append(ln.split(":", 1)[1].strip())
        elif ln.upper().startswith("SKIP:"):
            d.skips.append(ln.split(":", 1)[1].strip())
        elif m := re.match(r"^NOTE\s*\[([^\]]+)\]\s*:\s*(.+)$", ln, re.IGNORECASE):
            d.notes.setdefault(m.group(1).strip(), []).append(m.group(2).strip())
    return d


def set_steering_status(path: Path, new_status: str) -> None:
    """Update STATUS line cleanly (used by ./start.sh pause|resume|stop)."""
    ensure_steering_file(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    out, done = [], False
    for ln in lines:
        if ln.strip().upper().startswith("STATUS:") and not done:
            out.append(f"STATUS: {new_status.upper()}")
            done = True
        else:
            out.append(ln)
    if not done:
        out.insert(0, f"STATUS: {new_status.upper()}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def append_steering_directive(path: Path, key: str, target_rel: str) -> None:
    """Append a PRIORITY or RETRY directive (used by Zed tasks with $ZED_FILE)."""
    ensure_steering_file(path)
    line = f"{key.upper()}: {target_rel}"
    txt = path.read_text(encoding="utf-8")
    if line not in txt.splitlines():
        path.write_text(txt.rstrip() + f"\n{line}\n", encoding="utf-8")


def consume_directives(path: Path, processed_lines: list[str]) -> None:
    """Comment out one-shot PRIORITY/RETRY/NOTE lines once ingested."""
    if not processed_lines or not path.exists():
        return
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip() in processed_lines:
            out.append(f"# [APPLIED] {ln.strip()}")
        else:
            out.append(ln)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
