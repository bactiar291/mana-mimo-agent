import os
import unittest
from unittest.mock import patch

from tools import deep_audit, tool_profile


class DeepAuditSmokeTest(unittest.TestCase):
    def test_deep_audit_core_scenarios_pass(self):
        report = deep_audit.run_deep_audit(include_browser=False)

        # The registry is trimmed by the active tool profile, so assert the
        # registry and the advertised schema agree instead of a frozen count.
        self.assertEqual(report["registered_tools"], report["schema_tools"])
        self.assertGreater(report["registered_tools"], 0)
        self.assertEqual(report["tool_failures"], [])
        self.assertEqual(report["agent_failures"], [])
        self.assertTrue(report["passed"])
        self.assertGreaterEqual(report["tool_status_counts"].get("ok", 0), 50)
        self.assertEqual(report["agent_status_counts"].get("ok"), 4)

    def test_agent_loop_scenarios_cover_light_medium_hard_and_coding(self):
        names = {scenario["name"] for scenario in deep_audit.AGENT_LOOP_SCENARIOS}

        self.assertIn("light_final_answer", names)
        self.assertIn("medium_tool_then_final", names)
        self.assertIn("hard_multi_tool_loop", names)
        self.assertIn("coding_task_tool_loop", names)


class ToolProfileTest(unittest.TestCase):
    def test_lean_profile_is_the_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MIMO_TOOL_PROFILE", None)
            self.assertEqual(tool_profile.active_profile(), "lean")

    def test_full_profile_keeps_every_registered_tool(self):
        registry = {"read_file": {}, "notify_sms": {}}

        with patch.dict(os.environ, {"MIMO_TOOL_PROFILE": "full"}):
            removed = tool_profile.apply_profile(registry)

        self.assertEqual(removed, [])
        self.assertEqual(set(registry), {"read_file", "notify_sms"})

    def test_lean_profile_drops_unverified_tools(self):
        registry = {"read_file": {}, "notify_sms": {}, "mcp_reload": {}}

        with patch.dict(os.environ, {"MIMO_TOOL_PROFILE": "lean"}):
            removed = tool_profile.apply_profile(registry)

        self.assertEqual(removed, ["mcp_reload", "notify_sms"])
        self.assertEqual(set(registry), {"read_file"})

    def test_unknown_profile_falls_back_to_lean(self):
        with patch.dict(os.environ, {"MIMO_TOOL_PROFILE": "banana"}):
            self.assertEqual(tool_profile.active_profile(), "lean")

    def test_lean_surface_excludes_known_not_implemented_tools(self):
        for name in ("notify_email", "notify_sms", "mcp_reload", "voice_transcribe"):
            self.assertNotIn(name, tool_profile.LEAN_TOOLS)


if __name__ == "__main__":
    unittest.main()
