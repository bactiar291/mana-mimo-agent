import unittest
from unittest.mock import patch

from start_tg import MiMoTelegramBot


class FakeMessage:
    def __init__(self):
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))


class FakeUpdate:
    def __init__(self):
        self.message = FakeMessage()


class TelegramFormatterSmokeTest(unittest.TestCase):
    def setUp(self):
        self.bot = MiMoTelegramBot(token="test-token", chat_id="123456")

    def test_format_event_line_covers_core_event_types(self):
        tool_result = self.bot._format_event_line(
            {
                "event": "tool_result",
                "tool": "web_search",
                "status": "ok",
                "duration": 1.234,
                "detail": "Ditemukan hasil yang relevan",
                "next_step": "lanjut ke extract",
            }
        )
        fallback = self.bot._format_event_line(
            {
                "event": "fallback",
                "tool": "browser_open",
                "detail": "Coba browser setelah fetch gagal",
            }
        )
        final = self.bot._format_event_line(
            {
                "event": "final",
                "detail": "Jawaban final siap",
            }
        )
        browser_lifecycle = self.bot._format_event_line(
            {
                "event": "browser_lifecycle",
                "detail": "Browser ditutup",
                "tmp_removed": 3,
            }
        )
        tool_scope = self.bot._format_event_line(
            {
                "event": "tool_scope",
                "detail": "Tool aktif: web_search, web_extract",
            }
        )
        adjusted = self.bot._format_event_line(
            {
                "event": "tool_args_adjusted",
                "tool": "terminal",
                "detail": "timeout 120s -> 35s",
            }
        )

        self.assertIn("✅ web_search OK (1.2s): Ditemukan hasil yang relevan", tool_result)
        self.assertIn("next: lanjut ke extract", tool_result)
        self.assertEqual("↪ Fallback browser_open: Coba browser setelah fetch gagal", fallback)
        self.assertEqual("🏁 Final: Jawaban final siap", final)
        self.assertEqual("🧹 Browser: Browser ditutup (3 tmp)", browser_lifecycle)
        self.assertEqual("🎯 Tools: Tool aktif: web_search, web_extract", tool_scope)
        self.assertEqual("🧯 Guard terminal: timeout 120s -> 35s", adjusted)

    def test_event_stage_maps_core_event_types(self):
        self.assertEqual(self.bot._event_stage({"event": "tool_result", "tool": "web_search"}), "TOOL DONE")
        self.assertEqual(self.bot._event_stage({"event": "fallback", "tool": "browser_open"}), "FALLBACK")
        self.assertEqual(self.bot._event_stage({"event": "final"}), "DONE")
        self.assertEqual(self.bot._event_stage({"event": "browser_lifecycle"}), "BROWSER")
        self.assertEqual(self.bot._event_stage({"event": "tool_scope"}), "PLANNING")
        self.assertEqual(self.bot._event_stage({"event": "tool_args_adjusted"}), "ATTENTION")

    def test_command_menu_exposes_delegate_tools_and_status(self):
        commands = dict(self.bot._telegram_command_specs())

        self.assertIn("delegate", commands)
        self.assertIn("tools", commands)
        self.assertIn("status", commands)
        self.assertIn("tool", commands["status"].lower())

    def test_help_text_lists_features_and_tool_total(self):
        help_text = self.bot._help_text(tool_count=204)

        self.assertIn("Tools: 204", help_text)
        self.assertIn("/delegate", help_text)
        self.assertIn("/tools", help_text)
        self.assertIn("Session search", help_text)
        self.assertIn("MCP", help_text)

    def test_status_text_includes_tool_breakdown(self):
        status_text = self.bot._status_text(tool_count=204, audit_summary={
            "safe_smoke": 69,
            "external_or_stateful": 55,
            "destructive_or_write": 71,
            "expected_failure": 9,
        })

        self.assertIn("Tools: 204", status_text)
        self.assertIn("Safe smoke: 69", status_text)
        self.assertIn("Subagents: 0", status_text)

    def test_process_caption_is_simple_not_verbose_executor_trace(self):
        events = [
            {"event": "planning", "detail": "Membangun prompt, memory, dan tool context"},
            {"event": "tool_scope", "detail": "Tool aktif: read_file, write_file, terminal, browser_open"},
            {"event": "budget", "detail": "Tool budget task ini runtime-only"},
            {"event": "model_start", "detail": "MiMo sedang menentukan langkah berikutnya"},
        ]

        with patch("start_tg.time.monotonic", return_value=120.0):
            caption = self.bot._process_caption(events, started=110.0, idle=0.0)

        self.assertIn("MiMo lagi jalan", caption)
        self.assertIn("10s", caption)
        self.assertNotIn("MiMo Agent Executor", caption)
        self.assertNotIn("Tool aktif", caption)
        self.assertNotIn("runtime-only", caption)
        self.assertNotIn("Membuat rencana", caption)


class TelegramFinalFallbackSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MiMoTelegramBot(token="test-token", chat_id="123456")

    async def test_empty_final_uses_fallback_response(self):
        update = FakeUpdate()

        await self.bot._send_response(update, "")

        self.assertEqual(len(update.message.replies), 1)
        reply_text, kwargs = update.message.replies[0]
        self.assertIn("agent tidak menghasilkan teks jawaban", reply_text)
        self.assertEqual(kwargs, {})


if __name__ == "__main__":
    unittest.main()
