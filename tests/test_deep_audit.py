import unittest

from tools import deep_audit


class DeepAuditSmokeTest(unittest.TestCase):
    def test_deep_audit_core_scenarios_pass(self):
        report = deep_audit.run_deep_audit(include_browser=False)

        self.assertEqual(report["registered_tools"], 204)
        self.assertEqual(report["schema_tools"], 204)
        self.assertEqual(report["tool_failures"], [])
        self.assertEqual(report["agent_failures"], [])
        self.assertTrue(report["passed"])
        self.assertGreaterEqual(report["tool_status_counts"].get("ok", 0), 80)
        self.assertEqual(report["agent_status_counts"].get("ok"), 4)

    def test_agent_loop_scenarios_cover_light_medium_hard_and_coding(self):
        names = {scenario["name"] for scenario in deep_audit.AGENT_LOOP_SCENARIOS}

        self.assertIn("light_final_answer", names)
        self.assertIn("medium_tool_then_final", names)
        self.assertIn("hard_multi_tool_loop", names)
        self.assertIn("coding_task_tool_loop", names)


if __name__ == "__main__":
    unittest.main()
