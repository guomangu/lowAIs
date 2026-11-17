"""Environment parsing helpers for StructuredAI."""

import os
import re
from pathlib import Path

_DUR_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(raw: str) -> int:
    """Parse duration string like '24h', '30m', '7d' into positive seconds."""
    m = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", raw.lower())
    if not m:
        raise ValueError(f"Invalid RUN_DURATION format: {raw!r}")
    secs = int(m.group(1)) * _DUR_UNITS[m.group(2) or "s"]
    if secs <= 0:
        raise ValueError("RUN_DURATION must be > 0")
    return secs


def load_dotenv(env_path: Path) -> dict[str, str]:
    """Read key=value pairs from .env and expand shell variables."""
    parsed: dict[str, str] = {}
    if not env_path.is_file():
        return parsed
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        val = os.path.expandvars(v.strip().strip('"').strip("'"))
        parsed[k.strip()] = val
    return parsed


def env_get(env: dict[str, str], key: str, default: str) -> str:
    return os.environ.get(key, env.get(key, default)).strip()


def env_bool(env: dict[str, str], key: str, default: bool) -> bool:
    return env_get(env, key, "true" if default else "false").lower() in {"1", "true", "yes", "on"}
