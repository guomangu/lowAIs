"""Configure Zed global & project settings to select local StructuredAI LLM by default."""

import json
import re
import shutil
import sys
from pathlib import Path

from structuredai.config import Config
from structuredai.config_loader import build_config

_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
_COMMENT_OR_STR_RE = re.compile(r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*[\s\S]*?\*/')


def parse_jsonc(raw: str) -> dict:
    """Parse JSON with // or /* */ comments and trailing commas safely."""
    no_comments = _COMMENT_OR_STR_RE.sub(lambda m: m.group(1) or "", raw)
    cleaned = _TRAILING_COMMA_RE.sub(r"\1", no_comments).strip()
    return json.loads(cleaned) if cleaned else {}


def build_provider_entry(cfg: Config) -> dict:
    """Build Zed language_models.openai_compatible.structuredai_local block."""
    return {
        "api_url": cfg.llm_base_url.rstrip("/"),
        "available_models": [{
            "name": cfg.llm_model,
            "display_name": f"StructuredAI Local ({cfg.llm_model})",
            "max_tokens": cfg.llm_ctx_size,
            "max_output_tokens": cfg.llm_max_output_tokens,
            "capabilities": {"tools": True, "images": False, "parallel_tool_calls": False, "chat_completions": True},
        }],
    }


def patch_zed_settings(settings_path: Path, cfg: Config, root_dir: Path, env_path: Path, include_global: bool) -> None:
    """Safely merge local AI model, default_model & ACP server into Zed settings.json."""
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    data = parse_jsonc(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
    if settings_path.is_file() and not settings_path.with_suffix(".json.bak").exists():
        shutil.copy2(settings_path, settings_path.with_suffix(".json.bak"))
    agent = data.setdefault("agent", {})
    agent["default_model"] = {"provider": "structuredai_local", "model": cfg.llm_model, "enable_thinking": False}
    favs = [f for f in agent.get("favorite_models", []) if f.get("provider") != "structuredai_local"]
    agent["favorite_models"] = [{"provider": "structuredai_local", "model": cfg.llm_model}, *favs]
    if include_global:
        lms = data.setdefault("language_models", {})
        oai = lms.setdefault("openai_compatible", {})
        oai["structuredai_local"] = build_provider_entry(cfg)
        srvs = data.setdefault("agent_servers", {})
        srvs["StructuredAI Local"] = {
            "type": "custom",
            "command": str((root_dir / "scripts" / "zed-acp.sh").resolve()),
            "args": [],
            "env": {"STRUCTURED_AI_ENV": str(env_path.resolve()), "STRUCTUREDAI_LOCAL_API_KEY": "local"},
        }
    settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sync_all_zed_configs(root_dir: Path, env_path: Path) -> list[Path]:
    """Update Flatpak/native Zed user settings and workspace .zed/settings.json."""
    cfg = build_config(env_path)
    updated: list[Path] = []
    home = Path.home()
    candidates = [
        home / ".var" / "app" / "dev.zed.Zed" / "config" / "zed" / "settings.json",
        home / ".config" / "zed" / "settings.json",
    ]
    for c in candidates:
        if c.parent.parent.exists() or c.exists():
            patch_zed_settings(c, cfg, root_dir, env_path, include_global=True)
            updated.append(c)
    for proj_cfg in (root_dir / ".zed" / "settings.json", cfg.target_dir / ".zed" / "settings.json"):
        patch_zed_settings(proj_cfg, cfg, root_dir, env_path, include_global=False)
        updated.append(proj_cfg)
    return updated


if __name__ == "__main__":
    r = Path(sys.argv[1]).resolve()
    e = Path(sys.argv[2]).resolve()
    for p in sync_all_zed_configs(r, e):
        print(f"[Zed] Configured: {p}")
