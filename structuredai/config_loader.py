"""Config builder and validation helpers (strictly <= 100 lines)."""

from pathlib import Path

from structuredai.config import Config
from structuredai.env_parse import env_bool as _b
from structuredai.env_parse import env_get as _get
from structuredai.env_parse import load_dotenv, parse_duration


def build_config(env_path: Path | None = None) -> Config:
    """Load .env + os.environ into a validated Config object."""
    path = env_path or (Path.cwd() / ".env")
    e = load_dotenv(path)
    target = Path(_get(e, "TARGET_PROJECT_DIR", str(Path.cwd() / "workspace"))).expanduser().resolve()
    raw_spec = _get(e, "INITIAL_SPEC_PATH", "SPEC.md")
    spec = Path(raw_spec).expanduser()
    if not spec.is_absolute():
        spec = target / spec
    raw_exts = _get(e, "LINE_LIMIT_EXEMPT_EXTS", ".md,.json,.toml,.yaml,.yml,.lock,.sql,.css,.svg")
    exts = tuple(x.strip().lower() for x in raw_exts.split(",") if x.strip())
    return Config(
        target_dir=target, project_mode=_get(e, "PROJECT_MODE", "auto"), spec_path=spec.resolve(),
        metadata_storage=_get(e, "METADATA_STORAGE", "shadow"), state_dir_name=_get(e, "ORCHESTRATOR_STATE_DIR", ".orchestrator"),
        run_duration_sec=parse_duration(_get(e, "RUN_DURATION", "24h")), time_accounting_mode=_get(e, "TIME_ACCOUNTING_MODE", "active"),
        time_profile=_get(e, "TIME_PROFILE", "balanced"), freeze_ratio=float(_get(e, "FREEZE_WINDOW_RATIO", "0.05")),
        node_cap_ratio=float(_get(e, "NODE_TIME_CAP_RATIO", "0.10")), max_idle_hardening=int(_get(e, "MAX_IDLE_HARDENING_CYCLES", "10")),
        heartbeat_sec=int(_get(e, "HEARTBEAT_INTERVAL_SEC", "30")), resume_mode=_get(e, "RESUME_MODE", "auto"),
        llm_provider=_get(e, "LLM_PROVIDER", "llama_cpp"), llm_base_url=_get(e, "LLM_BASE_URL", "http://127.0.0.1:18080/v1"),
        llm_api_key=_get(e, "LLM_API_KEY", ""), llm_model=_get(e, "LLM_MODEL", "qwen3.5-0.8b-q4_k_m"),
        llm_model_path=_get(e, "LLM_MODEL_PATH", ""), llama_server_bin=_get(e, "LLAMA_SERVER_BIN", "llama-server"),
        llm_auto_start=_b(e, "LLM_AUTO_START_SERVER", True), llm_ctx_size=int(_get(e, "LLM_CTX_SIZE", "4096")),
        llm_max_output_tokens=int(_get(e, "LLM_MAX_OUTPUT_TOKENS", "1024")), llm_temperature=float(_get(e, "LLM_TEMPERATURE", "0.2")),
        llm_disable_thinking=_b(e, "LLM_DISABLE_THINKING", True), llm_structured_mode=_get(e, "LLM_STRUCTURED_MODE", "gbnf"),
        llm_critique_model=_get(e, "LLM_CRITIQUE_MODEL", ""), llm_timeout_sec=int(_get(e, "LLM_TIMEOUT_SEC", "90")),
        min_tokens_per_sec=float(_get(e, "MIN_LLM_TOKENS_PER_SEC", "5")), ram_limit_mb=int(_get(e, "RAM_LIMIT_MB", "1024")),
        llama_rss_restart_mb=int(_get(e, "LLAMA_RSS_RESTART_MB", "880")), llama_kv_cache_type=_get(e, "LLAMA_KV_CACHE_TYPE", "q8_0"),
        cpu_threads=int(_get(e, "CPU_THREADS", "4")), subprocess_timeout_sec=int(_get(e, "SUBPROCESS_TIMEOUT_SEC", "45")),
        thermal_pause_c=int(_get(e, "THERMAL_PAUSE_C", "85")), cooldown_ms=int(_get(e, "COOLDOWN_MS", "100")),
        disk_min_free_mb=int(_get(e, "DISK_MIN_FREE_MB", "2048")), max_events_log_mb=int(_get(e, "MAX_EVENTS_LOG_MB", "50")),
        target_stack=_get(e, "TARGET_STACK", "auto"), stack_profile_path=_get(e, "STACK_PROFILE_PATH", ""),
        dep_install_policy=_get(e, "DEPENDENCY_INSTALL_POLICY", "manifest_only"), max_lines_per_file=int(_get(e, "MAX_LINES_PER_FILE", "100")),
        min_split_lines=int(_get(e, "MIN_SPLIT_FILE_LINES", "15")), max_files_per_dir=int(_get(e, "MAX_FILES_PER_DIR", "5")),
        max_tree_depth=int(_get(e, "MAX_TREE_DEPTH", "4")), exempt_exts=exts,
        max_ingest_bytes=int(_get(e, "MAX_INGEST_FILE_BYTES", "262144")),
        custom_cmds={
            "syntax_check": _get(e, "CUSTOM_SYNTAX_CMD", ""), "lint": _get(e, "CUSTOM_LINT_CMD", ""),
            "test_targeted": _get(e, "CUSTOM_TEST_CMD", ""), "build_check": _get(e, "CUSTOM_BUILD_CMD", ""),
        },
        max_retries=int(_get(e, "MAX_RETRIES_PER_NODE", "5")), max_rebalance_cycles=int(_get(e, "MAX_REBALANCE_CYCLES", "2")),
        integration_interval=int(_get(e, "INTEGRATION_CHECK_INTERVAL", "5")), git_auto_commit=_b(e, "GIT_AUTO_COMMIT", True),
        git_work_branch=_get(e, "GIT_WORK_BRANCH", "ai-auto"), max_green_tags_keep=int(_get(e, "MAX_GREEN_TAGS_KEEP", "20")),
        allow_network_tests=_b(e, "ALLOW_NETWORK_IN_TESTS", False), enable_import_preflight=_b(e, "ENABLE_IMPORT_PREFLIGHT", True),
        enable_anti_trivial=_b(e, "ENABLE_ANTI_TRIVIAL_TEST_GATE", True), enable_test_monotonicity=_b(e, "ENABLE_TEST_MONOTONICITY_GATE", True),
        enable_stagnation=_b(e, "ENABLE_STAGNATION_DETECTOR", True), enable_dangerous_scan=_b(e, "ENABLE_DANGEROUS_CALL_SCANNER", True),
        dashboard_refresh_cycles=int(_get(e, "DASHBOARD_REFRESH_CYCLES", "5")), zed_sync_tasks=_b(e, "ZED_SYNC_TASKS", True),
    )


def validate_config(cfg: Config) -> list[str]:
    """Return a list of fail-fast validation errors, empty if valid."""
    errs: list[str] = []
    if cfg.ram_limit_mb < 512:
        errs.append("RAM_LIMIT_MB must be >= 512")
    if cfg.llama_rss_restart_mb >= cfg.ram_limit_mb:
        errs.append("LLAMA_RSS_RESTART_MB must be < RAM_LIMIT_MB")
    if not (0.02 <= cfg.freeze_ratio <= 0.25):
        errs.append("FREEZE_WINDOW_RATIO must be within [0.02, 0.25]")
    if cfg.llm_ctx_size < 2048 or cfg.llm_max_output_tokens >= cfg.llm_ctx_size:
        errs.append("Invalid LLM_CTX_SIZE / LLM_MAX_OUTPUT_TOKENS")
    if cfg.max_lines_per_file < 30 or cfg.min_split_lines >= cfg.max_lines_per_file:
        errs.append("Invalid MAX_LINES_PER_FILE / MIN_SPLIT_FILE_LINES")
    return errs
