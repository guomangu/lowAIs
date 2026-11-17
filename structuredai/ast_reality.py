"""Deterministic AST/regex signature extraction, hashing & REALITY.md formatting."""

import ast
import hashlib
from pathlib import Path
import re

_GENERIC_EXPORT_RE = re.compile(
    r"^\s*(?:export\s+(?:async\s+)?(?:function|class|const|interface|type)|pub\s+(?:async\s+)?(?:fn|struct|enum|trait)|func)\s+([A-Za-z0-9_]+)",
    re.MULTILINE,
)
_GENERIC_IMPORT_RE = re.compile(r"^\s*(?:import|from|use|require)\s+([^\n;]+)", re.MULTILINE)


def extract_symbols(code: str, ext: str) -> dict[str, list[str]]:
    """Extract exact imports, exported symbols and signatures deterministically."""
    if ext == ".py":
        return _extract_python(code)
    exports = sorted(set(_GENERIC_EXPORT_RE.findall(code)))
    imports = sorted(set(m.strip() for m in _GENERIC_IMPORT_RE.findall(code)))
    return {"imports": imports[:15], "signatures": exports[:20], "exports": exports}


def _extract_python(code: str) -> dict[str, list[str]]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"imports": [], "signatures": [], "exports": []}
    imports: list[str] = []
    sigs: list[str] = []
    exports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            imports.extend(f"{mod}.{a.name}" if mod else a.name for a in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = [a.arg for a in node.args.args]
            ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
            sigs.append(f"def {node.name}({', '.join(args)}){ret}")
            if not node.name.startswith("_"):
                exports.append(node.name)
        elif isinstance(node, ast.ClassDef):
            sigs.append(f"class {node.name}")
            if not node.name.startswith("_"):
                exports.append(node.name)
    return {"imports": sorted(set(imports)), "signatures": sigs, "exports": sorted(set(exports))}


def ast_sig_hash(symbols: dict[str, list[str]]) -> str:
    """Compute stable SHA-256 over public exports & signatures (for Ripple detection)."""
    payload = "|".join(sorted(symbols.get("signatures", []))) + "||" + "|".join(sorted(symbols.get("exports", [])))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def format_reality_md(rel_path: str, line_count: int, symbols: dict[str, list[str]], purpose: str) -> str:
    """Format compact <=15 line REALITY.md combining AST truth + short LLM summary."""
    imps = ", ".join(symbols.get("imports", [])[:8]) or "aucun"
    sigs = symbols.get("signatures", [])[:8]
    lines = [
        f"# REALITY: {rel_path} ({line_count} lignes)",
        f"- imports: `{imps}`",
        *[f"- `{s}`" for s in sigs],
        f"- role: {purpose.strip()[:220]}",
    ]
    return "\n".join(lines[:15]) + "\n"


def legacy_outline(path: Path, max_bytes: int = 262144) -> str:
    """Generate compact AST line-range index for >100-line brownfield monoliths."""
    if not path.is_file() or path.stat().st_size > max_bytes:
        return "[LEGACY_SKIPPED: binary or > MAX_INGEST_FILE_BYTES]"
    text = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix != ".py":
        return "\n".join(f"L{i+1}: {ln[:80]}" for i, ln in enumerate(text.splitlines()[:40]))
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return "[SYNTAX_ERROR in legacy file]"
    rows = [f"{getattr(n, 'name', '?')}: L{n.lineno}-L{getattr(n, 'end_lineno', n.lineno)}" for n in tree.body if hasattr(n, "lineno")]
    return "\n".join(rows[:35])
