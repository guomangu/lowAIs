"""Deterministic stack hook execution with killpg timeouts, sandbox & DEPS_REALITY."""

import os
import shlex
import shutil
import signal
import subprocess
import tempfile
from importlib import metadata
from pathlib import Path

from structuredai.config import Config
from structuredai.security_gate import sanitized_env


class StackAdapter:
    """Runs syntax, lint, test & build hooks safely inside isolated subprocesses."""

    def __init__(self, project_dir: Path, stack: dict, cfg: Config) -> None:
        self.project_dir = project_dir
        self.stack = stack
        self.cfg = cfg

    def run_cmd(self, cmd_tpl: str, ctx: dict[str, str], check_tool: bool = True) -> tuple[bool, str]:
        """Run formatted command with setsid/killpg timeout and sanitized env."""
        if not cmd_tpl.strip():
            return True, ""
        cmd_str = cmd_tpl.format(**ctx)
        parts = shlex.split(cmd_str)
        if check_tool and parts and shutil.which(parts[0]) is None:
            return True, f"[SKIP] tool '{parts[0]}' not installed"
        with tempfile.TemporaryDirectory(prefix="sai_sbx_") as sbx:
            env = sanitized_env(dict(os.environ), Path(sbx))
            if not self.cfg.allow_network_tests:
                env["HTTP_PROXY"] = env["HTTPS_PROXY"] = "http://127.0.0.1:0"
            try:
                proc = subprocess.Popen(
                    parts, cwd=self.project_dir, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True,
                )
            except FileNotFoundError:
                return False, f"Command not found: {parts[0]}"
            try:
                out, _ = proc.communicate(timeout=self.cfg.subprocess_timeout_sec)
                return proc.returncode == 0, out or ""
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                proc.wait()
                return False, f"TIMEOUT after {self.cfg.subprocess_timeout_sec}s: {cmd_str}"

    def _ctx(self, rel_file: str = "", test_file: str = "") -> dict[str, str]:
        p = Path(rel_file) if rel_file else Path(".")
        return {
            "file": rel_file, "dir": str(p.parent), "stem": p.stem,
            "test_file": test_file, "project_dir": str(self.project_dir),
        }

    def check_syntax(self, rel_file: str) -> tuple[bool, str]:
        return self.run_cmd(self.stack.get("syntax_check", ""), self._ctx(rel_file))

    def lint(self, rel_file: str) -> tuple[bool, str]:
        return self.run_cmd(self.stack.get("lint", ""), self._ctx(rel_file))

    def test_targeted(self, rel_file: str, test_file: str) -> tuple[bool, str]:
        return self.run_cmd(self.stack.get("test_targeted", ""), self._ctx(rel_file, test_file), check_tool=False)

    def test_suite(self) -> tuple[bool, str]:
        return self.run_cmd(self.stack.get("test_suite", ""), self._ctx(), check_tool=False)

    def build_check(self) -> tuple[bool, str]:
        return self.run_cmd(self.stack.get("build_check", ""), self._ctx())


def build_deps_reality(project_dir: Path, stack_name: str) -> tuple[str, set[str]]:
    """Build deterministic DEPS_REALITY.md and return known installed package roots."""
    pkgs: set[str] = set()
    lines = ["# DEPS_REALITY (Packages détectés déterministement)"]
    if stack_name == "python":
        for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower())[:25]:
            name = dist.metadata["Name"]
            pkgs.add(name.lower().replace("-", "_"))
            lines.append(f"- `{name}=={dist.version}`")
    for manifest in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod"):
        mp = project_dir / manifest
        if mp.is_file():
            lines.append(f"- Manifest détecté : `{manifest}`")
    return "\n".join(lines[:30]) + "\n", pkgs
