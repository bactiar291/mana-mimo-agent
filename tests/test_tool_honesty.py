import json
import os
import tempfile
import unittest
from unittest.mock import patch

from tools import event_system, mcp_client, notification, security, skill_manager, vision, voice


class ToolHonestyTest(unittest.TestCase):
    def test_vision_analyze_describe_requires_real_vision_engine(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as image:
            image.write(b"not really a png")
            image.flush()

            result = json.loads(vision.vision_analyze(image_path=image.name, question="Describe this image"))

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "not_implemented")
        self.assertIn("metadata", result)

    def test_vision_analyze_metadata_can_succeed(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as image:
            image.write(b"not really a png")
            image.flush()

            result = json.loads(vision.vision_analyze(image_path=image.name, question="metadata"))

        self.assertTrue(result["success"])
        self.assertEqual(result["analysis_type"], "metadata")
        self.assertEqual(result["file"], image.name)

    def test_vision_ocr_without_tesseract_fails_honestly(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as image, patch("tools.vision.shutil.which", return_value=None):
            image.write(b"not really a png")
            image.flush()

            result = json.loads(vision.vision_ocr(image.name))

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "not_implemented")
        self.assertIn("metadata", result)

    def test_voice_transcribe_without_whisper_fails_honestly(self):
        with tempfile.NamedTemporaryFile(suffix=".mp3") as audio, patch("tools.voice.shutil.which", return_value=None):
            audio.write(b"not really audio")
            audio.flush()

            result = json.loads(voice.voice_transcribe(audio.name))

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "not_implemented")
        self.assertIn("metadata", result)

    def test_voice_registration_can_be_disabled(self):
        calls = []

        with patch.dict(os.environ, {"MIMO_VOICE_ENABLED": "0"}):
            count = voice.register_voice_tools(lambda **kwargs: calls.append(kwargs))

        self.assertEqual(count, 0)
        self.assertEqual(calls, [])

    def test_email_and_sms_do_not_fake_queue_success(self):
        email = json.loads(notification.notify_email("a@example.com", "subject", "body"))
        sms = json.loads(notification.notify_sms("+10000000000", "hello"))

        self.assertFalse(email["success"])
        self.assertEqual(email["reason"], "not_implemented")
        self.assertFalse(sms["success"])
        self.assertEqual(sms["reason"], "not_implemented")

    def test_mcp_call_without_transport_fails_honestly(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch("tools.mcp_client.MCP_DIR", tmpdir):
            with open(os.path.join(tmpdir, "local.json"), "w", encoding="utf-8") as handle:
                json.dump({"name": "local", "url": "http://localhost:9999"}, handle)

            result = json.loads(mcp_client.mcp_call("local", "echo", {"value": 1}))

        self.assertFalse(result["success"])
        self.assertEqual(result["reason"], "not_implemented")

    def test_skill_install_from_file_url_writes_skill(self):
        with tempfile.TemporaryDirectory() as source_dir, tempfile.TemporaryDirectory() as skills_dir, patch(
            "tools.skill_manager.SKILLS_DIR", skills_dir
        ):
            source_path = os.path.join(source_dir, "demo.md")
            with open(source_path, "w", encoding="utf-8") as handle:
                handle.write("# Demo\n\nDo something useful.\n")

            result = json.loads(skill_manager.skill_install(f"file://{source_path}", "demo skill"))

            installed_path = os.path.join(skills_dir, "demo_skill.md")
            self.assertTrue(result["success"])
            self.assertEqual(result["path"], installed_path)
            self.assertTrue(os.path.isfile(installed_path))

    def test_event_listen_and_emit_register_delivery(self):
        with tempfile.TemporaryDirectory() as events_dir, tempfile.TemporaryDirectory() as listeners_dir, patch(
            "tools.event_system.EVENTS_DIR", events_dir
        ), patch("tools.event_system.LISTENERS_DIR", listeners_dir):
            listen = json.loads(event_system.event_listen("build.done", "noop"))
            emitted = json.loads(event_system.event_emit("build.done", {"ok": True}))

        self.assertTrue(listen["success"])
        self.assertTrue(emitted["success"])
        self.assertEqual(emitted["listeners_notified"], 1)

    def test_security_set_mode_changes_state_and_validates(self):
        original_mode = security.get_approval_system().mode
        try:
            changed = security.set_approval_mode("telegram")
            invalid = security.set_approval_mode("invalid")

            self.assertTrue(changed["success"])
            self.assertEqual(security.get_approval_system().mode, "telegram")
            self.assertFalse(invalid["success"])
            self.assertEqual(security.get_approval_system().mode, "telegram")
        finally:
            security.set_approval_mode(original_mode)


if __name__ == "__main__":
    unittest.main()
