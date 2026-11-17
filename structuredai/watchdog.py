"""Host watchdog managing llama-server lifecycle, RAM ceiling, disk & thermal pauses."""

import os
import shutil
import subprocess
import time
from urllib.parse import urlparse

from structuredai.config import Config
from structuredai.sys_probes import free_disk_mb, is_port_open, read_cpu_temp_c, read_rss_mb


class Watchdog:
    """Supervises local llama-server RSS, thermal limits, and disk free space."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.proc: subprocess.Popen | None = None
        self.restarts = 0
        parsed = urlparse(cfg.llm_base_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 18080

    def ensure_llm_ready(self) -> None:
        if not self.cfg.llm_auto_start or self.cfg.llm_provider != "llama_cpp":
            return
        if self.proc and self.proc.poll() is None and is_port_open(self.host, self.port):
            return
        self.start_llama()

    def start_llama(self) -> None:
        self.stop_llama()
        log_p = self.cfg.target_dir / self.cfg.state_dir_name / "llama-server.log"
        log_p.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.cfg.llama_server_bin, "-m", self.cfg.llm_model_path,
            "--host", self.host, "--port", str(self.port),
            "-c", str(self.cfg.llm_ctx_size), "-np", "1", "-t", str(self.cfg.cpu_threads),
            "-ctk", self.cfg.llama_kv_cache_type, "-ctv", self.cfg.llama_kv_cache_type, "--no-warmup",
            *(["--alias", self.cfg.llm_model] if self.cfg.llm_model else []),
            *(["--reasoning-budget", "0"] if self.cfg.llm_disable_thinking else []),
        ]
        self._log_fp = log_p.open("w", encoding="utf-8")
        self.proc = subprocess.Popen(cmd, stdout=self._log_fp, stderr=subprocess.STDOUT, start_new_session=True)
        for _ in range(40):
            if is_port_open(self.host, self.port):
                return
            if self.proc.poll() is not None:
                break
            time.sleep(0.5)
        tail = log_p.read_text(encoding="utf-8", errors="ignore")[-300:] if log_p.exists() else ""
        raise RuntimeError(f"llama-server failed on {self.host}:{self.port}: {tail}")

    def stop_llama(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if hasattr(self, "_log_fp") and self._log_fp:
            self._log_fp.close()
            self._log_fp = None

    def check_health(self, force_restart: bool = False) -> tuple[float, float | None, bool]:
        """Monitor RAM, thermal zone, and disk headroom; returns (rss_mb, temp_c, low_disk)."""
        rss = read_rss_mb(os.getpid()) + (read_rss_mb(self.proc.pid) if self.proc else 0.0)
        if force_restart or (self.proc and rss > self.cfg.llama_rss_restart_mb):
            self.restarts += 1
            self.start_llama()
        temp = read_cpu_temp_c()
        if self.cfg.thermal_pause_c > 0 and temp and temp >= self.cfg.thermal_pause_c:
            time.sleep(15)
        free_mb = free_disk_mb(self.cfg.target_dir)
        if free_mb < self.cfg.disk_min_free_mb:
            self._cleanup_caches()
            free_mb = free_disk_mb(self.cfg.target_dir)
        return rss, temp, free_mb < 512.0

    def _cleanup_caches(self) -> None:
        for name in (".pytest_cache", "__pycache__", ".ruff_cache"):
            for d in self.cfg.target_dir.rglob(name):
                if d.is_dir():
                    shutil.rmtree(d, ignore_errors=True)
