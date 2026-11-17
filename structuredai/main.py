"""CLI entry point for StructuredAI: start, doctor, status, pause, resume, priority, retry, stop."""

import argparse
import shutil
import signal
import sys
from pathlib import Path

from structuredai.config_loader import build_config, validate_config
from structuredai.state_machine import OrchestratorEngine
from structuredai.steering import append_steering_directive, set_steering_status
from structuredai.sys_probes import InstanceLock, free_disk_mb
from structuredai.watchdog import Watchdog


def _rel_target(target_dir: Path, raw_path: str) -> str:
    p = Path(raw_path)
    if p.is_absolute():
        try:
            return str(p.resolve().relative_to(target_dir.resolve()))
        except ValueError:
            return p.name
    return raw_path


def cmd_doctor(cfg) -> int:
    errs = validate_config(cfg)
    print(f"[doctor] Target dir : {cfg.target_dir}")
    print(f"[doctor] AI model   : {cfg.llm_model} ({cfg.llm_provider} @ {cfg.llm_base_url})")
    print(f"[doctor] Duration   : {cfg.run_duration_sec}s ({cfg.time_accounting_mode})")
    print(f"[doctor] RAM limit  : {cfg.ram_limit_mb} Mo | Disk free: {free_disk_mb(cfg.target_dir if cfg.target_dir.exists() else Path.cwd()):.0f} Mo")
    print(f"[doctor] git        : {shutil.which('git') or 'MISSING'}")
    print(f"[doctor] llama-srv  : {shutil.which(cfg.llama_server_bin) or 'MISSING'}")
    if cfg.llm_auto_start and cfg.llm_provider == "llama_cpp" and not Path(cfg.llm_model_path).is_file():
        errs.append(f"GGUF model not found at LLM_MODEL_PATH={cfg.llm_model_path}")
    if errs:
        for e in errs:
            print(f"[ERROR] {e}", file=sys.stderr)
        return 1
    print("[doctor] OK - Ready for autonomous run.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="structuredai")
    p.add_argument("action", nargs="?", default="start", choices=["start", "doctor", "status", "pause", "resume", "stop", "priority", "retry"])
    p.add_argument("target", nargs="?", default="")
    p.add_argument("--env", default=".env")
    args = p.parse_args(argv)
    cfg = build_config(Path(args.env))
    sdir = cfg.target_dir / cfg.state_dir_name
    steering = sdir / "STEERING.md"
    if args.action == "doctor":
        return cmd_doctor(cfg)
    if args.action == "status":
        dash = sdir / "DASHBOARD.md"
        print(dash.read_text(encoding="utf-8") if dash.is_file() else "No active DASHBOARD.md yet.")
        return 0
    if args.action in {"pause", "resume", "stop"}:
        set_steering_status(steering, {"pause": "PAUSE", "resume": "RUN", "stop": "STOP"}[args.action])
        print(f"STEERING.md updated -> STATUS: {args.action.upper()}")
        return 0
    if args.action in {"priority", "retry"}:
        if not args.target:
            print("Target file required", file=sys.stderr)
            return 2
        rel = _rel_target(cfg.target_dir, args.target)
        append_steering_directive(steering, args.action.upper(), rel)
        print(f"STEERING.md updated -> {args.action.upper()}: {rel}")
        return 0
    if errs := validate_config(cfg):
        for e in errs:
            print(f"[CONFIG ERROR] {e}", file=sys.stderr)
        return 1
    lock = InstanceLock(sdir / "orchestrator.lock")
    wd = Watchdog(cfg)
    eng = OrchestratorEngine(cfg, wd)
    signal.signal(signal.SIGINT, lambda *_: setattr(eng, "stop_flag", True))
    signal.signal(signal.SIGTERM, lambda *_: setattr(eng, "stop_flag", True))
    try:
        set_steering_status(steering, "RUN")
        eng.run()
    finally:
        wd.stop_llama()
        lock.release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
