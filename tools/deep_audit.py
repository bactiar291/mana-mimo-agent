#!/usr/bin/env python3
"""Deep MiMo tool scenario audit.

Executes light/medium/hard scenarios for tools where safe execution is possible.
Destructive/write tools are run only inside a temp fixture. External/credential/chat
side-effect tools are classified as skipped with a concrete reason instead of being
called against real services.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.audit_harness import classify_tool, prepare_fixture
from tools.tools import TOOLS, call_tool, get_tools_schema

ROOT = PROJECT_ROOT

EXTERNAL_SKIP_REASONS = {
    "notify_telegram": "would send real Telegram message/token-dependent",
    "notify_discord": "requires real Discord webhook",
    "notify_slack": "requires real Slack webhook",
    "text_to_speech": "may call external TTS/network and create media",
    "voice_tts": "may call external TTS/network and create media",
    "voice_transcribe": "requires real audio/STT engine",
    "voice_info": "requires real audio fixture beyond registry smoke",
    "vision_analyze": "vision description requires external model; covered by honesty tests",
    "vision_screenshot": "browser/network screenshot; covered by browser class smoke separately",
    "vision_ocr": "requires OCR binary/image fixture; covered by honesty tests",
    "vision_compare": "requires image fixtures; low value for live smoke",
    "video_analyze": "requires video fixture/ffprobe",
    "webhook_create": "opens listener port",
    "webhook_start": "opens listener port",
    "webhook_stop": "stops listener state",
    "webhook_log": "requires existing webhook id",
    "webhook_delete": "requires existing webhook id and mutates registry",
    "mcp_server": "requires MCP server lifecycle",
    "mcp_tools": "requires configured MCP server",
    "mcp_call": "requires configured MCP server",
    "mcp_test": "requires configured MCP server",
    "mcp_reload": "requires configured MCP server",
    "credential_test": "requires configured credential",
    "credential_rotate": "requires configured credential pool",
    "credential_export": "exports secret material; intentionally not run",
    "skill_install": "network/file install side-effect; covered by unit test with file://",
    "skill_auto_load": "depends on user skill corpus; smoke list covers skill manager",
    "plugin_reload": "requires plugin id",
    "channel_route": "depends on configured channels",
    "channel_broadcast": "would send outbound messages",
    "event_listen": "registers callback side-effect",
    "event_emit": "emits event to callbacks",
    "event_chain": "requires event chain definition",
    "event_replay": "requires chain id",
    "browser_click": "requires specific live page selector",
    "browser_type": "requires specific live page selector",
    "browser_press": "requires active page focus",
    "browser_scroll": "requires active page; included in browser integration if enabled",
    "browser_snapshot": "requires active page; included in browser integration if enabled",
    "browser_console": "requires active page; included in browser integration if enabled",
    "nodriver_open": "starts real browser engine; optional heavy integration",
    "nodriver_screenshot": "requires active nodriver page",
    "nodriver_click": "requires active nodriver page",
    "nodriver_type": "requires active nodriver page",
}


def jload(raw: Any) -> Any:
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {"raw": raw[:1000]}
    return raw


def is_error(payload: Any) -> bool:
    return isinstance(payload, dict) and bool(payload.get("error") or payload.get("success") is False)


def run_call(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    try:
        payload = jload(call_tool(tool, args))
        status = "error" if is_error(payload) else "ok"
    except Exception as exc:
        payload = {"error": repr(exc)}
        status = "exception"
    return {
        "tool": tool,
        "status": status,
        "duration_ms": int((time.time() - start) * 1000),
        "args": args,
        "summary": json.dumps(payload, ensure_ascii=False, default=str)[:500],
    }


def fixture_paths(tmp: Path) -> Dict[str, str]:
    f = prepare_fixture(tmp)
    (tmp / "old.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    (tmp / "new.txt").write_text("alpha\nBETA\ngamma\n", encoding="utf-8")
    return f


def scenarios_for(tool: str, fixture: Dict[str, str], tmp: Path) -> List[Dict[str, Any]]:
    root = fixture["root"]
    text = fixture["text"]
    data = fixture["json"]
    csv = fixture["csv"]
    db = fixture["db"]
    scenarios: Dict[str, List[Dict[str, Any]]] = {
        "web_search": [{"query": "example domain", "limit": 1}, {"query": "python", "limit": 2}],
        "search_engine_status": [{}],
        "search_engine_set": [{"engine": "duckduckgo"}, {"engine": "wikipedia"}, {"engine": "duckduckgo"}],
        "web_extract": [{"url": "https://example.com", "max_chars": 1000}],
        "http_request": [{"method": "GET", "url": "https://example.com", "timeout": 10}],
        "download_file": [{"url": "https://example.com", "path": str(tmp / "download.html"), "overwrite": True, "timeout": 15}],
        "read_file": [{"path": text, "limit": 2}, {"path": text, "offset": 2, "limit": 2}],
        "write_file": [{"path": str(tmp / "write.txt"), "content": "hello"}],
        "patch_file": [{"path": text, "old_string": "old", "new_string": "new"}],
        "search_files": [{"pattern": "MiMo", "path": root, "target": "content", "limit": 5}, {"pattern": "*.txt", "path": root, "target": "files", "limit": 5}],
        "terminal": [{"command": "true", "timeout": 5, "workdir": root}, {"command": "printf ok", "timeout": 5, "workdir": root}],
        "list_directory": [{"path": root}, {"path": root, "show_hidden": True}],
        "execute_python": [{"code": "print('ok')", "timeout": 5}, {"code": "print(sum(range(10)))", "timeout": 5}],
        "file_info": [{"path": text}, {"path": text, "hash_file": True}, {"path": root}],
        "append_file": [{"path": str(tmp / "append.txt"), "content": "line"}],
        "create_directory": [{"path": str(tmp / "created_dir")}],
        "copy_path": [{"source": text, "destination": str(tmp / "copy.txt"), "overwrite": True}],
        "move_path": [{"source": str(tmp / "move_source.txt"), "destination": str(tmp / "move_dest.txt"), "overwrite": True}],
        "move_to_trash": [{"path": str(tmp / "trashme.txt")}],
        "find_files": [{"pattern": "*.txt", "path": root, "limit": 5}],
        "list_tree": [{"path": root, "max_depth": 2, "limit": 50}],
        "replace_in_file": [{"path": text, "pattern": "hello", "replacement": "hi", "max_replacements": 1}],
        "text_diff": [{"old_path": str(tmp / "old.txt"), "new_path": str(tmp / "new.txt")}, {"old_path": text, "new_content": "different\n"}],
        "code_outline": [{"path": str(ROOT / "core/main.py"), "limit": 20}],
        "project_map": [{"path": root, "max_depth": 2}],
        "read_json": [{"path": data}],
        "write_json": [{"path": str(tmp / "write.json"), "data": {"x": 1}}],
        "json_query": [{"path": data, "key_path": "a.b"}],
        "csv_preview": [{"path": csv, "limit": 2}],
        "sqlite_query": [{"db_path": db, "query": "select * from t", "limit": 5}, {"db_path": db, "query": "insert into t values (2)", "allow_write": True}],
        "create_archive": [{"source": str(Path(root) / "dir"), "destination": str(tmp / "archive.tar.gz"), "overwrite": True}],
        "extract_archive": [{"path": str(tmp / "archive.tar.gz"), "destination": str(tmp / "extract"), "overwrite": True}],
        "git_status": [{"path": str(ROOT)}],
        "git_diff": [{"path": str(ROOT), "limit": 1000}],
        "git_log": [{"path": str(ROOT), "limit": 2}],
        "git_show": [{"path": str(ROOT), "ref": "HEAD", "limit": 1000}],
        "current_time": [{}],
        "system_info": [{}],
        "disk_usage": [{"path": root}],
        "process_list": [{"limit": 2}, {"filter": "start_tg", "limit": 5}],
        "process_kill": [{"pid": 99999999}],
        "task_board": [{"action": "list", "path": str(tmp / "todo.json")}, {"action": "add", "item": "audit", "path": str(tmp / "todo.json")}],
        "browser_status": [{}],
        "browser_close": [{}],
        "skills_list": [{}],
        "skill_view": [{"name": "missing"}],
        "skill_manage": [{"action": "list"}],
        "memory": [{"action": "list"}],
        "todo": [{"action": "list"}],
        "get_tool_stats": [{}],
        "get_best_pattern": [{"task_type": "missing"}],
        "get_error_fix": [{"error_type": "missing"}],
        "get_upgrade_history": [{}],
        "get_learning_summary": [{}],
        "supervisor_status": [{}],
        "session_search": [{}],
        "voice_list": [{}],
        "webhook_list": [{}],
        "memory_enhanced": [{"action": "list"}],
        "memory_profile": [{"action": "list"}],
        "memory_environment": [{"action": "list"}],
        "memory_facts": [{"action": "list"}],
        "memory_preferences": [{"action": "list"}],
        "thinking_list": [{}],
        "notify_email": [{"to": "a@example.com", "subject": "smoke", "body": "body"}],
        "notify_sms": [{"phone": "+100****0000", "message": "body"}],
        "session_create": [{"title": "audit", "source": "deep"}],
        "session_list": [{}],
        "cron_list": [{}],
        "delegate_status": [{}],
        "skill_scan": [{}],
        "channel_list": [{}],
        "channel_status": [{"channel_id": "missing"}],
        "auto_improve_status": [{}],
        "event_list": [{}],
        "plugin_list": [{}],
        "plugin_info": [{"plugin_id": "missing"}],
        "context_summarize": [{"text": "hello world " * 50, "max_length": 80}],
        "token_count": [{"text": "hello world"}],
        "credential_list": [{}],
        "kanban_list": [{}],
        "mcp_list": [{}],
        "mcp_call": [{"server_name": "missing", "tool_name": "noop", "arguments": {}}],
        "sandbox_execute": [{"code": "print('ok')", "timeout": 5}],
        "checkpoint_list": [{}],
        "workspace_list": [{}],
        "workspace_status": [{}],
        "security_check_command": [{"command": "ls"}, {"command": "rm -rf /root/mimo-agent"}],
        "security_check_path": [{"path": root}, {"path": "/root/mimo-agent"}],
        "nodriver_close": [{}],
    }
    if tool == "move_path":
        Path(tmp / "move_source.txt").write_text("move", encoding="utf-8")
    if tool == "move_to_trash":
        Path(tmp / "trashme.txt").write_text("trash", encoding="utf-8")
    if tool == "extract_archive":
        call_tool("create_archive", scenarios["create_archive"][0])
    return scenarios.get(tool, [])


EXPECTED_ERROR_TOOLS = {
    "skill_view", "process_kill", "notify_email", "notify_sms", "skill_scan",
    "mcp_call", "credential_test", "channel_status", "plugin_info",
}


AGENT_LOOP_SCENARIOS = [
    {
        "name": "light_final_answer",
        "streams": [[("answer", "Halo, siap.")]],
        "prompt": "hai",
        "expect": "Halo, siap.",
        "max_tool_calls": 5,
    },
    {
        "name": "medium_tool_then_final",
        "streams": [[("answer", '{"tool":"current_time","args":{}}')], [("answer", "Jam sudah dicek.")]],
        "prompt": "jam berapa",
        "expect": "Jam sudah dicek.",
        "max_tool_calls": 5,
    },
    {
        "name": "hard_multi_tool_loop",
        "streams": [
            [("answer", '{"tool":"execute_python","args":{"code":"print(1)"}}')],
            [("answer", '{"tool":"execute_python","args":{"code":"print(2)"}}')],
            [("answer", '{"tool":"execute_python","args":{"code":"print(3)"}}')],
            [("answer", "Loop tool calling sukses.")],
        ],
        "prompt": "debug coding multi step",
        "expect": "Loop tool calling sukses.",
        "max_tool_calls": 0,
    },
    {
        "name": "coding_task_tool_loop",
        "streams": [
            [("answer", '{"tool":"write_file","args":{"path":"/tmp/mimo_agent_loop_test.py","content":"print(123)"}}')],
            [("answer", '{"tool":"terminal","args":{"command":"python3 /tmp/mimo_agent_loop_test.py","timeout":10}}')],
            [("answer", "Coding task verified.")],
        ],
        "prompt": "buat dan test script python ringan",
        "expect": "Coding task verified.",
        "max_tool_calls": 5,
    },
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


def run_agent_loop_scenarios() -> List[Dict[str, Any]]:
    from unittest.mock import patch
    from core.agent import MiMoAgent

    results = []
    for scenario in AGENT_LOOP_SCENARIOS:
        fake = FakeMiMoClient(scenario["streams"])
        with patch("core.agent.MiMoClient", return_value=fake):
            agent = MiMoAgent(quiet=True, max_tool_calls=scenario["max_tool_calls"])
        start = time.time()
        try:
            answer = agent.chat_stream(scenario["prompt"])
            ok = scenario["expect"] in answer
            results.append({
                "name": scenario["name"],
                "status": "ok" if ok else "error",
                "duration_ms": int((time.time() - start) * 1000),
                "summary": answer[:500],
            })
        except Exception as exc:
            results.append({
                "name": scenario["name"],
                "status": "exception",
                "duration_ms": int((time.time() - start) * 1000),
                "summary": repr(exc),
            })
    return results


def run_deep_audit(include_browser: bool = False) -> Dict[str, Any]:
    tool_results = []
    with tempfile.TemporaryDirectory(prefix="mimo_deep_audit_") as tmp_s:
        tmp = Path(tmp_s)
        fixture = fixture_paths(tmp)
        for tool in sorted(TOOLS):
            scenario_args = scenarios_for(tool, fixture, tmp)
            if not scenario_args:
                reason = EXTERNAL_SKIP_REASONS.get(tool) or classify_tool(tool)
                tool_results.append({"tool": tool, "scenario": "skip", "status": "skipped", "summary": reason})
                continue
            for idx, args in enumerate(scenario_args, start=1):
                level = "light" if idx == 1 else "medium" if idx == 2 else "hard"
                result = run_call(tool, args)
                if result["status"] == "error" and tool in EXPECTED_ERROR_TOOLS:
                    result["status"] = "expected_error_ok"
                result["scenario"] = level
                tool_results.append(result)

        if include_browser:
            browser_sequence = [
                ("browser_open", {"url": "https://example.com", "wait": 3}),
                ("browser_get_text", {}),
                ("browser_get_links", {}),
                ("browser_screenshot", {"path": str(tmp / "browser.png")}),
                ("browser_close", {}),
            ]
            for idx, (tool, args) in enumerate(browser_sequence, start=1):
                result = run_call(tool, args)
                result["scenario"] = f"browser_{idx}"
                tool_results.append(result)

    agent_results = run_agent_loop_scenarios()
    status_counts = Counter(item["status"] for item in tool_results)
    agent_counts = Counter(item["status"] for item in agent_results)
    failures = [r for r in tool_results if r["status"] in {"error", "exception"}]
    agent_failures = [r for r in agent_results if r["status"] in {"error", "exception"}]
    return {
        "registered_tools": len(TOOLS),
        "schema_tools": len(get_tools_schema()),
        "tool_status_counts": dict(status_counts),
        "agent_status_counts": dict(agent_counts),
        "tool_failures": failures,
        "agent_failures": agent_failures,
        "tool_results": tool_results,
        "agent_results": agent_results,
        "passed": not failures and not agent_failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deep MiMo tool and agent-loop scenarios")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--browser", action="store_true", help="Include heavier live browser smoke sequence")
    args = parser.parse_args()
    report = run_deep_audit(include_browser=args.browser)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"registered_tools={report['registered_tools']} schema_tools={report['schema_tools']}")
        print(f"passed={report['passed']}")
        print(f"tool_status_counts={report['tool_status_counts']}")
        print(f"agent_status_counts={report['agent_status_counts']}")
        print(f"tool_failures={len(report['tool_failures'])}")
        print(f"agent_failures={len(report['agent_failures'])}")
        for item in report["tool_failures"][:50]:
            print(f"TOOL_FAIL {item['tool']} {item.get('scenario')}: {item['summary']}")
        for item in report["agent_failures"][:20]:
            print(f"AGENT_FAIL {item['name']}: {item['summary']}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
