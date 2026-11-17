"""End-to-end mocked-LLM dialectical run, git isolation, steering & CLI tests."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from structuredai.config_loader import build_config
from structuredai.llm_client import LLMResponse
from structuredai.main import main as cli_main
from structuredai.state_machine import OrchestratorEngine
from structuredai.steering import set_steering_status
from structuredai.watchdog import Watchdog


def _fake_llm_complete(self, role: str, sys_p: str, usr_p: str, temp=None) -> LLMResponse:
    if role == "0_ARCHITECT":
        data = {"files": [{"path": "calc.py", "purpose": "Add two ints", "depends_on": [], "req_ids": ["REQ-01"], "is_entry": True}]}
    elif role == "1_DRAFT":
        data = {"filename": "calc.py", "code": "def add(a: int, b: int) -> int:\n    return a + b\n", "exports_summary": "add"}
    elif role == "2_EXTRACT":
        data = {"purpose_summary": "Adds two integers cleanly.", "side_effects": "none"}
    elif role == "3_CRITIQUE":
        data = {"converged": True, "orders": []}
    elif role == "5_SYNTHESIS":
        test_src = (
            "import unittest\nfrom calc import add\n\n"
            "class TestCalc(unittest.TestCase):\n"
            "    def test_add(self):\n"
            "        assert add(2, 3) == 5\n"
            "        assert add(-1, 1) == 0\n\n"
            "if __name__ == '__main__':\n    unittest.main()\n"
        )
        data = {
            "optimized_code": "def add(a: int, b: int) -> int:\n    \"\"\"Return sum of a and b.\"\"\"\n    return a + b\n",
            "test_path": "tests/test_calc.py",
            "test_code": test_src,
        }
    else:
        data = {}
    return LLMResponse(data=data, raw_text=json.dumps(data), prompt_tokens=100, completion_tokens=50, duration_sec=0.2, tokens_per_sec=250.0)


class TestEndToEndAndSteering(unittest.TestCase):
    def test_full_dialectical_cycle_and_cli_steering(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            proj = root / "app"
            proj.mkdir()
            (proj / "SPEC.md").write_text("# SPEC\n- REQ-01: Provide add(a, b)\n", encoding="utf-8")
            env_p = root / ".env"
            env_p.write_text(
                "\n".join([
                    f"TARGET_PROJECT_DIR={proj}",
                    "RUN_DURATION=30m",
                    "LLM_AUTO_START_SERVER=false",
                    "CUSTOM_TEST_CMD=python3 -m unittest {test_file}",
                    "CUSTOM_LINT_CMD=python3 -m py_compile {file}",
                    "DASHBOARD_REFRESH_CYCLES=1",
                    "INTEGRATION_CHECK_INTERVAL=1",
                    "COOLDOWN_MS=0",
                ]) + "\n",
                encoding="utf-8",
            )
            cfg = build_config(env_p)
            wd = Watchdog(cfg)
            eng = OrchestratorEngine(cfg, wd)
            with patch("structuredai.llm_client.LLMClient.complete", new=_fake_llm_complete):
                eng.run()

            state = json.loads((proj / ".orchestrator" / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["nodes"]["calc.py"]["state"], "6_LOCKED")
            self.assertEqual(state["nodes"]["calc.py"]["retries"], 0)
            self.assertEqual(state["time_budget"]["last_green_tag"], "green-step-001")
            self.assertTrue((proj / ".orchestrator" / "RUN_REPORT.md").is_file())
            self.assertTrue((proj / ".orchestrator" / "DASHBOARD.md").is_file())
            self.assertTrue((proj / ".orchestrator" / "tree" / "calc.py" / "REALITY.md").is_file())
            self.assertEqual(cli_main(["pause", "--env", str(env_p)]), 0)
            self.assertIn("STATUS: PAUSE", (proj / ".orchestrator" / "STEERING.md").read_text(encoding="utf-8"))
            self.assertEqual(cli_main(["priority", str(proj / "calc.py"), "--env", str(env_p)]), 0)
            self.assertIn("PRIORITY: calc.py", (proj / ".orchestrator" / "STEERING.md").read_text(encoding="utf-8"))
            set_steering_status(proj / ".orchestrator" / "STEERING.md", "RUN")
            self.assertEqual(cli_main(["status", "--env", str(env_p)]), 0)


if __name__ == "__main__":
    unittest.main()
