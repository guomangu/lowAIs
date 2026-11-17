"""Universal stack and project-mode detection (Greenfield vs Brownfield)."""

import tomllib
from pathlib import Path

from structuredai.config import Config

BUILTIN_STACKS: dict[str, dict] = {
    "python": {
        "name": "python", "code_exts": [".py"], "test_pattern": "tests/test_{stem}.py",
        "syntax_check": "python3 -m py_compile {file}", "lint": "ruff check {file}",
        "test_targeted": "pytest -q --tb=short {test_file}", "test_suite": "pytest -q",
        "build_check": "python3 -m compileall -q {project_dir}", "extractor": "python_ast",
    },
    "node_ts": {
        "name": "node_ts", "code_exts": [".ts", ".tsx"], "test_pattern": "tests/{stem}.test.ts",
        "syntax_check": "npx --no-install tsc --noEmit", "lint": "npx --no-install eslint {file}",
        "test_targeted": "npx --no-install vitest run {test_file}", "test_suite": "npx --no-install vitest run",
        "build_check": "npm run build", "extractor": "regex",
    },
    "rust": {
        "name": "rust", "code_exts": [".rs"], "test_pattern": "tests/{stem}_test.rs",
        "syntax_check": "cargo check --message-format=short", "lint": "cargo clippy -- -D warnings",
        "test_targeted": "cargo test {stem}", "test_suite": "cargo test",
        "build_check": "cargo build", "extractor": "regex",
    },
    "go": {
        "name": "go", "code_exts": [".go"], "test_pattern": "{dir}/{stem}_test.go",
        "syntax_check": "go vet ./...", "lint": "golangci-lint run ./...",
        "test_targeted": "go test -v ./{dir}", "test_suite": "go test ./...",
        "build_check": "go build ./...", "extractor": "regex",
    },
}


def detect_project_mode(project_dir: Path, mode_cfg: str) -> str:
    """Return 'greenfield' if project_dir has no source files yet, else 'brownfield'."""
    if mode_cfg in {"greenfield", "brownfield"}:
        return mode_cfg
    if not project_dir.exists():
        return "greenfield"
    ignored = {".git", ".orchestrator", ".zed", "SPEC.md", "README.md", ".env", ".gitignore"}
    for entry in project_dir.iterdir():
        if entry.name not in ignored:
            return "brownfield"
    return "greenfield"


def detect_stack(project_dir: Path, spec_text: str, cfg: Config) -> dict:
    """Resolve stack profile from stack.toml, .env TARGET_STACK, files, or SPEC keywords."""
    if cfg.stack_profile_path and Path(cfg.stack_profile_path).is_file():
        raw = tomllib.loads(Path(cfg.stack_profile_path).read_text(encoding="utf-8"))
        prof = {**raw.get("stack", {}), **raw.get("commands", {}), **raw.get("symbols", {})}
        prof.setdefault("name", "custom")
        prof.setdefault("code_exts", prof.pop("code_extensions", [".py"]))
        return _apply_overrides(prof, cfg)
    name = cfg.target_stack
    if name == "auto":
        name = _sniff_dir(project_dir) or _sniff_spec(spec_text) or "python"
    base = dict(BUILTIN_STACKS.get(name, BUILTIN_STACKS["python"]))
    return _apply_overrides(base, cfg)


def _sniff_dir(d: Path) -> str | None:
    if not d.exists():
        return None
    checks = [
        (("pyproject.toml", "requirements.txt", "setup.py"), "python"),
        (("tsconfig.json",), "node_ts"), (("Cargo.toml",), "rust"), (("go.mod",), "go"),
    ]
    for files, stack in checks:
        if any((d / f).exists() for f in files):
            return stack
    if list(d.glob("**/*.py")):
        return "python"
    return None


def _sniff_spec(spec_text: str) -> str | None:
    low = spec_text.lower()
    for kw, st in [("rust", "rust"), ("cargo", "rust"), ("typescript", "node_ts"), ("golang", "go"), ("go 1.", "go")]:
        if kw in low:
            return st
    return None


def _apply_overrides(prof: dict, cfg: Config) -> dict:
    import shutil
    if prof.get("name") == "python" and shutil.which("pytest") is None:
        prof["test_targeted"] = "python3 -m unittest {test_file}"
        prof["test_suite"] = "python3 -m unittest discover -s tests"
    for key, val in cfg.custom_cmds.items():
        if val:
            prof[key] = val
    return prof
