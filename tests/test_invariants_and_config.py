"""Tests for invariants (<=100L/module), .env config & TimeBudgetManager."""

import json
import tempfile
import unittest
from pathlib import Path

from structuredai.config_loader import build_config, validate_config
from structuredai.env_parse import parse_duration
from structuredai.time_budget import TimeBudgetManager

ROOT = Path(__file__).resolve().parent.parent


class TestInvariantsAndConfig(unittest.TestCase):
    def test_all_framework_modules_under_100_lines(self) -> None:
        py_files = sorted((ROOT / "structuredai").glob("*.py"))
        self.assertGreaterEqual(len(py_files), 20)
        for p in py_files:
            lines = len(p.read_text(encoding="utf-8").splitlines())
            self.assertLessEqual(lines, 100, f"{p.name} has {lines} lines (>100)")

    def test_zed_tasks_valid_json(self) -> None:
        tasks = json.loads((ROOT / ".zed" / "tasks.json").read_text(encoding="utf-8"))
        self.assertTrue(isinstance(tasks, list) and len(tasks) >= 8)
        for t in tasks:
            self.assertIn("label", t)
            self.assertIn("command", t)

    def test_parse_duration_and_config_validation(self) -> None:
        self.assertEqual(parse_duration("30m"), 1800)
        self.assertEqual(parse_duration("24h"), 86400)
        self.assertEqual(parse_duration("3d"), 259200)
        with self.assertRaises(ValueError):
            parse_duration("0h")
        with tempfile.TemporaryDirectory() as td:
            env_p = Path(td) / ".env"
            env_p.write_text(f"TARGET_PROJECT_DIR={td}/proj\nRAM_LIMIT_MB=1024\nLLAMA_RSS_RESTART_MB=880\n", encoding="utf-8")
            cfg = build_config(env_p)
            self.assertEqual(validate_config(cfg), [])
            bad_p = Path(td) / ".env.bad"
            bad_p.write_text("RAM_LIMIT_MB=1024\nLLAMA_RSS_RESTART_MB=1200\n", encoding="utf-8")
            self.assertTrue(validate_config(build_config(bad_p)))

    def test_time_budget_horizons_and_degradation(self) -> None:
        tbm = TimeBudgetManager(total_seconds=1000, profile="balanced", freeze_ratio=0.05)
        self.assertEqual(tbm.current_horizon(), "H0_INGEST")
        tbm.elapsed_active = 200.0
        self.assertEqual(tbm.current_horizon(), "H1_BUILD")
        tbm.elapsed_active = 600.0
        self.assertEqual(tbm.current_horizon(), "H2_ALIGN")
        tbm.elapsed_active = 850.0
        self.assertEqual(tbm.current_horizon(), "H3_HARDEN")
        tbm.elapsed_active = 960.0
        self.assertTrue(tbm.is_frozen())
        r, reb = tbm.effective_limits(5, 2, pending_nodes=20, avg_call_sec=10.0)
        self.assertEqual((r, reb), (3, 1))


if __name__ == "__main__":
    unittest.main()
