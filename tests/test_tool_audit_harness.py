import unittest

from tools import audit_harness


class ToolAuditHarnessTest(unittest.TestCase):
    def test_all_registered_tools_are_classified(self):
        report = audit_harness.run_audit()

        self.assertEqual(report["registered_tools"], report["schema_tools"])
        self.assertEqual(report["structural_issues"], [])
        self.assertEqual(report["failures"], [])
        self.assertEqual(report["unclassified"], [])
        self.assertTrue(report["passed"])

    def test_known_tool_categories_are_stable(self):
        self.assertEqual(audit_harness.classify_tool("web_search"), "safe_smoke")
        self.assertEqual(audit_harness.classify_tool("write_file"), "destructive_or_write")
        self.assertEqual(audit_harness.classify_tool("browser_click"), "external_or_stateful")
        self.assertEqual(audit_harness.classify_tool("skill_view"), "expected_failure")


if __name__ == "__main__":
    unittest.main()
