#!/usr/bin/env python3
"""Safe MiMo tool registry audit harness.

Runs structural checks for every registered tool and smoke-tests only tools that
are low-risk and deterministic. Tools that need credentials, browser state,
external services, or destructive side effects are classified but not executed.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tools.tools import TOOLS, call_tool, get_tools_schema

SAFE_SMOKE_ARGS: Dict[str, Dict[str, Any]] = {
    "search_engine_status": {},
    "search_engine_set": {"engine": "duckduckgo"},
    "web_search": {"query": "example domain", "limit": 1},
    "web_extract": {"url": "https://example.com", "max_chars": 2000},
    "read_file": {},
    "search_files": {"pattern": "MiMo", "target": "content", "limit": 5},
    "terminal": {"command": "true", "timeout": 5},
    "list_directory": {},
    "execute_python": {"code": "print('ok')", "timeout": 5},
    "file_info": {},
    "find_files": {"pattern": "*.txt", "limit": 5},
    "list_tree": {"max_depth": 2},
    "text_diff": {"new_content": "different\n"},
    "code_outline": {"path": "core/main.py"},
    "project_map": {"max_depth": 2},
    "read_json": {},
    "json_query": {"key_path": "a.b"},
    "csv_preview": {"limit": 2},
    "sqlite_query": {"query": "select * from t", "limit": 5},
    "http_request": {"method": "GET", "url": "https://example.com", "timeout": 10},
    "git_status": {"path": "/root/mimo-agent"},
    "git_diff": {"path": "/root/mimo-agent", "limit": 1000},
    "git_log": {"path": "/root/mimo-agent", "limit": 1},
    "git_show": {"path": "/root/mimo-agent", "ref": "HEAD", "limit": 1000},
    "current_time": {},
    "system_info": {},
    "disk_usage": {},
    "process_list": {"limit": 2},
    "task_board": {"action": "list"},
    "browser_status": {},
    "browser_close": {},
    "skills_list": {},
    "skill_manage": {"action": "list"},
    "memory": {"action": "list"},
    "todo": {"action": "list"},
    "get_tool_stats": {},
    "get_best_pattern": {"task_type": "missing"},
    "get_error_fix": {"error_type": "missing"},
    "get_upgrade_history": {},
    "get_learning_summary": {},
    "supervisor_status": {},
    "session_search": {},
    "voice_list": {},
    "webhook_list": {},
    "memory_enhanced": {"action": "list"},
    "memory_profile": {"action": "list"},
    "memory_environment": {"action": "list"},
    "memory_facts": {"action": "list"},
    "memory_preferences": {"action": "list"},
    "thinking_list": {},
    "session_list": {},
    "cron_list": {},
    "delegate_status": {},
    "channel_list": {},
    "auto_improve_status": {},
    "event_list": {},
    "plugin_list": {},
    "context_summarize": {"text": "hello world " * 20, "max_length": 50},
    "token_count": {"text": "hello world"},
    "credential_list": {},
    "kanban_list": {},
    "mcp_list": {},
    "sandbox_execute": {"code": "print('ok')", "timeout": 5},
    "checkpoint_list": {},
    "workspace_list": {},
    "workspace_status": {},
    "security_check_command": {"command": "ls"},
    "security_check_path": {},
    "nodriver_close": {},
}

EXPECTED_FAILURE_ARGS: Dict[str, Dict[str, Any]] = {
    "skill_view": {"name": "missing"},
    "process_kill": {"pid": 99999999},
    "notify_email": {"to": "a@example.com", "subject": "smoke", "body": "body"},
    "notify_sms": {"phone": "+100****0000", "message": "body"},
    "skill_scan": {},
    "mcp_call": {"server_name": "missing", "tool_name": "noop", "arguments": {}},
    "credential_test": {"credential_id": "missing"},
    "channel_status": {"channel_id": "missing"},
    "plugin_info": {"plugin_id": "missing"},
}

EXTERNAL_OR_STATE_PREFIXES = (
    "browser_open", "browser_get_text", "browser_get_links", "browser_click",
    "browser_type", "browser_evaluate", "browser_wait_for", "browser_screenshot",
    "browser_set_engine", "browser_press", "browser_scroll", "browser_snapshot",
    "browser_console", "vision_", "video_", "voice_tts", "voice_transcribe",
    "voice_info", "text_to_speech", "notify_telegram", "notify_discord",
    "notify_slack", "webhook_create", "webhook_log", "webhook_start",
    "webhook_stop", "delegate_task", "delegate_batch", "session_export",
    "skill_validate", "skill_export", "skill_import", "channel_route",
    "channel_broadcast", "event_listen", "event_emit", "event_chain",
    "event_replay", "plugin_reload", "credential_rotate", "skill_install",
    "skill_auto_load", "mcp_server", "mcp_tools", "mcp_test", "mcp_reload",
    "sandbox_install", "sandbox_test", "nodriver_open", "nodriver_screenshot",
    "nodriver_click", "nodriver_type",
)

DESTRUCTIVE_PREFIXES = (
    "write_file", "patch_file", "append_file", "create_directory", "copy_path",
    "move_path", "move_to_trash", "replace_in_file", "write_json",
    "download_file", "create_archive", "extract_archive", "session_delete",
    "session_rename", "webhook_delete", "cron_create", "cron_update",
    "cron_delete", "cron_pause", "cron_resume", "cron_run", "delegate_cancel",
    "channel_add", "channel_remove", "channel_config", "channel_filter",
    "event_create", "event_delete", "event_log", "plugin_install",
    "plugin_enable", "plugin_disable", "plugin_config", "plugin_remove",
    "context_compress", "context_expand", "context_prune", "context_optimize",
    "credential_add", "credential_remove", "credential_export", "kanban_task",
    "kanban_move", "kanban_assign", "kanban_complete", "kanban_block",
    "checkpoint_create", "checkpoint_restore", "checkpoint_diff", "checkpoint_delete",
    "checkpoint_cleanup", "workspace_create", "workspace_switch", "workspace_delete",
    "workspace_config", "security_set_mode", "learning_add", "auto_improve_learn",
    "auto_improve_report", "log_upgrade", "learn_pattern", "learn_error",
    "track_tool_usage", "supervisor_plan", "supervisor_execute", "supervisor_adapt",
    "thinking_analyze", "thinking_plan", "thinking_chain", "session_log",
    "session_create",
)


def classify_tool(name: str) -> str:
    if name in SAFE_SMOKE_ARGS:
        return "safe_smoke"
    if name in EXPECTED_FAILURE_ARGS:
        return "expected_failure"
    if name.startswith(DESTRUCTIVE_PREFIXES):
        return "destructive_or_write"
    if name.startswith(EXTERNAL_OR_STATE_PREFIXES):
        return "external_or_stateful"
    return "unclassified"


def prepare_fixture(root: Path) -> Dict[str, str]:
    (root / "a.txt").write_text("hello old world\nMiMo Agent\n", encoding="utf-8")
    (root / "b.json").write_text('{"a":{"b":2},"items":[1,2]}', encoding="utf-8")
    (root / "c.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (root / "dir").mkdir()
    (root / "dir" / "nested.txt").write_text("nested", encoding="utf-8")
    db_path = root / "d.db"
    con = sqlite3.connect(db_path)
    con.execute("create table t(x int)")
    con.execute("insert into t values (1)")
    con.commit()
    con.close()
    return {
        "text": str(root / "a.txt"),
        "json": str(root / "b.json"),
        "csv": str(root / "c.csv"),
        "db": str(db_path),
        "dir": str(root / "dir"),
        "root": str(root),
    }


def expand_args(name: str, args: Dict[str, Any], fixture: Dict[str, str]) -> Dict[str, Any]:
    args = dict(args)
    if name in {"read_file", "file_info"}:
        args.setdefault("path", fixture["text"])
    if name == "text_diff":
        args.setdefault("old_path", fixture["text"])
    if name in {"search_files", "list_directory", "find_files", "list_tree", "project_map", "disk_usage", "security_check_path"}:
        args.setdefault("path", fixture["root"])
    if name == "task_board":
        args.setdefault("path", os.path.join(fixture["root"], "todo.json"))
    if name == "read_json" or name == "json_query":
        args.setdefault("path", fixture["json"])
    if name == "csv_preview":
        args.setdefault("path", fixture["csv"])
    if name == "sqlite_query":
        args.setdefault("db_path", fixture["db"])
    return args


def is_error_payload(payload: Any) -> bool:
    return isinstance(payload, dict) and bool(payload.get("error") or payload.get("success") is False)


def smoke_tool(name: str, args: Dict[str, Any], fixture: Dict[str, str]) -> Tuple[str, Any]:
    args = expand_args(name, args, fixture)
    try:
        raw = call_tool(name, args)
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            payload = {"raw": str(raw)[:500]}
        return ("error" if is_error_payload(payload) else "ok"), payload
    except Exception as exc:  # defensive: call_tool should usually catch these
        return "exception", {"error": repr(exc)}


def run_audit() -> Dict[str, Any]:
    schema = get_tools_schema()
    schema_names = [item["function"]["name"] for item in schema]
    structural_issues = []
    for name, meta in TOOLS.items():
        params = meta.get("parameters") or {}
        props = params.get("properties") or {}
        for required in params.get("required") or []:
            if required not in props:
                structural_issues.append({"tool": name, "issue": "required_missing_property", "field": required})
        if name not in schema_names:
            structural_issues.append({"tool": name, "issue": "missing_from_schema"})

    results = []
    with tempfile.TemporaryDirectory(prefix="mimo_tool_audit_") as tmp:
        fixture = prepare_fixture(Path(tmp))
        for name in sorted(TOOLS):
            category = classify_tool(name)
            if category == "safe_smoke":
                status, payload = smoke_tool(name, SAFE_SMOKE_ARGS[name], fixture)
            elif category == "expected_failure":
                status, payload = smoke_tool(name, EXPECTED_FAILURE_ARGS[name], fixture)
                status = "expected_failure_ok" if status == "error" else "expected_failure_unexpected_ok"
            else:
                status, payload = "skipped", {"reason": category}
            results.append({
                "tool": name,
                "category": category,
                "status": status,
                "summary": json.dumps(payload, ensure_ascii=False, default=str)[:400],
            })

    counts = Counter(item["status"] for item in results)
    categories = Counter(item["category"] for item in results)
    failures = [item for item in results if item["status"] in {"error", "exception", "expected_failure_unexpected_ok"}]
    unclassified = [item["tool"] for item in results if item["category"] == "unclassified"]
    return {
        "registered_tools": len(TOOLS),
        "schema_tools": len(schema),
        "structural_issues": structural_issues,
        "status_counts": dict(counts),
        "category_counts": dict(categories),
        "failures": failures,
        "unclassified": unclassified,
        "results": results,
        "passed": not structural_issues and not failures and not unclassified,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit MiMo tool registry safely")
    parser.add_argument("--json", action="store_true", help="Print full JSON report")
    args = parser.parse_args()
    report = run_audit()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"registered_tools={report['registered_tools']} schema_tools={report['schema_tools']}")
        print(f"passed={report['passed']}")
        print(f"status_counts={report['status_counts']}")
        print(f"category_counts={report['category_counts']}")
        print(f"structural_issues={len(report['structural_issues'])}")
        print(f"failures={len(report['failures'])}")
        print(f"unclassified={len(report['unclassified'])}")
        for item in report["failures"][:20]:
            print(f"FAIL {item['tool']}: {item['status']} {item['summary']}")
        for tool in report["unclassified"][:20]:
            print(f"UNCLASSIFIED {tool}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
