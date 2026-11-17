"""Tests for Zed JSONC settings patching & StructuredAI Local ACP server."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from structuredai.config_loader import build_config
from structuredai.zed_acp import handle_prompt, handle_rpc
from structuredai.zed_config import parse_jsonc, patch_zed_settings


class TestZedIntegration(unittest.TestCase):
    def test_parse_jsonc_and_patch_preserves_existing_settings(self) -> None:
        raw = '// header\n{\n  "theme": { "mode": "dark", },\n  "agent_servers": { "claude-acp": { "type": "registry" } },\n}\n'
        parsed = parse_jsonc(raw)
        self.assertEqual(parsed["theme"]["mode"], "dark")
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            env_p = root / ".env"
            env_p.write_text(f"TARGET_PROJECT_DIR={root / 'proj'}\nLLM_MODEL=qwen3.5-0.8b-q4_k_m\nLLM_BASE_URL=http://127.0.0.1:18080/v1\n", encoding="utf-8")
            cfg = build_config(env_p)
            settings_p = root / "settings.json"
            settings_p.write_text(raw, encoding="utf-8")
            patch_zed_settings(settings_p, cfg, root, env_p, include_global=True)
            self.assertTrue((root / "settings.json.bak").is_file())
            out = json.loads(settings_p.read_text(encoding="utf-8"))
            self.assertEqual(out["theme"]["mode"], "dark")
            self.assertIn("claude-acp", out["agent_servers"])
            self.assertIn("StructuredAI Local", out["agent_servers"])
            self.assertEqual(out["agent"]["default_model"]["provider"], "structuredai_local")
            self.assertEqual(out["agent"]["default_model"]["model"], "qwen3.5-0.8b-q4_k_m")
            self.assertEqual(out["language_models"]["openai_compatible"]["structuredai_local"]["api_url"], "http://127.0.0.1:18080/v1")

    def test_acp_initialize_session_and_steering_commands(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proj = root / "proj"
            (proj / ".orchestrator").mkdir(parents=True)
            (proj / ".orchestrator" / "DASHBOARD.md").write_text("# Live OK", encoding="utf-8")
            env_p = root / ".env"
            env_p.write_text(f"TARGET_PROJECT_DIR={proj}\n", encoding="utf-8")
            cfg = build_config(env_p)
            buf = io.StringIO()
            with patch("sys.stdout", buf):
                handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, cfg)
                handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "session/new", "params": {}}, cfg)
                handle_rpc({"jsonrpc": "2.0", "id": 3, "method": "session/prompt", "params": {"sessionId": "s1", "prompt": [{"type": "text", "text": "/status"}]}}, cfg)
            lines = [json.loads(x) for x in buf.getvalue().splitlines() if x.strip()]
            self.assertEqual(lines[0]["result"]["agentInfo"]["title"], "StructuredAI Local")
            self.assertEqual(lines[1]["result"]["sessionId"], "sai-local-1")
            self.assertIn("# Live OK", lines[2]["params"]["update"]["content"]["text"])
            self.assertEqual(lines[3]["result"]["stopReason"], "end_turn")
            self.assertIn("PAUSE", handle_prompt(cfg, "/pause"))
            self.assertIn("STATUS: PAUSE", (proj / ".orchestrator" / "STEERING.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
