import json
import os
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from tools import channel_router, credential_pool, mcp_client, webhooks


FAKE_MCP_SERVER = r'''
import json
import sys


def read_message():
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = sys.stdin.buffer.read(1)
        if not chunk:
            return None
        header += chunk
    headers = header.decode().split("\r\n")
    length = 0
    for line in headers:
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode())


def send_message(payload):
    data = json.dumps(payload).encode()
    sys.stdout.buffer.write(f"Content-Length: {len(data)}\r\n\r\n".encode() + data)
    sys.stdout.buffer.flush()

while True:
    msg = read_message()
    if msg is None:
        break
    method = msg.get("method")
    msg_id = msg.get("id")
    if method == "initialize":
        send_message({"jsonrpc": "2.0", "id": msg_id, "result": {"protocolVersion": "2024-11-05", "serverInfo": {"name": "fake", "version": "1"}, "capabilities": {"tools": {}}}})
    elif method == "notifications/initialized":
        continue
    elif method == "tools/list":
        send_message({"jsonrpc": "2.0", "id": msg_id, "result": {"tools": [{"name": "echo", "description": "Echo text", "inputSchema": {"type": "object"}}]}})
    elif method == "tools/call":
        args = msg.get("params", {}).get("arguments", {})
        send_message({"jsonrpc": "2.0", "id": msg_id, "result": {"content": [{"type": "text", "text": args.get("text", "")}], "isError": False}})
    else:
        send_message({"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": "unknown method"}})
'''


class LocalExternalToolsTest(unittest.TestCase):
    def test_mcp_command_transport_lists_and_calls_fake_server(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            server_path = os.path.join(tmpdir, "fake_mcp.py")
            with open(server_path, "w", encoding="utf-8") as handle:
                handle.write(FAKE_MCP_SERVER)
            command = f"{sys.executable} {server_path}"

            with patch("tools.mcp_client.MCP_DIR", tmpdir):
                add = json.loads(mcp_client.mcp_server("add", name="local", command=command))
                listed = json.loads(mcp_client.mcp_tools("local"))
                called = json.loads(mcp_client.mcp_call("local", "echo", {"text": "hello"}))
                tested = json.loads(mcp_client.mcp_test("local"))

        self.assertTrue(add["success"])
        self.assertTrue(listed["success"])
        self.assertEqual(listed["tools"][0]["name"], "echo")
        self.assertTrue(called["success"])
        self.assertEqual(called["result"]["content"][0]["text"], "hello")
        self.assertTrue(tested["success"])

    def test_credential_pool_rotation_and_redaction(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch("tools.credential_pool.CREDENTIALS_DIR", tmpdir):
            add = json.loads(credential_pool.credential_add("main", "demo", "SECRETKEY123456", "SECRET2"))
            listed = json.loads(credential_pool.credential_list("demo"))
            rotated = json.loads(credential_pool.credential_rotate("demo"))
            tested = json.loads(credential_pool.credential_test(add["credential_id"]))
            removed = json.loads(credential_pool.credential_remove(add["credential_id"]))

        self.assertTrue(add["success"])
        self.assertEqual(listed["count"], 1)
        self.assertEqual(listed["credentials"][0]["key"], "SECRETKE...")
        self.assertTrue(rotated["success"])
        self.assertEqual(rotated["usage_count"], 1)
        self.assertTrue(tested["success"])
        self.assertTrue(removed["success"])

    def test_channel_router_local_add_route_status_remove(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch("tools.channel_router.CHANNELS_DIR", tmpdir):
            add = json.loads(channel_router.channel_add("home", "telegram", '{"chat_id":"1"}'))
            status = json.loads(channel_router.channel_status(add["channel_id"]))
            routed = json.loads(channel_router.channel_route("hello", "telegram"))
            removed = json.loads(channel_router.channel_remove(add["channel_id"]))

        self.assertTrue(add["success"])
        self.assertTrue(status["success"])
        self.assertEqual(routed["routed_to"], add["channel_id"])
        self.assertTrue(removed["success"])

    def test_webhook_local_create_log_delete_without_opening_port(self):
        with tempfile.TemporaryDirectory() as tmpdir, patch("tools.webhooks.WEBHOOKS_DIR", tmpdir):
            created = json.loads(webhooks.webhook_create("demo", port=18080))
            log_path = os.path.join(tmpdir, f"{created['webhook_id']}.log")
            with open(log_path, "w", encoding="utf-8") as handle:
                handle.write("2026-01-01T00:00:00 - {\"ok\": true}\n")
            logs = json.loads(webhooks.webhook_log(created["webhook_id"]))
            deleted = json.loads(webhooks.webhook_delete(created["webhook_id"]))

        self.assertTrue(created["success"])
        self.assertTrue(logs["success"])
        self.assertIn("ok", logs["logs"][0])
        self.assertTrue(deleted["success"])


if __name__ == "__main__":
    unittest.main()
