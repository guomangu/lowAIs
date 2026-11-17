"""Host confinement (PathJail), protected paths, env sanitization & dangerous call scanner."""

import re
from pathlib import Path

PROTECTED_BASENAMES = {".env", ".env.local", "SPEC.md", "stack.toml"}
_DANGEROUS_PATTERNS = [
    (re.compile(r"rm\s+-rf\s+[/~]"), "Destructive rm -rf on root or home"),
    (re.compile(r"shutil\.rmtree\s*\(\s*['\"](/|~)"), "Destructive rmtree outside project"),
    (re.compile(r"os\.environ\s*\["), "Direct mutation/read of host os.environ"),
    (re.compile(r"\b(18080)\b"), "Access/bind attempt on reserved LLM port 18080"),
    (re.compile(r"os\.system\s*\("), "Unsafe os.system invocation"),
]


class PathJail:
    """Restricts agent file writes inside target_dir and away from protected artifacts."""

    def __init__(self, target_dir: Path, state_dir_name: str = ".orchestrator") -> None:
        self.root = target_dir.resolve()
        self.state_dir = (self.root / state_dir_name).resolve()

    def resolve_safe(self, rel_or_abs: str | Path) -> Path:
        """Resolve path and verify it stays strictly inside target_dir without symlink escape."""
        p = Path(rel_or_abs)
        cand = p if p.is_absolute() else (self.root / p)
        for parent in [cand, *cand.parents]:
            if parent.exists() and parent.is_symlink() and not parent.resolve().is_relative_to(self.root):
                raise PermissionError(f"Symlink escape blocked: {rel_or_abs}")
            if parent == self.root:
                break
        resolved = cand.resolve()
        if not resolved.is_relative_to(self.root) or resolved == self.root:
            raise PermissionError(f"Path outside TARGET_PROJECT_DIR: {rel_or_abs}")
        return resolved

    def assert_writable_by_agent(self, rel_path: str) -> Path:
        """Verify path is safe AND not a protected spec/config/orchestrator file."""
        target = self.resolve_safe(rel_path)
        rel = target.relative_to(self.root)
        parts = set(rel.parts)
        if ".git" in parts or target.is_relative_to(self.state_dir):
            raise PermissionError(f"Protected orchestrator/git path: {rel_path}")
        if target.name in PROTECTED_BASENAMES or target.name.startswith(".env"):
            raise PermissionError(f"Protected configuration/spec file: {rel_path}")
        return target


def scan_dangerous_calls(code: str, reserved_port: int = 18080) -> list[str]:
    """Scan generated code/tests for destructive host patterns before execution."""
    issues: list[str] = []
    for rx, msg in _DANGEROUS_PATTERNS:
        if rx.search(code):
            issues.append(msg)
    if str(reserved_port) in code and ("bind" in code or "listen" in code or "port" in code.lower()) and not any("18080" in i for i in issues):
        issues.append(f"Potential collision with reserved LLM port {reserved_port}")
    return issues


def sanitized_env(base_env: dict[str, str], sandbox_dir: Path) -> dict[str, str]:
    """Strip secrets/API keys and isolate HOME/TMPDIR for generated test subprocesses."""
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    clean: dict[str, str] = {}
    for k, v in base_env.items():
        ku = k.upper()
        if any(s in ku for s in ("API_KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL")):
            continue
        clean[k] = v
    clean["HOME"] = str(sandbox_dir)
    clean["TMPDIR"] = str(sandbox_dir)
    clean["PYTHONDONTWRITEBYTECODE"] = "1"
    return clean
