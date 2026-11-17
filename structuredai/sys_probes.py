"""Low-level Linux system probes & single-instance file lock."""

import fcntl
import os
import shutil
import socket
from pathlib import Path


class InstanceLock:
    """Exclusive non-blocking lock preventing concurrent runs on the same project."""

    def __init__(self, lock_path: Path) -> None:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = lock_path.open("w", encoding="utf-8")
        try:
            fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fp.write(f"{os.getpid()}\n")
            self._fp.flush()
        except BlockingIOError as exc:
            self._fp.close()
            raise RuntimeError(f"Another StructuredAI instance owns {lock_path}") from exc

    def release(self) -> None:
        fcntl.flock(self._fp.fileno(), fcntl.LOCK_UN)
        self._fp.close()


def read_rss_mb(pid: int) -> float:
    """Read resident set size (VmRSS) from /proc/<pid>/status."""
    try:
        for ln in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
            if ln.startswith("VmRSS:"):
                return int(ln.split()[1]) / 1024.0
    except OSError:
        pass
    return 0.0


def read_cpu_temp_c() -> float | None:
    """Read max thermal zone temperature in Celsius if available."""
    temps: list[float] = []
    for p in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
        try:
            temps.append(int(p.read_text().strip()) / 1000.0)
        except (OSError, ValueError):
            continue
    return max(temps) if temps else None


def free_disk_mb(path: Path) -> float:
    return shutil.disk_usage(path).free / (1024.0 * 1024.0)


def is_port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0
