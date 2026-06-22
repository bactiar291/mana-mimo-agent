import json
import os
import tempfile
import unittest
from unittest.mock import patch

from tools import delegation


class FakeAgent:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def chat(self, prompt):
        return f"real agent result for: {prompt.splitlines()[0]}"


class DelegationSmokeTest(unittest.TestCase):
    def test_delegate_task_runs_agent_and_persists_result_in_sync_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "tools.delegation.DELEGATION_DIR", tmpdir
        ), patch.dict(os.environ, {"MIMO_DELEGATE_SYNC": "1"}), patch(
            "core.agent.MiMoAgent", FakeAgent
        ):
            created = json.loads(delegation.delegate_task("audit tools", "ctx"))
            status = json.loads(delegation.delegate_status(created["task_id"]))

        self.assertTrue(created["success"])
        self.assertEqual(status["task"]["status"], "completed")
        self.assertIn("real agent result for: audit tools", status["task"]["result"])


if __name__ == "__main__":
    unittest.main()
