"""Chaos tests: JSON noise, stagnation ping-pong, anti-triche, DAG cycles, ripple & security."""

import tempfile
import unittest
from pathlib import Path

from structuredai.error_distiller import StagnationTracker, check_degeneration
from structuredai.graph_ops import detect_cycles, next_actionable_node, propagate_ripple
from structuredai.llm_client import strip_and_parse_json
from structuredai.security_gate import PathJail, scan_dangerous_calls
from structuredai.sys_probes import InstanceLock
from structuredai.validators import anti_trivial_test_gate, check_test_monotonicity, preflight_imports


class TestChaosGuards(unittest.TestCase):
    def test_chaos_1_strip_think_and_fences(self) -> None:
        raw = "<think>long useless thoughts</think>\n```json\n{\"converged\": true, \"orders\": []}\n```"
        self.assertEqual(strip_and_parse_json(raw), {"converged": True, "orders": []})

    def test_chaos_2_stagnation_ping_pong_and_break(self) -> None:
        stag = StagnationTracker(k=5)
        node: dict = {}
        brk1, tmp1, _ = stag.record_and_advise(node, "def a(): return 1", "err1")
        self.assertFalse(brk1)
        self.assertIsNone(tmp1)
        stag.record_and_advise(node, "def a(): return 2", "err2")
        brk_pp, tmp_pp, hint = stag.record_and_advise(node, "def a(): return 1", "err1")
        self.assertFalse(brk_pp)
        self.assertEqual(tmp_pp, 0.45)
        self.assertIn("STAGNATION", hint)
        brk3, _, _ = stag.record_and_advise(node, "def a(): return 1", "err1")
        self.assertTrue(brk3)

    def test_chaos_5_and_8_anti_trivial_and_degeneration(self) -> None:
        self.assertTrue(anti_trivial_test_gate("assert True", "parser", ".py"))
        self.assertTrue(anti_trivial_test_gate("from parser import fn\nfrom unittest.mock import patch\n@patch('parser.fn')\ndef test_x(m): assert 1 == 2\nassert 2 == 3", "parser", ".py"))
        good_test = "from parser import parse\ndef test_ok():\n    assert parse('1m') == 60\n    assert parse('2s') == 2\n"
        self.assertEqual(anti_trivial_test_gate(good_test, "parser", ".py"), [])
        self.assertIsNotNone(check_test_monotonicity(good_test, "def test_ok():\n    assert True\n"))
        big = "\n".join(f"x_{i} = {i}" for i in range(20))
        self.assertIsNotNone(check_degeneration(big, "def f():\n    return True\n"))

    def test_chaos_7_and_11_cycles_and_ripple(self) -> None:
        cyc = detect_cycles({"a.py": ["b.py"], "b.py": ["a.py"]})
        self.assertEqual(cyc, ["a.py", "b.py", "a.py"])
        nodes = {
            "types.py": {"state": "6_LOCKED", "depends_on": []},
            "core.py": {"state": "6_LOCKED", "depends_on": ["types.py"]},
        }
        impacted = propagate_ripple(nodes, "types.py")
        self.assertEqual(impacted, ["core.py"])
        self.assertEqual(next_actionable_node(nodes), "core.py")

    def test_chaos_9_and_12_pathjail_dangerous_and_flock(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            jail = PathJail(root, ".orchestrator")
            for bad in ("../outside.py", "SPEC.md", ".env", ".orchestrator/state.json", ".git/config"):
                with self.assertRaises(PermissionError):
                    jail.assert_writable_by_agent(bad)
            self.assertTrue(scan_dangerous_calls("import os; os.system('rm -rf /')"))
            self.assertTrue(scan_dangerous_calls("app.run(port=18080)"))
            lock_p = root / ".orchestrator" / "orchestrator.lock"
            lk1 = InstanceLock(lock_p)
            with self.assertRaises(RuntimeError):
                InstanceLock(lock_p)
            lk1.release()

    def test_preflight_imports_catches_hallucinated_symbol(self) -> None:
        errs = preflight_imports("from core.hash import fake_fn\n", ".py", {"core/hash.py": {"real_fn"}}, set())
        self.assertTrue(errs and "real_fn" in errs[0])


if __name__ == "__main__":
    unittest.main()
