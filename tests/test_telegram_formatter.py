import unittest
from unittest.mock import patch

from start_tg import MiMoTelegramBot


class FakeMessage:
    def __init__(self):
        self.replies = []
        self.edits = []

    async def reply_text(self, text, **kwargs):
        self.replies.append((text, kwargs))
        return FakeSentMessage(self)


class FakeSentMessage:
    """What Telegram hands back after reply_text — editable in place."""

    def __init__(self, origin: "FakeMessage"):
        self._origin = origin
        self.deleted = False

    async def edit_text(self, text, **kwargs):
        self._origin.edits.append(text)

    async def delete(self):
        self.deleted = True


class FakeChat:
    id = 123456


class FakeUpdate:
    def __init__(self):
        self.message = FakeMessage()
        self.effective_chat = FakeChat()


class FakeBot:
    async def send_chat_action(self, **kwargs):
        return None


class FakeContext:
    bot = FakeBot()


class TelegramFormatterSmokeTest(unittest.TestCase):
    def setUp(self):
        self.bot = MiMoTelegramBot(token="test-token", owner_chat_id="123456")

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

        self.assertIn("✅ 🌐 Searching web OK (1.2s): Ditemukan hasil yang relevan", tool_result)
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
        help_text = self.bot._help_text(tool_count=72)

        self.assertIn("Tools: 72", help_text)
        self.assertIn("/delegate", help_text)
        self.assertIn("/tools", help_text)
        self.assertIn("Yang benar-benar jalan", help_text)
        self.assertIn("profil:", help_text)

    def test_help_text_does_not_advertise_unimplemented_capabilities(self):
        help_text = self.bot._help_text(tool_count=72)

        # These were advertised while the underlying tools returned not_implemented.
        for overclaim in ("MCP", "webhooks", "Cron", "checkpoints"):
            self.assertNotIn(overclaim, help_text)

    def test_status_text_includes_tool_breakdown(self):
        status_text = self.bot._status_text(tool_count=72, audit_summary={
            "safe_smoke": 58,
            "external_or_stateful": 55,
            "destructive_or_write": 71,
            "expected_failure": 9,
        })

        self.assertIn("Tools: 72", status_text)
        self.assertIn("Safe smoke: 58", status_text)
        self.assertIn("Profil tool:", status_text)
        self.assertIn("Subagents: 0", status_text)

    def test_process_caption_shows_real_current_step_and_recent_tool_trace(self):
        events = [
            {"event": "planning", "detail": "Membangun prompt, memory, dan tool context"},
            {"event": "tool_scope", "detail": "Tool aktif: read_file, write_file, terminal, browser_open"},
            {"event": "budget", "detail": "Tool budget task ini runtime-only"},
            {"event": "model_start", "detail": "MiMo sedang menentukan langkah berikutnya"},
            {"event": "tool_start", "tool": "read_file", "detail": "/root/mimo-agent/core/agent.py L10-40"},
        ]

        with patch("start_tg.time.monotonic", return_value=120.0):
            caption = self.bot._process_caption(events, started=110.0, idle=0.0)

        self.assertIn("MiMo Agent • LIVE", caption)
        self.assertIn("10s", caption)
        self.assertIn("Sekarang", caption)
        self.assertIn("Timeline", caption)
        self.assertIn("📖 Reading agent.py L10-40", caption)

    def test_process_caption_hides_timeline_before_first_real_action(self):
        """No placeholder text: the timeline only appears once real work happened."""
        events = [
            {"event": "planning", "detail": "Membangun prompt"},
            {"event": "model_start", "detail": "MiMo sedang berpikir"},
        ]

        with patch("start_tg.time.monotonic", return_value=120.0):
            caption = self.bot._process_caption(events, started=110.0, idle=0.0)

        self.assertIn("🧠", caption)
        self.assertNotIn("Timeline", caption)
        self.assertNotIn("Menunggu event eksekusi pertama", caption)

    def test_process_caption_collapses_repeated_actions(self):
        events = [
            {"event": "tool_start", "tool": "patch_file", "detail": "/root/mimo-agent/core/agent.py"},
            {"event": "tool_start", "tool": "patch_file", "detail": "/root/mimo-agent/core/agent.py"},
            {"event": "tool_start", "tool": "patch_file", "detail": "/root/mimo-agent/core/agent.py"},
        ]

        with patch("start_tg.time.monotonic", return_value=120.0):
            caption = self.bot._process_caption(events, started=110.0, idle=0.0)

        self.assertIn("🔧 Editing agent.py (×3)", caption)
        self.assertIn("Timeline (3 aksi)", caption)

    def test_process_caption_exposes_safe_tool_command_and_result(self):
        events = [
            {"event": "planning", "detail": "Membangun prompt"},
            {"event": "tool_start", "tool": "terminal", "detail": "curl -H 'Authorization: Bearer ***' https://example.test/?token=abc"},
            {"event": "tool_result", "tool": "terminal", "status": "ok", "duration": 1.25, "detail": "exit 0 checked config"},
            {"event": "tool_start", "tool": "read_file", "detail": "/root/mimo-agent/core/agent.py"},
        ]

        with patch("start_tg.time.monotonic", return_value=120.0):
            caption = self.bot._process_caption(events, started=110.0, idle=0.0)

        self.assertIn("💻 Running terminal", caption)
        self.assertIn("📖 Reading agent.py", caption)
        self.assertIn("[REDACTED]", caption)
        self.assertNotIn("secret-value", caption)
        self.assertNotIn("token=abc", caption)

    def test_process_caption_uses_hermes_style_activity_labels(self):
        events = [
            {"event": "tool_start", "tool": "skill_view", "detail": "mimo-agent-architecture"},
            {"event": "tool_start", "tool": "search_files", "detail": "progress in /root/mimo-agent"},
            {"event": "tool_start", "tool": "todo", "detail": "3 tasks"},
            {"event": "tool_start", "tool": "read_file", "detail": "/root/mimo-agent/start_tg.py L480-1049"},
        ]

        with patch("start_tg.time.monotonic", return_value=120.0):
            caption = self.bot._process_caption(events, started=110.0, idle=0.0)

        self.assertIn("📚 Reading skill mimo-agent-architecture", caption)
        self.assertIn("🔎 Searching files in /root/mimo-agent", caption)
        self.assertIn("📋 Updating tasks", caption)
        self.assertIn("📖 Reading start_tg.py L480-1049", caption)

    def test_progress_messages_emit_each_real_tool_step_separately(self):
        start = self.bot._progress_message_for_event(
            {"event": "tool_start", "tool": "read_file", "detail": "/root/mimo-agent/core/agent.py"}
        )
        result = self.bot._progress_message_for_event(
            {
                "event": "tool_result",
                "tool": "read_file",
                "status": "ok",
                "duration": 0.4,
                "detail": "218 lines read",
            }
        )

        self.assertEqual("📖 Reading agent.py", start)
        self.assertEqual("✅ 📖 Reading file OK (0.4s): 218 lines read", result)
        self.assertIsNone(self.bot._progress_message_for_event({"event": "planning", "detail": "context"}))
        self.assertIsNone(self.bot._progress_message_for_event({"event": "model_start", "detail": "thinking"}))

    def test_process_caption_redacts_sensitive_search_and_browser_details(self):
        events = [
            {"event": "tool_start", "tool": "web_search", "detail": "private research password=secret-value"},
            {"event": "tool_start", "tool": "browser_open", "detail": "https://example.test/private?token=abc"},
        ]

        with patch("start_tg.time.monotonic", return_value=120.0):
            caption = self.bot._process_caption(events, started=110.0, idle=0.0)

        self.assertIn("🌐 Searching web", caption)
        self.assertIn("🌐 Opening example.test", caption)
        self.assertNotIn("private research", caption)
        self.assertNotIn("secret-value", caption)
        self.assertNotIn("token=abc", caption)
        self.assertNotIn("/private", caption)


class TelegramProgressFeedSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MiMoTelegramBot(token="test-token", owner_chat_id="123456")

    async def test_process_feed_uses_one_live_message_with_real_steps(self):
        update = FakeUpdate()
        stop_event = __import__("asyncio").Event()
        stop_event.set()
        progress_queue = __import__("queue").Queue()
        progress_queue.put({"event": "planning", "detail": "hidden"})
        progress_queue.put({"event": "tool_start", "tool": "read_file", "detail": "/root/a.py"})
        progress_queue.put({"event": "tool_result", "tool": "read_file", "status": "ok", "duration": 0.2, "detail": "done"})
        progress_queue.put({"event": "tool_start", "tool": "terminal", "detail": "echo hidden"})

        status_message = await self.bot._process_feed(update, FakeContext(), progress_queue, stop_event)

        # Exactly one status message is created, not one message per event.
        self.assertEqual(len(update.message.replies), 1)
        self.assertIsNotNone(status_message)

        caption = update.message.replies[0][0]
        self.assertIn("MiMo Agent • LIVE", caption)
        # The live card reports the newest real step and keeps earlier ones in the timeline.
        self.assertIn("💻 Running terminal", caption)
        self.assertIn("📖 Reading /root/a.py", caption)
        self.assertIn("Timeline", caption)

    async def test_process_feed_returns_message_that_can_be_deleted(self):
        update = FakeUpdate()
        stop_event = __import__("asyncio").Event()
        stop_event.set()
        progress_queue = __import__("queue").Queue()
        progress_queue.put({"event": "tool_start", "tool": "read_file", "detail": "/root/a.py"})

        status_message = await self.bot._process_feed(update, FakeContext(), progress_queue, stop_event)
        await status_message.delete()

        self.assertTrue(status_message.deleted)


class TelegramFinalFallbackSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MiMoTelegramBot(token="test-token", owner_chat_id="123456")

    async def test_empty_final_uses_fallback_response(self):
        update = FakeUpdate()

        await self.bot._send_response(update, "")

        self.assertEqual(len(update.message.replies), 1)
        reply_text, kwargs = update.message.replies[0]
        self.assertIn("agent tidak menghasilkan teks jawaban", reply_text)
        self.assertEqual(kwargs, {})


if __name__ == "__main__":
    unittest.main()
