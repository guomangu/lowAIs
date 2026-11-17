"""Surgical error distillation (<=180 tok), stagnation ping-pong & degeneration guards."""

import hashlib
import re

_LINE_RE = re.compile(r"(?:line\s+|:)(\d+)", re.IGNORECASE)
_NOISE_RE = re.compile(r"(site-packages|node_modules|/usr/lib/)")


def distill_error(raw_error: str, code: str = "", max_chars: int = 560) -> str:
    """Strip stack noise and keep root error + +/-3 lines around failing line."""
    kept = [ln for ln in raw_error.splitlines() if ln.strip() and not _NOISE_RE.search(ln)]
    tail = "\n".join(kept[-8:]) if kept else raw_error[-300:]
    m = _LINE_RE.search(tail)
    snippet = ""
    if m and code:
        ln_no = max(1, int(m.group(1)))
        lines = code.splitlines()
        lo, hi = max(0, ln_no - 4), min(len(lines), ln_no + 3)
        snippet = "\n".join(f"{i+1}: {lines[i]}" for i in range(lo, hi))
    out = f"{tail}\n--- CONTEXT ---\n{snippet}" if snippet else tail
    return out[:max_chars]


def content_hash(text: str) -> str:
    """Normalized SHA-256 hash ignoring trailing spaces."""
    norm = "\n".join(ln.rstrip() for ln in text.strip().splitlines())
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def check_degeneration(prev_code: str, new_code: str, did_split: bool = False) -> str | None:
    """Block reward-hacking reductions (>50% LOC drop without split or trivial body)."""
    if did_split or not prev_code.strip():
        return None
    prev_n = sum(1 for ln in prev_code.splitlines() if ln.strip() and not ln.strip().startswith("#"))
    new_n = sum(1 for ln in new_code.splitlines() if ln.strip() and not ln.strip().startswith("#"))
    if prev_n >= 12 and new_n < max(4, int(prev_n * 0.5)):
        return f"Code degeneration blocked: non-empty lines dropped {prev_n} -> {new_n} without split"
    return None


class StagnationTracker:
    """Tracks K=5 recent code/error hashes per node and returns escalation strategy."""

    def __init__(self, k: int = 5) -> None:
        self.k = k

    def record_and_advise(self, node: dict, code: str, distilled_err: str) -> tuple[bool, float | None, str]:
        """Return (should_break_early, temp_override, hint) based on history_hashes."""
        ch = content_hash(code)
        eh = content_hash(distilled_err)
        hist: list[str] = list(node.get("history_hashes", []))
        err_hist: list[str] = list(node.get("error_hashes", []))
        repeated_code = ch in hist
        repeated_err = eh in err_hist
        hist = (hist + [ch])[-self.k :]
        err_hist = (err_hist + [eh])[-self.k :]
        node["history_hashes"] = hist
        node["error_hashes"] = err_hist
        if hist.count(ch) >= 3:
            return True, None, "Identical output repeated 3 times: tripping circuit breaker."
        if repeated_code:
            return False, 0.45, "STAGNATION DETECTED: previous code repeated; change implementation approach."
        if repeated_err:
            return False, 0.35, "SAME ERROR REPEATED: verify dependencies/signatures and simplify logic."
        return False, None, ""
