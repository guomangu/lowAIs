"""Adaptive time-budget manager with dual-clock accounting and 5 horizons."""

import time

HORIZON_PROFILES = {
    "balanced": (0.08, 0.55, 0.80, 0.95),
    "sprint": (0.05, 0.55, 0.90, 0.95),
    "hardening": (0.12, 0.35, 0.65, 0.93),
}


class TimeBudgetManager:
    """Controls time horizons, active tick accumulation and graceful degradation."""

    def __init__(
        self,
        total_seconds: int,
        profile: str = "balanced",
        accounting_mode: str = "active",
        freeze_ratio: float = 0.05,
        node_cap_ratio: float = 0.10,
        heartbeat_sec: int = 30,
        elapsed_active: float = 0.0,
    ) -> None:
        self.total_seconds = max(1, total_seconds)
        self.profile = profile if profile in HORIZON_PROFILES else "balanced"
        self.accounting_mode = accounting_mode
        self.freeze_ratio = freeze_ratio
        self.node_cap_ratio = node_cap_ratio
        self.heartbeat_sec = max(5, heartbeat_sec)
        self.elapsed_active = elapsed_active
        self.start_wall = time.time()
        self.last_mono = time.monotonic()

    def tick(self, paused: bool = False) -> float:
        """Advance active or wall clock; returns elapsed seconds used for ratio."""
        now_mono = time.monotonic()
        delta = max(0.0, now_mono - self.last_mono)
        self.last_mono = now_mono
        if not paused:
            capped = min(delta, float(self.heartbeat_sec * 2))
            self.elapsed_active += capped
        if self.accounting_mode == "wall_clock":
            return max(self.elapsed_active, time.time() - self.start_wall)
        return self.elapsed_active

    def progress_ratio(self) -> float:
        """Return normalized progress in [0.0, 1.0+]."""
        used = self.elapsed_active
        if self.accounting_mode == "wall_clock":
            used = max(used, time.time() - self.start_wall)
        return used / float(self.total_seconds)

    def remaining_seconds(self) -> float:
        """Return remaining seconds before hard deadline."""
        used = self.progress_ratio() * self.total_seconds
        return max(0.0, float(self.total_seconds) - used)

    def current_horizon(self) -> str:
        """Determine current strategic horizon H0..H4."""
        r = self.progress_ratio()
        h0, h1, h2, h3 = HORIZON_PROFILES[self.profile]
        freeze_at = min(h3, 1.0 - self.freeze_ratio)
        if r >= freeze_at:
            return "H4_FROZEN"
        if r >= h2:
            return "H3_HARDEN"
        if r >= h1:
            return "H2_ALIGN"
        if r >= h0:
            return "H1_BUILD"
        return "H0_INGEST"

    def is_frozen(self) -> bool:
        """True once inside the final freeze window."""
        return self.current_horizon() == "H4_FROZEN"

    def node_exceeded_cap(self, node_spent_sec: float) -> bool:
        """Prevent a single difficult node from starving the global run."""
        return node_spent_sec >= (self.total_seconds * self.node_cap_ratio)

    def effective_limits(
        self, base_retries: int, base_rebalance: int, pending_nodes: int, avg_call_sec: float
    ) -> tuple[int, int]:
        """Gracefully tighten retries/rebalance under late time pressure."""
        rem = self.remaining_seconds() * (1.0 - self.freeze_ratio)
        if pending_nodes <= 0 or avg_call_sec <= 0:
            return base_retries, base_rebalance
        per_node = rem / float(pending_nodes)
        if per_node < 3.0 * avg_call_sec:
            return min(base_retries, 3), min(base_rebalance, 1)
        return base_retries, base_rebalance
