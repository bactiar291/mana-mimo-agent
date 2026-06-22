import json
import unittest

from core.agent import MiMoAgent
from tools import tools


class ToolRegistryCompatibilityTest(unittest.TestCase):
    def test_args_style_handler_receives_full_args_dict(self):
        original = dict(tools.TOOLS)
        try:
            tools.register_tool(
                name="_test_args_style",
                description="test",
                parameters={"type": "object", "properties": {}},
                handler=lambda args: json.dumps({"value": args.get("value")}),
            )

            result = json.loads(tools.call_tool("_test_args_style", {"value": "ok"}))

            self.assertEqual(result["value"], "ok")
        finally:
            tools.TOOLS.clear()
            tools.TOOLS.update(original)

    def test_kwargs_style_handler_still_works(self):
        original = dict(tools.TOOLS)
        try:
            tools.register_tool(
                name="_test_kwargs_style",
                description="test",
                parameters={"type": "object", "properties": {}},
                handler=lambda value="": json.dumps({"value": value}),
            )

            result = json.loads(tools.call_tool("_test_kwargs_style", {"value": "ok"}))

            self.assertEqual(result["value"], "ok")
        finally:
            tools.TOOLS.clear()
            tools.TOOLS.update(original)


class RuntimeOnlyBudgetTest(unittest.TestCase):
    def test_zero_max_tool_calls_means_runtime_only_budget(self):
        agent = MiMoAgent(quiet=True, max_tool_calls=0)

        budget = agent._task_tool_budget("subitin email ke https://example.com")

        self.assertGreaterEqual(budget, 1_000_000)
        self.assertEqual(agent._tool_budget_label(budget), "runtime-only")


if __name__ == "__main__":
    unittest.main()
