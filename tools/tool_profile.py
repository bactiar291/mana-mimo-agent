#!/usr/bin/env python3
"""
tool_profile.py — Honest tool surface for MiMo Agent.

Why this exists
---------------
The registry historically exposed 204 tools to the model. An audit showed that
most of them were never reachable by the agent's own tool router, and a subset
returned `not_implemented` (no SMTP, no SMS provider, no MCP transport, no
vision model, no whisper binary) or duplicated an existing working tool.

Advertising a tool the agent cannot honestly execute is an overclaim: it wastes
prompt budget and invites the model to promise capabilities that fail at call
time. This module keeps the default surface limited to tools that were verified
to run in this environment.

Profiles
--------
- "lean" (default): verified, non-duplicate tools only.
- "full": every registered tool, for debugging/experiments.

Select with the MIMO_TOOL_PROFILE environment variable.
"""
from __future__ import annotations

import os
from typing import Dict, Iterable, List

DEFAULT_PROFILE = "lean"

# Verified working, non-duplicate tools. Each name here was executed or read in
# source during the 2026-08-29 audit.
LEAN_TOOLS: frozenset = frozenset({
    # --- files ---
    "read_file", "write_file", "append_file", "patch_file", "replace_in_file",
    "file_info", "find_files", "search_files", "list_directory", "list_tree",
    "create_directory", "copy_path", "move_path", "move_to_trash",
    "text_diff", "read_json", "csv_preview", "code_outline", "project_map",
    "create_archive", "extract_archive", "sqlite_query",
    # --- git ---
    "git_status", "git_diff", "git_log", "git_show",
    # --- shell / system ---
    "terminal", "execute_python", "system_info", "process_list", "process_kill",
    "disk_usage",
    # --- web ---
    "web_search", "web_extract", "http_request", "download_file",
    # --- browser ---
    "browser_open", "browser_get_text", "browser_get_links", "browser_click",
    "browser_type", "browser_press", "browser_scroll", "browser_evaluate",
    "browser_console", "browser_snapshot", "browser_screenshot",
    "browser_wait_for", "browser_status", "browser_close", "browser_set_engine",
    # --- media (only what real binaries back) ---
    "vision_ocr", "vision_screenshot", "vision_analyze", "vision_compare",
    "voice_tts", "voice_list", "voice_info",
    # --- agent state ---
    "memory", "memory_facts", "memory_preferences", "memory_profile",
    "todo", "current_time",
    "skill_view", "skill_manage", "skills_list",
    "delegate_task", "delegate_status",
    # --- outbound notifications that actually post ---
    "notify_telegram", "notify_discord", "notify_slack",
})


def active_profile() -> str:
    """Return the configured profile name."""
    value = (os.environ.get("MIMO_TOOL_PROFILE") or DEFAULT_PROFILE).strip().lower()
    return value if value in {"lean", "full"} else DEFAULT_PROFILE


def allowed_names(registered: Iterable[str]) -> List[str]:
    """Names that should stay exposed for the active profile."""
    registered = list(registered)
    if active_profile() == "full":
        return registered
    return [name for name in registered if name in LEAN_TOOLS]


def apply_profile(tools: Dict[str, dict]) -> List[str]:
    """Remove out-of-profile tools from a registry dict in place.

    Returns the sorted list of removed names so callers can log or test it.
    """
    keep = set(allowed_names(tools.keys()))
    removed = sorted(name for name in tools if name not in keep)
    for name in removed:
        tools.pop(name, None)
    return removed
