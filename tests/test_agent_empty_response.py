import json
import os
import tempfile
import unittest
from unittest.mock import patch

from core.agent import Memory, MiMoAgent


def schema_for(*names):
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": f"{name} test tool",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
        for name in names
    ]


class FakeMiMoClient:
    def __init__(self, streams):
        self.streams = list(streams)
        self.prompts = []

    def chat_stream(self, prompt, web_search=True, enable_thinking=True):
        self.prompts.append(prompt)
        if not self.streams:
            return iter(())
        return iter(self.streams.pop(0))

    def new_conversation(self):
        pass


class AgentEmptyResponseTest(unittest.TestCase):
    def make_agent(self, streams, max_tool_calls=5):
        fake_client = FakeMiMoClient(streams)
        with patch("core.agent.MiMoClient", return_value=fake_client), patch(
            "core.agent.get_tools_schema",
            return_value=schema_for(
                "web_search",
                "web_extract",
                "http_request",
                "terminal",
                "execute_python",
                "read_file",
                "search_files",
                "git_status",
                "sandbox_execute",
                "current_time",
                "browser_open",
                "browser_get_text",
                "browser_click",
                "browser_type",
                "browser_wait_for",
                "browser_evaluate",
                "browser_screenshot",
                "browser_status",
                "browser_close",
                "browser_set_engine",
                "delegate_task",
                "memory",
                "memory_enhanced",
                "memory_facts",
                "memory_preferences",
                "voice_tts",
                "voice_list",
                "voice_transcribe",
                "voice_info",
                "text_to_speech",
            ),
        ):
            agent = MiMoAgent(quiet=True, max_tool_calls=max_tool_calls)
        return agent

    def test_empty_response_without_url_retries_before_final(self):
        agent = self.make_agent([
            [("think", "planning only")],
            [("answer", "Selesai setelah retry")],
        ])
        events = []

        result = agent.chat_stream("jelasin status task ini", progress_callback=events.append)

        self.assertEqual(result, "Selesai setelah retry")
        self.assertTrue(any(event["event"] == "retry" for event in events))
        self.assertTrue(any(event["event"] == "finalizing" for event in events))
        self.assertTrue(any(event["event"] == "final" for event in events))

    def test_empty_response_with_form_url_uses_browser_fallback(self):
        agent = self.make_agent([
            [("think", "planning only")],
            [("answer", "Form berhasil dicek")],
        ])
        events = []
        tool_calls = []

        def fake_call_tool(tool, args):
            tool_calls.append((tool, args))
            return json.dumps({"success": True, "content": "loaded"})

        with patch("core.agent.call_tool", side_effect=fake_call_tool):
            result = agent.chat_stream(
                "subitin email ke https://example.com/form",
                progress_callback=events.append,
            )

        self.assertEqual(result, "Form berhasil dicek")
        self.assertEqual(tool_calls[0], ("browser_open", {"url": "https://example.com/form", "wait": 5}))
        self.assertTrue(any(event["event"] == "fallback" for event in events))
        self.assertTrue(any(event["event"] == "tool_result" for event in events))

    def test_out_of_scope_tool_is_rejected_before_execution(self):
        agent = self.make_agent([
            [("answer", '{"tool": "delegate_task", "args": {"goal": "overkill"}}')],
            [("answer", "Pakai jawaban simpel saja")],
        ])
        events = []
        tool_calls = []

        def fake_call_tool(tool, args):
            tool_calls.append((tool, args))
            return json.dumps({"success": True})

        with patch("core.agent.call_tool", side_effect=fake_call_tool):
            result = agent.chat_stream("jam berapa sekarang?", progress_callback=events.append)

        self.assertEqual(result, "Pakai jawaban simpel saja")
        self.assertEqual(tool_calls, [])
        self.assertTrue(any(event["event"] == "retry" and event.get("tool") == "delegate_task" for event in events))

    def test_memory_tools_are_not_in_default_scope(self):
        agent = self.make_agent([[("answer", "ok")]])

        normal_scope = agent._select_tool_names("jam berapa sekarang?")
        memory_scope = agent._select_tool_names("ingat preferensi gue pakai bahasa indonesia")

        self.assertNotIn("memory", normal_scope)
        self.assertNotIn("memory_enhanced", normal_scope)
        self.assertIn("memory", memory_scope)

    def test_task_budget_never_exceeds_agent_cap(self):
        agent = self.make_agent([[("answer", "ok")]])

        self.assertEqual(agent._task_tool_budget("debug traceback api error"), 5)
        self.assertEqual(agent._task_tool_budget("subitin email ke https://example.com"), 5)
        self.assertEqual(agent._task_tool_budget("hai"), 4)

    def test_repeated_identical_tool_call_is_rejected(self):
        agent = self.make_agent([
            [("answer", '{"tool": "web_search", "args": {"query": "mimo agent", "limit": 3}}')],
            [("answer", '{"tool": "web_search", "args": {"query": "mimo agent", "limit": 3}}')],
            [("answer", "Hasil pertama sudah cukup")],
        ])
        events = []
        tool_calls = []

        def fake_call_tool(tool, args):
            tool_calls.append((tool, args))
            return json.dumps({"results": [{"title": "MiMo Agent", "url": "https://example.com"}]})

        with patch("core.agent.call_tool", side_effect=fake_call_tool):
            result = agent.chat_stream("cari mimo agent", progress_callback=events.append)

        self.assertEqual(result, "Hasil pertama sudah cukup")
        self.assertEqual(len(tool_calls), 1)
        self.assertTrue(
            any(
                event["event"] == "retry"
                and event.get("tool") == "web_search"
                and "sama sudah dipakai" in event.get("detail", "")
                for event in events
            )
        )

    def test_terminal_timeout_is_clamped_before_execution(self):
        agent = self.make_agent([
            [("answer", '{"tool": "terminal", "args": {"command": "sleep 120", "timeout": 120}}')],
            [("answer", "Command terlalu lama, sudah dihentikan cepat")],
        ])
        events = []
        tool_calls = []

        def fake_call_tool(tool, args):
            tool_calls.append((tool, args))
            return json.dumps({"error": f"Command timed out after {args['timeout']}s"})

        with patch("core.agent.call_tool", side_effect=fake_call_tool):
            result = agent.chat_stream("jalanin command terminal sleep", progress_callback=events.append)

        self.assertEqual(result, "Command terlalu lama, sudah dihentikan cepat")
        self.assertEqual(tool_calls[0][1]["timeout"], 35)
        self.assertTrue(
            any(
                event["event"] == "tool_args_adjusted"
                and event.get("tool") == "terminal"
                and "120s -> 35s" in event.get("detail", "")
                for event in events
            )
        )

    def test_explicit_user_preference_is_learned_and_session_is_traced(self):
        agent = self.make_agent([[("answer", "Siap, gue jawab singkat.")]])
        events = []

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "core.agent.LEARNING_LOG", os.path.join(tmpdir, "learning.jsonl")
        ), patch("core.agent.SESSION_TRACE_LOG", os.path.join(tmpdir, "runs.jsonl")):
            agent.memory = Memory(os.path.join(tmpdir, "memory.json"))

            result = agent.chat_stream(
                "jawab indo dan langsung aja",
                progress_callback=events.append,
            )

            self.assertEqual(result, "Siap, gue jawab singkat.")
            self.assertEqual(agent.memory.data["preferences"]["language"], "Indonesian")
            self.assertEqual(agent.memory.data["preferences"]["style"], "direct_concise")
            self.assertTrue(any(event["event"] == "memory" for event in events))
            with open(os.path.join(tmpdir, "runs.jsonl"), "r", encoding="utf-8") as file_handle:
                trace = json.loads(file_handle.readline())
            self.assertEqual(trace["status"], "done")
            self.assertIn("jawab indo", trace["user"])

    def test_recent_agent_lessons_are_included_in_prompt(self):
        agent = self.make_agent([[("answer", "ok")]])

        with tempfile.TemporaryDirectory() as tmpdir, patch(
            "core.agent.LEARNING_LOG", os.path.join(tmpdir, "learning.jsonl")
        ), patch("core.agent.SESSION_TRACE_LOG", os.path.join(tmpdir, "runs.jsonl")):
            agent._record_agent_lesson("tool_args_adjusted", "terminal: timeout 120s -> 35s")

            result = agent.chat_stream("hai")

            self.assertEqual(result, "ok")
            self.assertIn("# RECENT AGENT LESSONS", agent.client.prompts[0])
            self.assertIn("timeout 120s -> 35s", agent.client.prompts[0])

    def test_runtime_only_budget_allows_many_distinct_tool_calls(self):
        streams = [
            [("answer", '{"tool": "execute_python", "args": {"code": "print(0)"}}')],
            [("answer", '{"tool": "execute_python", "args": {"code": "print(1)"}}')],
            [("answer", '{"tool": "execute_python", "args": {"code": "print(2)"}}')],
            [("answer", '{"tool": "execute_python", "args": {"code": "print(3)"}}')],
            [("answer", '{"tool": "execute_python", "args": {"code": "print(4)"}}')],
            [("answer", '{"tool": "execute_python", "args": {"code": "print(5)"}}')],
            [("answer", '{"tool": "execute_python", "args": {"code": "print(6)"}}')],
            [("answer", "Semua step selesai")],
        ]
        agent = self.make_agent(streams, max_tool_calls=0)
        tool_calls = []
        events = []

        def fake_call_tool(tool, args):
            tool_calls.append((tool, args))
            return json.dumps({"output": "ok", "exit_code": 0})

        with patch("core.agent.call_tool", side_effect=fake_call_tool):
            result = agent.chat_stream("debug python multi step", progress_callback=events.append)

        self.assertEqual(result, "Semua step selesai")
        self.assertEqual(len(tool_calls), 7)
        self.assertFalse(any(event["event"] == "max_tool_calls" for event in events))
        self.assertTrue(any(event["event"] == "budget" and "runtime-only" in event["detail"] for event in events))

    def test_voice_tools_require_explicit_audio_intent(self):
        agent = self.make_agent([[("answer", "ok")]])

        complaint_scope = agent._select_tool_names("mimo agent gue kadang ngeluarin suara aneh")
        tts_scope = agent._select_tool_names("buat mp3 dari teks ini pakai tts")
        transcribe_scope = agent._select_tool_names("transcribe audio /tmp/sample.mp3")

        self.assertNotIn("voice_tts", complaint_scope)
        self.assertNotIn("text_to_speech", complaint_scope)
        self.assertIn("voice_tts", tts_scope)
        self.assertIn("text_to_speech", tts_scope)
        self.assertIn("voice_transcribe", transcribe_scope)
        self.assertIn("voice_info", transcribe_scope)

    def test_agent_audit_intent_gets_code_tools_and_no_stale_tool_list(self):
        agent = self.make_agent([[("answer", "ok")]])

        scope = agent._select_tool_names("reaudit mendalam tools agent ini")
        prompt = agent._build_prompt("reaudit mendalam tools agent ini", tool_names=scope)

        self.assertIn("read_file", scope)
        self.assertIn("search_files", scope)
        self.assertIn("git_status", scope)
        self.assertNotIn("AVAILABLE TOOLS (48)", prompt)
        self.assertIn("AVAILABLE TOOLS DETAIL", prompt)


if __name__ == "__main__":
    unittest.main()
