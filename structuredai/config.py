"""Immutable configuration dataclass for StructuredAI."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    target_dir: Path
    project_mode: str
    spec_path: Path
    metadata_storage: str
    state_dir_name: str
    run_duration_sec: int
    time_accounting_mode: str
    time_profile: str
    freeze_ratio: float
    node_cap_ratio: float
    max_idle_hardening: int
    heartbeat_sec: int
    resume_mode: str
    llm_provider: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_model_path: str
    llama_server_bin: str
    llm_auto_start: bool
    llm_ctx_size: int
    llm_max_output_tokens: int
    llm_temperature: float
    llm_disable_thinking: bool
    llm_structured_mode: str
    llm_critique_model: str
    llm_timeout_sec: int
    min_tokens_per_sec: float
    ram_limit_mb: int
    llama_rss_restart_mb: int
    llama_kv_cache_type: str
    cpu_threads: int
    subprocess_timeout_sec: int
    thermal_pause_c: int
    cooldown_ms: int
    disk_min_free_mb: int
    max_events_log_mb: int
    target_stack: str
    stack_profile_path: str
    dep_install_policy: str
    max_lines_per_file: int
    min_split_lines: int
    max_files_per_dir: int
    max_tree_depth: int
    exempt_exts: tuple[str, ...]
    max_ingest_bytes: int
    custom_cmds: dict[str, str]
    max_retries: int
    max_rebalance_cycles: int
    integration_interval: int
    git_auto_commit: bool
    git_work_branch: str
    max_green_tags_keep: int
    allow_network_tests: bool
    enable_import_preflight: bool
    enable_anti_trivial: bool
    enable_test_monotonicity: bool
    enable_stagnation: bool
    enable_dangerous_scan: bool
    dashboard_refresh_cycles: int
    zed_sync_tasks: bool
