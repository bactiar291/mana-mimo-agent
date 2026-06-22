import importlib
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from tools import extra_tools, tools
from lib import search_engine


class ToolAuditRegressionTest(unittest.TestCase):
    def test_memory_list_alias_returns_memory_instead_of_error(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "tools.extra_tools.MEMORY_FILE", os.path.join(tmpdir, "memory.json")
        ):
            result = json.loads(extra_tools.memory_tool("list"))

        self.assertNotIn("error", result)
        self.assertIn("facts", result)
        self.assertIn("preferences", result)
        self.assertIn("notes", result)

    def test_skill_view_missing_skill_uses_success_false_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch("tools.extra_tools.SKILLS_DIR", tmpdir):
            result = json.loads(extra_tools.skill_view("missing"))

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "not_found")
        self.assertIn("Skill 'missing' not found", result["error"])

    def test_runtime_skill_view_missing_skill_uses_success_false_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch("tools.skill_manager.SKILLS_DIR", tmpdir):
            result = json.loads(tools.call_tool("skill_view", {"name": "missing"}))

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "not_found")
        self.assertIn("Skill 'missing' not found", result["error"])

    def test_runtime_search_files_accepts_glob_in_files_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "demo.txt")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("demo")

            result = json.loads(tools.call_tool("search_files", {"pattern": "*.txt", "path": tmpdir, "target": "files"}))

        self.assertEqual(result["count"], 1)
        self.assertTrue(result["results"][0].endswith("demo.txt"))

    def test_search_engine_reports_duckduckgo_challenge_as_blocked(self):
        challenge_html = """
        <html><body>
          <form id="challenge-form" action="//duckduckgo.com/anomaly.js"></form>
        </body></html>
        """.encode()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return challenge_html

        with patch("lib.search_engine.urllib.request.urlopen", return_value=FakeResponse()):
            results = search_engine.search_duckduckgo("example", 1)

        self.assertEqual(results[0]["error"], "DuckDuckGo: blocked_by_challenge")

    def test_web_search_preserves_engine_failure_reasons(self):
        with patch("lib.search_engine.search_duckduckgo", return_value=[{"error": "DuckDuckGo: blocked_by_challenge"}]), patch(
            "lib.search_engine.search_searxng", return_value=[{"error": "SearXNG: All instances failed"}]
        ), patch("lib.search_engine.search_wikipedia", return_value=[{"error": "Wikipedia: no_results"}]), patch(
            "lib.search_engine.search_brave", return_value=[{"error": "Brave: API key required"}]
        ):
            result = search_engine.web_search("example", 1)

        self.assertEqual(result["engine"], "none")
        self.assertIn("failures", result)
        self.assertIn("DuckDuckGo: blocked_by_challenge", result["failures"])
        self.assertIn("SearXNG: All instances failed", result["failures"])

    def test_root_launcher_imports_cli_main(self):
        launcher = importlib.import_module("p")

        self.assertTrue(callable(launcher.main))


if __name__ == "__main__":
    unittest.main()
