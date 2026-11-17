"""Transactional Git isolation: branch ai-auto, selective staging & green tags."""

from pathlib import Path
import subprocess

_SECRET_PATTERNS = (".env", ".pem", ".key", "id_rsa", ".orchestrator")


class GitTx:
    """Manages atomic commits, rollbacks, and High-Watermark green tags safely."""

    def __init__(self, project_dir: Path, work_branch: str = "ai-auto", auto_commit: bool = True, max_tags: int = 20) -> None:
        self.dir = project_dir
        self.work_branch = work_branch
        self.auto_commit = auto_commit
        self.max_tags = max_tags

    def _git(self, *args: str) -> tuple[bool, str]:
        res = subprocess.run(["git", *args], cwd=self.dir, capture_output=True, text=True, check=False)
        return res.returncode == 0, (res.stdout + res.stderr).strip()

    def ensure_ready(self, state_dir_name: str = ".orchestrator") -> None:
        """Initialize repo if missing, exclude orchestrator artifacts, switch to work branch."""
        if not (self.dir / ".git").exists():
            self._git("init", "-b", "main")
            self._git("config", "user.name", "StructuredAI")
            self._git("config", "user.email", "structuredai@localhost")
        excl = self.dir / ".git" / "info" / "exclude"
        excl.parent.mkdir(parents=True, exist_ok=True)
        cur = excl.read_text(encoding="utf-8") if excl.exists() else ""
        add_lines = [p for p in (f"{state_dir_name}/", ".env", ".env.*") if p not in cur]
        if add_lines:
            excl.write_text(cur + ("\n" if cur and not cur.endswith("\n") else "") + "\n".join(add_lines) + "\n", encoding="utf-8")
        ok, _ = self._git("rev-parse", "--verify", "HEAD")
        if not ok:
            self._git("commit", "--allow-empty", "-m", "chore(init): baseline")
        self._git("checkout", "-B", self.work_branch)

    def head_sha(self) -> str:
        ok, out = self._git("rev-parse", "--short", "HEAD")
        return out if ok else "none"

    def stage_and_commit(self, rel_paths: list[str], message: str) -> str | None:
        """Selectively stage non-secret node files and commit atomically."""
        if not self.auto_commit:
            return self.head_sha()
        safe = [p for p in rel_paths if p and not any(tok in p for tok in _SECRET_PATTERNS)]
        if not safe:
            return None
        self._git("add", "--", *safe)
        ok, _ = self._git("diff", "--cached", "--quiet")
        if ok:
            return self.head_sha()
        ok_c, _ = self._git("commit", "-m", message)
        return self.head_sha() if ok_c else None

    def rollback_paths(self, rel_paths: list[str]) -> None:
        """Restore tracked files and remove untracked failed files for a node."""
        for p in rel_paths:
            self._git("checkout", "HEAD", "--", p)
            self._git("clean", "-fd", "--", p)

    def tag_green_step(self, step_num: int) -> str:
        """Create sliding High-Watermark tag and prune older tags + git gc."""
        tag = f"green-step-{step_num:03d}"
        self._git("tag", "-f", tag)
        ok, out = self._git("tag", "--list", "green-step-*", "--sort=-creatordate")
        if ok:
            tags = [t.strip() for t in out.splitlines() if t.strip()]
            for old in tags[self.max_tags :]:
                self._git("tag", "-d", old)
        if step_num % 10 == 0:
            self._git("gc", "--auto")
        return tag

    def reset_to_tag(self, tag: str) -> bool:
        ok, _ = self._git("reset", "--hard", tag)
        return ok
