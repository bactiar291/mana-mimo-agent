#!/usr/bin/env python3
"""
agent.py — Hermes-grade agentic loop for MiMo.
Features:
- Live think tag display (dim cyan)
- Robust multi-format tool call parsing
- Multi-step reasoning with full context
- Persistent memory system
- Streaming output with tool-call hiding
- Bordered response boxes (Hermes-style)
- Per-tool icons and timing display
- Animated "preparing tool..." with braille spinners
- Synthesizing animation
- Typo correction
- Clean formatting
"""
import json
import os
import re
import shlex
import sys
import threading
import itertools
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from core.mimo_client import MiMoClient, LT, GT, THINK_OPEN, THINK_CLOSE
except ImportError:
    from mimo_client import MiMoClient, LT, GT, THINK_OPEN, THINK_CLOSE
from tools.tools import get_tools_schema, call_tool

ProgressCallback = Callable[[Dict[str, Any]], None]

# ─── Smooth Spinner ──────────────────────────────────────────────────────────

THINKING_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
PROGRESS_FRAMES = [
    "▰▱▱▱▱▱▱▱▱▱",
    "▰▰▱▱▱▱▱▱▱▱",
    "▰▰▰▱▱▱▱▱▱▱",
    "▰▰▰▰▱▱▱▱▱▱",
    "▰▰▰▰▰▱▱▱▱▱",
    "▰▰▰▰▰▰▱▱▱▱",
    "▰▰▰▰▰▰▰▱▱▱",
    "▰▰▰▰▰▰▰▰▱▱",
    "▰▰▰▰▰▰▰▰▰▱",
    "▰▰▰▰▰▰▰▰▰▰",
]

TOOL_CALL_OPEN = LT + "tool_call" + GT
TOOL_CALL_CLOSE = LT + "/tool_call" + GT


class Spinner:
    def __init__(self, label: str = "Thinking", style: str = "thinking", color: str = "\033[36m"):
        self.label = label
        self.style = style
        self.frames = THINKING_FRAMES if style == "thinking" else PROGRESS_FRAMES
        self.color = color
        self.running = False
        self.thread = None

    def _spin(self):
        for frame in itertools.cycle(self.frames):
            if not self.running:
                break
            if self.style == "thinking":
                line = f"\r{self.color}{frame}\033[0m {self.label}   "
            else:
                detail = self.label
                line = f"\r{self.color}{frame}\033[0m {detail}   "
            sys.stdout.write(line)
            sys.stdout.flush()
            time.sleep(0.05)
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        sys.stdout.write("\r\033[2K")
        sys.stdout.flush()

    def update(self, label: str):
        self.label = label


# ─── Colors ──────────────────────────────────────────────────────────────────

class C:
    R = "\033[31m"
    G = "\033[32m"
    Y = "\033[33m"
    B = "\033[34m"
    M = "\033[35m"
    C = "\033[36m"
    W = "\033[37m"
    DIM = "\033[90m"
    BOLD = "\033[1m"
    X = "\033[0m"
    THINK = "\033[38;5;214m"  # warm amber for thinking (256-color)


# ─── Persistent Memory ────────────────────────────────────────────────────────

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.json")
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
LEARNING_LOG = os.path.join(DATA_DIR, "learning", "agent_lessons.jsonl")
SESSION_TRACE_LOG = os.path.join(DATA_DIR, "sessions", "agent_runs.jsonl")


class Memory:
    def __init__(self, path: str = MEMORY_FILE):
        self.path = path
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {"facts": [], "preferences": {}, "notes": [], "updated": ""}

    def _save(self):
        self.data["updated"] = datetime.now().isoformat()
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def add_fact(self, fact: str):
        if fact not in self.data["facts"]:
            self.data["facts"].append(fact)
            self._save()

    def set_pref(self, key: str, value: str):
        self.data["preferences"][key] = value
        self._save()

    def add_note(self, note: str):
        self.data["notes"].append({"text": note, "time": datetime.now().isoformat()})
        self._save()

    def clear(self):
        self.data = {"facts": [], "preferences": {}, "notes": [], "updated": ""}
        self._save()

    def summary(self) -> str:
        parts = []
        if self.data["facts"]:
            parts.append("Facts:\n" + "\n".join(f"  - {f}" for f in self.data["facts"]))
        if self.data["preferences"]:
            parts.append("Preferences:\n" + "\n".join(f"  - {k} = {v}" for k, v in self.data["preferences"].items()))
        if self.data["notes"]:
            recent = self.data["notes"][-5:]
            parts.append("Recent notes:\n" + "\n".join(f"  - [{n['time'][:10]}] {n['text']}" for n in recent))
        return "\n".join(parts) if parts else "(empty)"


# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are MiMo Agent — an advanced agentic AI assistant with the tools listed in this prompt. You are a problem-solver, not just an answer-giver. You are FAST and EFFICIENT.

TOOL CALL FORMAT — when you need a tool, output EXACTLY this JSON (no markdown wrapping, no explanation before it):
{"tool": "tool_name", "args": {"param": "value"}}

After receiving tool results, continue reasoning and answer naturally in the user's language.

=== SPEED RULES (IMPORTANT!) ===

1. MINIMIZE TOOL CALLS — use the FEWEST tools possible to achieve the goal
2. DON'T EXPLORE UNNECESSARILY — if you know what to do, just DO IT
3. COMBINE STEPS — one browser call is better than three
4. SKIP VERBOSE OUTPUT — don't explain your plan, just execute

WEB TASK EXECUTION POLICY — IMPORTANT:
- For any user-provided public URL/web task, prefer terminal curl first: fetch headers/redirects and raw HTML/JS with curl before using heavier tools.
- Use http_request for simple API calls or when curl is unnecessary, but do not jump to Chromium before lightweight HTTP/curl inspection.
- If lightweight HTTP shows a JS app or hidden API, inspect scripts/endpoints with execute_python or terminal curl. Use Python requests to debug API payloads, mail.tm flows, CSRF tokens, JSON endpoints, and form submissions.
- Use browser_open/Chromium only after HTTP/curl/API inspection fails, the site requires rendered JS, captcha/user interaction, or selectors must be clicked/typed.
- For temporary email tasks, prefer mail.tm API via http_request/execute_python first. Do not open a browser for email unless the API path fails.
- Close Chromium with browser_close when finished. Do not leave browser sessions open.
- Report real progress: what was tried, what worked, what failed, and the next fallback.

EFFICIENCY EXAMPLES:

WRONG (slow, 5+ calls):
  browser_open(url) -> browser_get_text(body) -> browser_get_links() -> browser_evaluate(...) -> ...
  
RIGHT (fast, 2-3 calls):
  browser_open(url, wait=5) -> browser_type(selector, wallet) -> browser_click(button) -> browser_get_text(result)

FOR WALLET/AIRDROP CHECKING:
  1. browser_open(url, wait=5)
  2. Look at the content — find input field and button selectors
  3. browser_type(selector, wallet_address)
  4. browser_click(button_selector) 
  5. browser_get_text(result_selector) -> DONE!

FOR SEARCHING USER PROFILES:
  1. web_search(query) OR browser_open(profile_url)
  2. browser_get_text(body) -> extract info -> DONE!

DON'T:
- Get all links when you don't need them
- Evaluate JS when CSS selectors work
- Call browser_get_text multiple times on same page
- Explore pages unless absolutely necessary

=== AGENTIC REASONING PROTOCOL ===

You MUST follow this reasoning chain for every complex task:

1. DECOMPOSE — break the problem into sub-tasks
2. PLAN — decide which tools to use and in what order
3. EXECUTE — run tools one by one, analyzing each result
4. SELF-CHECK — after each result, ask yourself:
   - "Is this result correct and complete?"
   - "Does this make sense given what I know?"
   - "Should I try a different approach?"
5. ADAPT — if a result is unexpected or wrong:
   - Don't repeat the same failed approach
   - Try a DIFFERENT tool or DIFFERENT parameters
   - Think: "What else could work?"
6. VERIFY — before giving a final answer, confirm:
   - Did I achieve the stated goal?
   - Is the information accurate?
   - Did I miss anything?

SELF-CORRECTION RULES:
- If web_search returns irrelevant results -> try different keywords, then try web_extract on specific URLs
- If web_extract fails (404, empty) -> try browser_open for JS-heavy sites
- If browser_open returns empty content -> wait longer or try different selectors
- If a tool returns an error -> analyze the error, fix the approach, retry ONCE
- If you're stuck after 2 attempts -> tell the user what you found and what failed
- NEVER repeat the exact same failed command twice

EXPLORATION MINDSET:
- When you don't know something, SEARCH for it — don't guess
- When a direct path fails, try an indirect path (e.g., search instead of direct URL)
- When results are ambiguous, try to get MORE data before concluding
- Think out loud in your reasoning: "This didn't work, let me try X instead"

GOAL-TARGETING:
- Always keep the user's ORIGINAL GOAL in mind
- Track your progress: "I've done X, still need Y and Z"
- Don't get distracted by tangential information
- If you can't fully achieve the goal, explain what's missing and why
- Prioritize ACTION over explanation — do first, explain after

=== RESPONSE FORMAT RULES (MANDATORY!) ===

- Respond in PLAIN TEXT only. No markdown tables, no box-drawing, no ASCII art, no fancy formatting.
- Use simple bullet points (- xxxxx) for lists.
- Use **bold** ONLY for critical info (errors, file paths, status).
- Keep responses SHORT. One-liners preferred. Only expand when the topic demands it.
- No greetings, no filler, no "sure thing!", no "great question!"
- If done, say done. If failed, say why. No sugarcoating.
- Speak casual like a friend, Indonesian/English mix is fine.
- NEVER use code blocks for non-code content.
- NEVER use headers (##) unless listing multiple distinct sections.

COMPLEX TASK EXAMPLES:
Task: "Find X profile and analyze their followers"
  Step 1: web_search "X profile username" -> get URL
  Step 2: browser_open URL -> get page content
  Step 3: browser_get_text with specific selectors -> extract data
  Step 4: If followers count not visible -> try different selectors or scroll
  Step 5: Compile findings and present

Task: "Build a Python script to automate X"
  Step 1: Research the target (web_search, web_extract)
  Step 2: Understand the API/mechanism (inspect JS, find endpoints)
  Step 3: Write the script (execute_python or write_file)
  Step 4: Test it (terminal)
  Step 5: Fix errors if any (iterate)
  Step 6: Verify it works (final test)

=== END REASONING PROTOCOL ===

AVAILABLE TOOLS (48):
- web_search(query*, limit)
- web_extract(url*, max_chars)
- read_file(path*, offset, limit)
- write_file(path*, content*)
- patch_file(path*, old_string*, new_string*)
- search_files(pattern*, path, target, limit)
- terminal(command*, timeout, workdir)
- list_directory(path, show_hidden)
- execute_python(code*, timeout)
- file_info(path*, hash_file)
- append_file(path*, content*, newline)
- create_directory(path*)
- copy_path(source*, destination*, overwrite)
- move_path(source*, destination*, overwrite)
- move_to_trash(path*)
- find_files(pattern*, path, mode, limit, show_hidden)
- list_tree(path, max_depth, show_hidden, limit)
- replace_in_file(path*, pattern*, replacement*, regex, max_replacements)
- text_diff(old_path*, new_path, new_content, context)
- code_outline(path*, limit)
- project_map(path, max_depth)
- read_json(path*)
- write_json(path*, data*, indent)
- json_query(path*, key_path)
- csv_preview(path*, limit, delimiter)
- sqlite_query(db_path*, query*, params, limit, allow_write)
- http_request(method*, url*, headers, body, timeout)
- download_file(url*, path*, overwrite, timeout)
- create_archive(source*, destination*, overwrite)
- extract_archive(path*, destination*, overwrite)
- git_status(path)
- git_diff(path, staged, file, limit)
- git_log(path, limit)
- git_show(path, ref, limit)
- current_time()
- system_info()
- disk_usage(path)
- process_list(filter, limit)
- process_kill(pid*, signal_name)
- task_board(action*, item, status, path)
- browser_open(url*, wait): Open URL in headless anti-detect Chromium (for SPA/JS sites)
- browser_get_text(selector): Get text from current browser page
- browser_get_links(): Get all links from current browser page
- browser_click(selector*): Click element on browser page
- browser_type(selector*, text*, press_enter): Type into input field
- browser_evaluate(js_code*): Execute JavaScript in browser
- browser_wait_for(selector*, timeout): Wait for element to appear
- browser_close(): Close browser and free memory

RULES:
1. Use tools whenever you need real information — never guess or hallucinate
2. For multi-step tasks, chain tools sequentially (search -> extract -> analyze -> answer)
3. After tool results, give a natural answer in the user's language
4. Do NOT repeat the user's question back to them
5. If a tool fails, try an alternative approach
6. For code/file tasks, verify results by reading back
7. Be thorough but concise — no filler text
8. NEVER use markdown formatting (**bold**, *italic*, `code`, ```code blocks```, # headers, - bullet lists)
9. This is a TERMINAL — output plain text only. No markdown rendering.
10. For structured data, use box-drawing tables like this:
    ┌──────────────┬──────────────┐
    │ Label        │ Value        │
    ├──────────────┼──────────────┤
    │ Username     │ @Gxxxxxxxxx  │
    │ Followers    │ 71           │
    └──────────────┴──────────────┘
11. Use plain text lists with arrows: -> item, => important, * bullet
12. Keep answers clean, structured, professional — like a senior engineer's terminal output
13. MAX 8 tool calls per question. Use them wisely — be efficient, don't waste calls on unnecessary exploration.
14. If web_search or web_extract fails to find something after 2 tries, tell the user you couldn't find it. Don't keep trying different URLs.
15. NEVER invent or hallucinate URLs. Only use URLs from search results or user input. If you're not sure a URL exists, search for it first.
16. If the user's message has typos, understand the INTENT and work with the corrected meaning. Don't ask "did you mean X?" — just proceed with the most likely correction.
17. When user asks about a URL they provided, use that EXACT URL — don't modify or guess variations.
18. For SPA/JS-heavy sites (React, Next.js, Vue, Angular) that return empty content with web_extract, use browser_open instead. It renders JavaScript and gets the real page content.
19. Always close the browser with browser_close when done to free memory.

STYLE:
- Match the user's language (Indonesian if they speak Indonesian)
- Plain text only — NO markdown, NO asterisks for bold, NO backticks
- Use indentation and line breaks for readability
- For emphasis use CAPS or arrows =>
- Be direct, sharp, actionable — like a senior dev talking
- Learn from every interaction — note patterns, preferences, corrections
- Self-improve: if user corrects you, remember and adapt permanently
- For section separators, use: ────────────────── (box-drawing chars, NOT @@@@@ or ###)
- NEVER use @@@@@ as separators — always use ──────── or -----------------
- Use box-drawing tables for structured data:
    ┌──────────────┬──────────────┐
    │ Label        │ Value        │
    ├──────────────┼──────────────┤
    │ Data         │ Here         │
    └──────────────┴──────────────┘
"""


def build_tools_description(tool_names: Optional[List[str]] = None) -> str:
    schemas = get_tools_schema()
    allowed = set(tool_names or [])
    lines = []
    for s in schemas:
        fn = s["function"]
        name = fn["name"]
        if allowed and name not in allowed:
            continue
        desc = fn["description"][:80]
        params = fn["parameters"].get("properties", {})
        required = fn["parameters"].get("required", [])
        param_str = ", ".join(f"{k}{'*' if k in required else ''}" for k in params.keys())
        lines.append(f"  - {name}({param_str}): {desc}")
    return "\n".join(lines)


# ─── Tool Call Parser (Multi-Strategy) ────────────────────────────────────────

def parse_tool_call(response: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    """
    Parse tool call from model response. Strategies:
   1. <tool_call>{...}</tool_call> wrapper
    2. ```json\\n{...}\\n``` code block
    3. Plain {"tool": "name", "args": {...}} with balanced braces
    4. Whole response is JSON
    """
    if not response or len(response.strip()) < 5:
        return None

    # Strip think tags first
    cleaned = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL).strip()

    # Strategy 1: <tool_call> wrapper
    wrapper_match = re.search(
        r'<tool_call>\\s*(\\{.*?\\})\\s*</tool_call>',
        cleaned, re.DOTALL
    )
    if wrapper_match:
        try:
            obj = json.loads(wrapper_match.group(1))
            if "tool" in obj:
                return obj["tool"], obj.get("args", {})
        except json.JSONDecodeError:
            pass

    # Strategy 2: JSON in code block
    code_block = re.search(r'```(?:json)?\\s*(\\{[^`]*?"tool"[^`]*?\\})\\s*```', cleaned, re.DOTALL)
    if code_block:
        try:
            obj = json.loads(code_block.group(1))
            if "tool" in obj:
                return obj["tool"], obj.get("args", {})
        except json.JSONDecodeError:
            pass

    # Strategy 3: {"tool": "name", "args": {...}} with balanced braces
    pattern = r'\\{"tool"\\s*:\\s*"([^"]+)"\\s*,\\s*"args"\\s*:\\s*'
    match = re.search(pattern, cleaned)
    if match:
        tool_name = match.group(1)
        start = match.end()
        depth = 1
        i = start
        in_string = False
        escape = False
        while i < len(cleaned) and depth > 0:
            ch = cleaned[i]
            if escape:
                escape = False
            elif ch == '\\\\':
                escape = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == '{':
                    depth += 1
                elif ch == '}':
                    depth -= 1
            i += 1
        if depth == 0:
            args_str = cleaned[start:i-1]
            try:
                args = json.loads(args_str)
                return tool_name, args
            except json.JSONDecodeError:
                pass

    # Strategy 4: Whole response is JSON
    try:
        obj = json.loads(cleaned.strip())
        if isinstance(obj, dict) and "tool" in obj:
            return obj["tool"], obj.get("args", {})
    except json.JSONDecodeError:
        pass

    return None


# ─── Typo Correction ─────────────────────────────────────────────────────────

import difflib

# Common typo patterns (Indonesian + English tech terms)
TYPO_CORRECTIONS = {
    "munri": "murni",
    "monri": "monri",
    "skrip": "skrip",
    "script": "script",
    "utomation": "automation",
    "atomation": "automation",
    "webiste": "website",
    "websie": "website",
    "scrpit": "script",
    "scrpt": "script",
    "scrptnya": "script-nya",
    "skirpt": "script",
    "fuction": "function",
    "funtion": "function",
    "runing": "running",
    "rinning": "running",
    "conection": "connection",
    "connetion": "connection",
    "retreive": "retrieve",
    "retrive": "retrieve",
    "instalasi": "instalasi",
    "instal": "install",
    "folde": "folder",
    "fienya": "file-nya",
    "filenya": "file-nya",
    "dilurusin": "diluruskan",
    "penalaran": "penalaran",
    "typo": "typo",
    "halu": "halu",
    "halusinasi": "halusinasi",
    "bautin": "buatin",
    "buati": "buatin",
    "kasi": "kasih",
    "kasih": "kasih",
    "gak": "gak",
    "gajelas": "gak jelas",
    "jadiin": "jadiin",
    "bikinin": "bikinin",
    "bikin": "bikin",
    "cariin": "cariin",
    "cari": "cari",
    "ambilin": "ambilin",
    "ambil": "ambil",
    "baca": "baca",
    "tulis": "tulis",
    "hapus": "hapus",
    "jalanin": "jalanin",
    "jalan": "jalan",
    "cek": "cek",
    "tolong": "tolong",
    "plis": "tolong",
    "pls": "tolong",
    "dong": "dong",
    "ya": "ya",
    "sih": "sih",
    "nih": "nih",
    "deh": "deh",
    "kok": "kok",
    "lho": "lho",
}

# URL typo patterns — fix common URL typos
URL_FIXES = {
    "campaig": "campaign",
    "campign": "campaign",
    "campaing": "campaign",
    "registr": "register",
    "registar": "register",
    "dashbord": "dashboard",
    "dashbaord": "dashboard",
    "proflie": "profile",
    "profle": "profile",
    "seting": "setting",
    "settng": "setting",
}


def fix_typo(text: str) -> str:
    """Fix common typos in user input. Returns corrected text."""
    words = text.split()
    corrected = []
    suffixes = ["nya", "in", "an", "kan", "pun", "lah", "kah", "tah", "dong", "deh", "sih", "nih", "kok"]

    for word in words:
        lower = word.lower().strip(".,!?;:")

        if lower in TYPO_CORRECTIONS:
            replacement = TYPO_CORRECTIONS[lower]
            if word[0].isupper():
                replacement = replacement.capitalize()
            corrected.append(replacement)
            continue

        if lower in URL_FIXES:
            corrected.append(URL_FIXES[lower])
            continue

        found = False
        for suffix in suffixes:
            if lower.endswith(suffix) and len(lower) > len(suffix) + 2:
                root = lower[:-len(suffix)]
                if root in TYPO_CORRECTIONS:
                    replacement = TYPO_CORRECTIONS[root] + "-" + suffix
                    if word[0].isupper():
                        replacement = replacement.capitalize()
                    corrected.append(replacement)
                    found = True
                    break
        if found:
            continue

        matches = difflib.get_close_matches(lower, TYPO_CORRECTIONS.keys(), n=1, cutoff=0.85)
        if matches:
            replacement = TYPO_CORRECTIONS[matches[0]]
            if word[0].isupper():
                replacement = replacement.capitalize()
            corrected.append(replacement)
            continue

        corrected.append(word)

    return " ".join(corrected)


def fix_url_typo(url: str) -> str:
    """Fix common typos in URLs (path segments)."""
    for typo, fix in URL_FIXES.items():
        if typo in url.lower():
            idx = url.lower().find(typo)
            url = url[:idx] + fix + url[idx+len(typo):]
    return url


# ─── Per-Tool Icons and Labels (Hermes-style) ────────────────────────────────

TOOL_ICONS = {
    "web_search": "🌐",
    "web_extract": "📄",
    "read_file": "📖",
    "write_file": "✏️",
    "append_file": "📝",
    "patch_file": "🔧",
    "delete_file": "🗑️",
    "search_files": "🔍",
    "terminal": "💻",
    "execute_python": "🐍",
    "list_directory": "📁",
    "file_info": "📋",
    "create_directory": "📂",
    "copy_path": "📋",
    "move_path": "📦",
    "move_to_trash": "🗑️",
    "find_files": "🔎",
    "list_tree": "🌳",
    "replace_in_file": "🔄",
    "text_diff": "🔍",
    "code_outline": "📑",
    "project_map": "🗺️",
    "read_json": "📊",
    "write_json": "📊",
    "json_query": "🔍",
    "csv_preview": "📊",
    "sqlite_query": "🗄️",
    "http_request": "🌐",
    "download_file": "⬇️",
    "create_archive": "📦",
    "extract_archive": "📦",
    "git_status": "🔀",
    "git_diff": "🔀",
    "git_log": "📜",
    "git_show": "📜",
    "current_time": "⏰",
    "system_info": "⚙️",
    "disk_usage": "💾",
    "process_list": "🖥️",
    "process_kill": "☠️",
    "task_board": "📋",
    "browser_open": "🌐",
    "browser_get_text": "📖",
    "browser_get_links": "🔗",
    "browser_click": "👆",
    "browser_type": "⌨️",
    "browser_evaluate": "⚡",
    "browser_wait_for": "⏳",
    "browser_close": "🔌",
    # New tools
    "sandbox_execute": "🐍",
    "delegate_task": "🚀",
    "session_search": "🔍",
    "vision_analyze": "👁️",
    "voice_tts": "🔊",
    "memory_enhanced": "🧠",
    "thinking_analyze": "💭",
    "supervisor_plan": "📋",
    "skill_manage": "📚",
    "kanban_task": "📋",
    "webhook_create": "🔔",
    "notify_telegram": "📱",
    "context_compress": "📦",
    "credential_add": "🔑",
    "checkpoint_create": "💾",
    "workspace_create": "🏗️",
    "mcp_server": "🔌",
    "event_create": "⚡",
    "plugin_install": "🧩",
    "channel_add": "📡",
    "auto_improve_learn": "📈",
    "skill_scan": "🛡️",
}

TOOL_LABELS = {
    "web_search": "Mencari di web...",
    "web_extract": "Mengekstrak halaman...",
    "read_file": "Membaca file...",
    "write_file": "Menulis file...",
    "append_file": "Menambah ke file...",
    "patch_file": "Mengedit file...",
    "delete_file": "Menghapus file...",
    "search_files": "Mencari di file...",
    "terminal": "Menjalankan perintah...",
    "execute_python": "Menjalankan Python...",
    "list_directory": "Membaca direktori...",
    "file_info": "Mengecek info file...",
    "create_directory": "Membuat direktori...",
    "copy_path": "Menyalin file...",
    "move_path": "Memindah file...",
    "move_to_trash": "Menghapus file...",
    "find_files": "Mencari file...",
    "list_tree": "Membaca struktur folder...",
    "replace_in_file": "Mengganti teks...",
    "text_diff": "Membandingkan file...",
    "code_outline": "Membaca struktur kode...",
    "project_map": "Memetakan proyek...",
    "read_json": "Membaca JSON...",
    "write_json": "Menulis JSON...",
    "json_query": "Query JSON...",
    "csv_preview": "Membaca CSV...",
    "sqlite_query": "Query database...",
    "http_request": "Request HTTP...",
    "download_file": "Mengunduh file...",
    "create_archive": "Membuat arsip...",
    "extract_archive": "Mengekstrak arsip...",
    "git_status": "Mengecek git status...",
    "git_diff": "Mengecek git diff...",
    "git_log": "Mengecek git log...",
    "git_show": "Mengecek commit...",
    "current_time": "Mengecek waktu...",
    "system_info": "Mengecek sistem...",
    "disk_usage": "Mengecek disk...",
    "process_list": "Mengecek proses...",
    "process_kill": "Menghentikan proses...",
    "task_board": "Mengupdate task...",
    "browser_open": "Membuka halaman...",
    "browser_get_text": "Membaca konten halaman...",
    "browser_get_links": "Mengambil link...",
    "browser_click": "Mengklik elemen...",
    "browser_type": "Mengetik...",
    "browser_evaluate": "Menjalankan JavaScript...",
    "browser_wait_for": "Menunggu elemen...",
    "browser_close": "Menutup browser...",
}


# ─── Hermes-Style UI Helpers ──────────────────────────────────────────────────

def _format_duration(seconds: float) -> str:
    """Format duration in human-readable form."""
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    else:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins}m {secs:.0f}s"


def _print_border(text: str, color: str = C.C, width: int = 80):
    """Print text inside a bordered box (Hermes-style)."""
    # Calculate inner width for text
    inner_width = width - 4  # Account for "    " prefix and borders

    # Word-wrap the text
    lines = []
    for paragraph in text.split('\n'):
        if not paragraph:
            lines.append('')
            continue
        while len(paragraph) > inner_width:
            # Find last space within width
            break_at = paragraph.rfind(' ', 0, inner_width)
            if break_at == -1:
                break_at = inner_width
            lines.append(paragraph[:break_at])
            paragraph = paragraph[break_at:].lstrip()
        if paragraph:
            lines.append(paragraph)

    # Print box
    print(f"\n{color}\u256d{'─' * (width - 2)}\u256e{C.X}")
    for line in lines:
        padded = f"  {line}"
        # Pad to full width
        visible_len = len(padded)
        padding = max(0, width - 4 - visible_len)
        print(f"{color}  {padded}{' ' * padding}{C.X}")
    print(f"{color}\u2570{'─' * (width - 2)}\u256f{C.X}\n")


def _print_preparing(tool_name: str):
    """Print 'preparing tool...' line with icon (Hermes-style)."""
    icon = TOOL_ICONS.get(tool_name, "⚙️")
    label = TOOL_LABELS.get(tool_name, f"Menjalankan {tool_name}...")
    # Smooth animation with multiple frames
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼"]
    for frame in frames:
        sys.stdout.write(f"\r  {C.DIM}┊{C.X} {icon} {C.CYAN}{frame}{C.X} {C.DIM}preparing {tool_name}...{C.X}   ")
        sys.stdout.flush()
        time.sleep(0.05)
    sys.stdout.write(f"\r  {C.DIM}┊{C.X} {icon} {C.DIM}preparing {tool_name}...{C.X}   ")
    sys.stdout.flush()


def _print_tool_execution(tool_name: str, args: Dict[str, Any], duration: float):
    """Print tool execution line with command preview and timing (Hermes-style)."""
    icon = TOOL_ICONS.get(tool_name, "⚙️")
    time_str = _format_duration(duration)

    if tool_name in ("terminal", "execute_python"):
        cmd = args.get("command", args.get("code", ""))
        preview = cmd[:80].replace('\n', ' ')
        if len(cmd) > 80:
            preview += "..."
        print(f"\r\033[2K  {C.DIM}┊{C.X} {icon} {C.DIM}${preview}{C.X}  {C.DIM}{time_str}{C.X}")
    else:
        arg_preview = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(args.items())[:2])
        print(f"\r\033[2K  {C.DIM}┊{C.X} {icon} {C.DIM}{tool_name}({arg_preview}){C.X}  {C.DIM}{time_str}{C.X}")


def _print_tool_result(tool_name: str, result: str):
    """Print tool result status line (Hermes-style)."""
    try:
        data = json.loads(result)
        if "error" in data:
            print(f"  {C.DIM}┊{C.X} {C.R}error:{C.X} {C.DIM}{str(data['error'])[:120]}{C.X}")
        else:
            if isinstance(data, dict):
                keys = list(data.keys())[:4]
                preview = ", ".join(keys)
                print(f"  {C.DIM}┊{C.X} {C.G}ok{C.X} {C.DIM}({preview}){C.X}")
            else:
                print(f"  {C.DIM}┊{C.X} {C.G}ok{C.X}")
    except json.JSONDecodeError:
        lines = result.strip().split('\n')
        print(f"  {C.DIM}┊{C.X} {C.G}ok{C.X} {C.DIM}({len(lines)} lines){C.X}")


def _print_synthesizing():
    """Print synthesizing animation (Hermes-style)."""
    frames = ["(◔_◔)", "(◑_◑)", "(◕_◕)", "(◔_◔)"]
    for frame in frames:
        sys.stdout.write(f"\r  {C.DIM}{frame} synthesizing...{C.X}")
        sys.stdout.flush()
        time.sleep(0.12)
    # Smooth clear
    sys.stdout.write("\r\033[2K")
    sys.stdout.flush()
    sys.stdout.flush()


# ─── Agent ───────────────────────────────────────────────────────────────────

class MiMoAgent:
    """Hermes-grade agentic conversation manager."""

    def __init__(self, model: str = "mimo-v2.5-pro", web_search: bool = True,
                 show_thinking: bool = True, quiet: bool = False,
                 progress_callback: Optional[ProgressCallback] = None,
                 max_runtime: int = 180,
                 request_timeout: int = 75,
                 max_tool_calls: int = 0):
        self.client = MiMoClient(model=model, timeout=request_timeout)
        self.history: List[Dict[str, str]] = []
        self.web_search = web_search
        self.show_thinking = show_thinking
        self.quiet = quiet
        self.max_tool_calls = max(0, int(max_tool_calls))
        self.max_runtime = max_runtime
        self.progress_callback = progress_callback
        self.tools_schema = get_tools_schema()
        self.memory = Memory()

    def _emit_progress(self, callback: Optional[ProgressCallback], event: str, **data: Any):
        """Emit structured progress without letting UI callbacks break the agent."""
        if not callback:
            return
        payload = {"event": event, "time": time.time(), **data}
        try:
            callback(payload)
        except Exception:
            pass

    def _append_jsonl(self, path: str, payload: Dict[str, Any]):
        try:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(path, "a", encoding="utf-8") as file_handle:
                file_handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass

    def _record_agent_lesson(self, lesson_type: str, detail: str, context: str = ""):
        self._append_jsonl(
            LEARNING_LOG,
            {
                "time": datetime.now().isoformat(),
                "type": lesson_type,
                "detail": self._safe_preview(detail, 400),
                "context": self._safe_preview(context, 500),
            },
        )

    def _recent_agent_lessons(self, limit: int = 5) -> str:
        try:
            if not os.path.exists(LEARNING_LOG):
                return ""
            with open(LEARNING_LOG, "r", encoding="utf-8") as file_handle:
                lines = file_handle.readlines()[-limit:]
            lessons = []
            for line in lines:
                try:
                    item = json.loads(line)
                    lessons.append(f"- {item.get('type')}: {item.get('detail')}")
                except json.JSONDecodeError:
                    continue
            return "\n".join(lessons)
        except Exception:
            return ""

    def _learn_from_user_message(self, user_msg: str) -> List[str]:
        text = (user_msg or "").strip()
        lower = text.lower()
        learned: List[str] = []

        language_patterns = (
            ("bahasa indonesia", "Indonesian"),
            ("bahasa indo", "Indonesian"),
            ("pakai indo", "Indonesian"),
            ("jawab indo", "Indonesian"),
            ("english", "English"),
        )
        for marker, language in language_patterns:
            if marker in lower:
                self.memory.set_pref("language", language)
                learned.append(f"language={language}")
                break

        concise_markers = ("jangan muter", "jangan bertele", "langsung aja", "to the point", "singkat aja")
        if any(marker in lower for marker in concise_markers):
            self.memory.set_pref("style", "direct_concise")
            learned.append("style=direct_concise")

        name_match = re.search(r"\b(?:panggil|call)\s+(?:gue|aku|saya|me)\s+([A-Za-z0-9_.-]{2,40})", text, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip()
            self.memory.set_pref("user_name", name)
            learned.append(f"user_name={name}")

        avoid_match = re.search(r"\b(?:jangan|dont|don't)\s+(.{3,80})", text, re.IGNORECASE)
        if avoid_match:
            avoid = re.sub(r"\s+", " ", avoid_match.group(1)).strip(" .,!?:;")
            if avoid and not any(secret in avoid.lower() for secret in ("password", "token", "cookie")):
                self.memory.set_pref("avoid", avoid)
                learned.append(f"avoid={self._safe_preview(avoid, 60)}")

        prefer_match = re.search(r"\b(?:gue|aku|saya|i)\s+(?:prefer|lebih suka|suka)\s+(.{3,80})", text, re.IGNORECASE)
        if prefer_match:
            pref = re.sub(r"\s+", " ", prefer_match.group(1)).strip(" .,!?:;")
            if pref:
                self.memory.set_pref("preference", pref)
                learned.append(f"preference={self._safe_preview(pref, 60)}")

        return learned

    def _record_session_trace(
        self,
        user_msg: str,
        answer: str,
        tool_trace: List[str],
        status: str,
        duration: float,
        active_tools: List[str],
    ):
        self._append_jsonl(
            SESSION_TRACE_LOG,
            {
                "time": datetime.now().isoformat(),
                "status": status,
                "duration": round(duration, 3),
                "user": self._safe_preview(user_msg, 500),
                "answer": self._safe_preview(answer, 700),
                "tool_trace": tool_trace[-12:],
                "active_tools": active_tools,
            },
        )

    def _safe_preview(self, value: Any, limit: int = 180) -> str:
        """Compact data for progress UI without dumping huge outputs."""
        if value is None:
            return ""
        if not isinstance(value, str):
            try:
                value = json.dumps(value, ensure_ascii=False)
            except TypeError:
                value = str(value)
        value = redact = re.sub(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b", "<redacted>", value)
        value = re.sub(r"bot\d{6,}:[A-Za-z0-9_-]+", "bot<redacted>", value)
        value = re.sub(r"\s+", " ", value).strip()
        if len(value) > limit:
            return value[:limit - 1] + "…"
        return value

    def _summarize_tool_args(self, tool_name: str, args: Dict[str, Any]) -> str:
        if not isinstance(args, dict):
            return self._safe_preview(args)
        if tool_name == "http_request":
            method = args.get("method", "GET")
            url = args.get("url", "")
            return self._safe_preview(f"{method} {url}", 220)
        if tool_name == "terminal":
            return self._safe_preview(args.get("command", ""), 220)
        if tool_name == "execute_python":
            code = args.get("code", "")
            first_line = str(code).strip().splitlines()[0] if str(code).strip() else "python"
            return self._safe_preview(first_line, 220)
        if tool_name.startswith("browser_"):
            if "url" in args:
                return self._safe_preview(args.get("url"), 220)
            if "selector" in args:
                return self._safe_preview(args.get("selector"), 220)
        return self._safe_preview(args, 220)

    def _summarize_tool_result(self, result: str) -> str:
        try:
            data = json.loads(result)
            if isinstance(data, dict):
                if "error" in data:
                    return "error: " + self._safe_preview(data.get("error"), 160)
                files = self._extract_result_files(data)
                if files:
                    return self._safe_preview(f"file {files[0]}", 180)
                if "content" in data:
                    title = data.get("title") or data.get("url") or ""
                    return self._safe_preview(f"{title} {data.get('content', '')}", 180)
                if "status" in data:
                    body = data.get("body", "")
                    return self._safe_preview(f"status {data.get('status')} {body}", 180)
                if "exit_code" in data:
                    output = data.get("output", "")
                    return self._safe_preview(f"exit {data.get('exit_code')} {output}", 180)
        except Exception:
            pass
        return self._safe_preview(result, 180)

    def _tool_result_data(self, result: str) -> Dict[str, Any]:
        try:
            data = json.loads(result)
            return data if isinstance(data, dict) else {"result": data}
        except Exception:
            return {"result": result}

    def _tool_result_status(self, result: str) -> str:
        data = self._tool_result_data(result)
        if data.get("error") or data.get("success") is False:
            return "error"
        if "exit_code" in data:
            try:
                if int(data.get("exit_code", 0)) != 0:
                    return "error"
            except (TypeError, ValueError):
                return "error"
        if "status" in data:
            status = data.get("status")
            if isinstance(status, int) and status >= 400:
                return "error"
            if isinstance(status, str) and status.lower() in {"error", "failed", "fail"}:
                return "error"
        return "ok"

    def _task_tool_budget(self, user_msg: str) -> int:
        if self.max_tool_calls <= 0:
            return 1_000_000
        text = user_msg.lower()
        cap = self.max_tool_calls
        debug_terms = ("debug", "fix", "error", "traceback", "api", "curl", "terminal", "log", "deploy")
        browser_action_terms = ("login", "signup", "register", "daftar", "form", "claim", "submit", "subitin", "isi", "wallet", "connect")
        browser_terms = ("http://", "https://", "website", "web", "browser")
        if any(term in text for term in debug_terms):
            return min(cap, 24)
        if any(term in text for term in browser_action_terms):
            return min(cap, 18)
        if any(term in text for term in browser_terms):
            return min(cap, 12)
        return min(cap, 4)

    def _tool_budget_label(self, tool_budget: int) -> str:
        if self.max_tool_calls <= 0 or tool_budget >= 1_000_000:
            return "runtime-only"
        return f"{tool_budget} calls"

    def _select_tool_names(self, user_msg: str) -> List[str]:
        text = (user_msg or "").lower()
        ordered_names = [s["function"]["name"] for s in self.tools_schema]
        names = set(ordered_names)
        selected = set()

        def add(*tool_names: str):
            selected.update(name for name in tool_names if name in names)

        common = ("current_time",)
        add(*common)

        has_url = bool(self._first_url(user_msg))
        web_terms = ("http://", "https://", "website", "web", "search", "cari", "google", "cek situs", "site")
        browser_action_terms = (
            "submit", "subit", "subitin", "isi", "email", "login", "signup",
            "register", "daftar", "form", "claim", "wallet", "connect", "click", "klik",
        )
        file_terms = (
            "file", "folder", "repo", "code", "kode", "test", "bug", "fix", "patch",
            "edit", "ubah", "benerin", "debug", "traceback", "git", "diff",
            "audit", "reaudit", "agent", "tool", "tools", "registry", "prompt",
        )
        terminal_terms = ("terminal", "command", "jalanin", "run", "install", "pip", "npm", "server", "process", "log")
        python_terms = ("python", "script", "calculate", "hitung", "kalkulasi", "data")
        memory_terms = ("memory", "remember", "ingat", "inget", "preferensi", "preference", "profil", "profile")

        if any(term in text for term in memory_terms):
            add("memory", "memory_enhanced", "memory_facts", "memory_preferences", "memory_profile", "memory_environment")

        if has_url or any(term in text for term in web_terms):
            add("web_search", "web_extract", "http_request")

        if has_url and any(term in text for term in browser_action_terms):
            add(
                "browser_open", "browser_get_text", "browser_click", "browser_type",
                "browser_wait_for", "browser_evaluate", "browser_screenshot",
                "browser_status", "browser_close", "browser_set_engine",
                "web_extract", "http_request", "terminal",
            )
        elif any(term in text for term in ("browser", "chromium", "selector", "click", "klik")):
            add(
                "browser_open", "browser_get_text", "browser_click", "browser_type",
                "browser_wait_for", "browser_evaluate", "browser_screenshot",
                "browser_status", "browser_close",
            )

        if any(term in text for term in file_terms):
            add(
                "read_file", "write_file", "patch_file", "append_file", "replace_in_file",
                "search_files", "find_files", "list_directory", "list_tree", "file_info",
                "text_diff", "code_outline", "project_map", "git_status", "git_diff",
                "git_log", "git_show", "execute_python", "terminal",
            )

        if any(term in text for term in terminal_terms):
            add("terminal", "execute_python", "system_info", "process_list", "process_kill", "disk_usage")

        if any(term in text for term in python_terms):
            add("execute_python", "sandbox_execute")

        if any(term in text for term in ("screenshot", "gambar", "image", "vision", "ocr")):
            add("vision_analyze", "vision_screenshot", "vision_ocr", "vision_compare", "browser_screenshot")

        tts_terms = (
            "tts", "text to speech", "text-to-speech", "buat audio", "bikin audio",
            "generate audio", "buat mp3", "bikin mp3", "voiceover", "narasi suara",
            "ubah teks jadi suara", "konversi teks jadi suara", "convert text to speech",
        )
        voice_create_actions = ("buat", "bikin", "generate", "convert", "konversi", "ubah", "simpan")
        voice_create_targets = ("audio", "mp3", "voiceover", "narasi suara")
        if any(term in text for term in tts_terms) or (
            any(action in text for action in voice_create_actions)
            and any(target in text for target in voice_create_targets)
        ) or (
            any(action in text for action in voice_create_actions)
            and "suara" in text
            and any(target in text for target in ("teks", "text", "mp3", "audio"))
        ):
            add("voice_tts", "voice_list", "text_to_speech")

        if any(term in text for term in ("transcribe", "transkripsi", "transkrip", "speech to text", "speech-to-text", "stt")):
            add("voice_transcribe", "voice_info")

        if any(term in text for term in ("voice list", "list voice", "daftar voice", "daftar suara tts")):
            add("voice_list")

        if any(term in text for term in ("audio info", "info audio", "metadata audio", "cek audio")):
            add("voice_info")

        if not selected:
            add("web_search", "current_time")

        return [name for name in ordered_names if name in selected]

    def _tool_call_key(self, tool_name: str, args: Dict[str, Any]) -> str:
        try:
            args_key = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
        except TypeError:
            args_key = str(args)
        return f"{tool_name}:{args_key}"

    def _normalize_tool_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        remaining_runtime: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], List[str]]:
        normalized = dict(args or {})
        notes: List[str] = []
        timeout_caps = {
            "terminal": 35,
            "execute_python": 35,
            "http_request": 20,
            "download_file": 45,
            "browser_wait_for": 12,
        }
        if tool_name in timeout_caps:
            default_timeout = timeout_caps[tool_name]
            raw_timeout = normalized.get("timeout", default_timeout)
            try:
                timeout = int(raw_timeout)
            except (TypeError, ValueError):
                timeout = default_timeout
            cap = default_timeout
            if remaining_runtime is not None:
                cap = max(3, min(cap, int(max(1, remaining_runtime - 8))))
            clamped = max(1, min(timeout, cap))
            if clamped != timeout:
                notes.append(f"timeout {timeout}s -> {clamped}s")
            normalized["timeout"] = clamped
        return normalized, notes

    def _tool_evidence(self, tool_name: str, args: Dict[str, Any], result: str, status: str) -> Dict[str, str]:
        data = self._tool_result_data(result)
        summary = self._summarize_tool_result(result)
        if status == "error":
            return {
                "verdict": "failed",
                "evidence": summary,
                "instruction": "Do not claim success. Pick a targeted fallback or explain the blocker.",
            }

        evidence_parts = []
        if isinstance(data, dict):
            for key in ("url", "status", "title", "path", "file", "exit_code", "engine"):
                if key in data:
                    evidence_parts.append(f"{key}={data.get(key)}")
            if data.get("content"):
                evidence_parts.append(f"content_preview={self._safe_preview(data.get('content'), 140)}")
            if data.get("output"):
                evidence_parts.append(f"output_preview={self._safe_preview(data.get('output'), 140)}")
        evidence = "; ".join(evidence_parts) or summary

        instruction = "If this evidence satisfies the user request, produce the final answer now."
        if tool_name == "browser_open":
            instruction = "Inspect page state next only if the user's requested action is not yet verified."
        elif tool_name in {"browser_click", "browser_type"}:
            instruction = "Verify the visible result with browser_get_text or browser_screenshot before claiming success."
        elif tool_name in {"web_extract", "http_request", "web_search", "terminal", "execute_python", "read_file"}:
            instruction = "If the requested information is present, answer now instead of exploring unrelated tools."

        return {"verdict": "ok", "evidence": evidence, "instruction": instruction}

    def _first_url(self, text: str) -> str:
        match = re.search(r'https?://[^\s<>"\')]+', text or "")
        return match.group(0).rstrip(".,);]") if match else ""

    def _empty_response_fallback_call(self, user_msg: str, retry_index: int) -> Optional[Tuple[str, Dict[str, Any]]]:
        url = self._first_url(user_msg)
        if not url:
            return None
        text = user_msg.lower()
        browser_terms = (
            "submit", "subit", "subitin", "isi", "email", "login", "signup",
            "register", "daftar", "form", "claim", "wallet", "connect",
        )
        if any(term in text for term in browser_terms):
            return "browser_open", {"url": url, "wait": 5}
        if retry_index <= 1:
            return "web_extract", {"url": url, "max_chars": 10000}
        return "browser_open", {"url": url, "wait": 5}

    def _fallback_hint(self, tool_name: str, args: Dict[str, Any], result: str) -> str:
        status = self._tool_result_status(result)
        if status != "error":
            return "Lanjut dari hasil tool ini."
        if tool_name == "browser_open":
            url = args.get("url", "") if isinstance(args, dict) else ""
            return (
                "browser_open gagal. Fallback berurutan: coba web_extract/http_request untuk baca HTML, "
                "terminal curl untuk cek status, lalu browser_set_engine atau browser_close sebelum retry Chromium. "
                f"Target: {url}"
            )
        if tool_name.startswith("browser_"):
            return "Tool browser gagal. Cek selector/state halaman, ambil browser_get_text/browser_screenshot, atau retry setelah browser_close."
        if tool_name in ("http_request", "web_extract"):
            return "Tool web gagal. Coba terminal curl atau browser_open untuk jalur alternatif."
        if tool_name == "terminal":
            return "Command gagal. Baca stderr/exit code, koreksi command, lalu retry dengan batas waktu lebih kecil."
        return "Tool gagal. Gunakan error ini sebagai input planning berikutnya dan pilih fallback yang lebih stabil."

    def _fallback_steps(self, tool_name: str, args: Dict[str, Any], result: str) -> List[Dict[str, Any]]:
        if self._tool_result_status(result) != "error" or not isinstance(args, dict):
            return []

        url = str(args.get("url", "") or "").strip()
        if tool_name == "browser_open" and url:
            wait = args.get("wait", 3)
            try:
                wait = max(3, min(10, int(wait) + 2))
            except (TypeError, ValueError):
                wait = 5
            current_engine = args.get("engine") or ""
            retry_engine = "playwright" if current_engine != "playwright" else "drission"
            curl_command = (
                "curl -L -sS --max-time 20 "
                f"-A {shlex.quote('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')} "
                f"{shlex.quote(url)}"
            )
            return [
                {
                    "tool": "web_extract",
                    "args": {"url": url, "max_chars": 10000},
                    "detail": "Fallback ringan: ekstrak HTML tanpa Chromium",
                    "stop_on_success": True,
                },
                {
                    "tool": "http_request",
                    "args": {"method": "GET", "url": url, "timeout": 20},
                    "detail": "Fallback HTTP: cek status dan body langsung",
                    "stop_on_success": True,
                },
                {
                    "tool": "terminal",
                    "args": {"command": curl_command, "timeout": 25},
                    "detail": "Fallback curl: cek akses dari shell",
                    "stop_on_success": True,
                },
                {
                    "tool": "browser_status",
                    "args": {},
                    "detail": "Diagnostik Chromium sebelum reset",
                    "stop_on_success": False,
                },
                {
                    "tool": "browser_close",
                    "args": {},
                    "detail": "Reset Chromium dan bersihkan state browser",
                    "stop_on_success": False,
                },
                {
                    "tool": "browser_open",
                    "args": {"url": url, "wait": wait, "engine": retry_engine},
                    "detail": f"Retry Chromium dengan engine {retry_engine}",
                    "stop_on_success": True,
                },
            ]

        if tool_name == "web_extract" and url:
            curl_command = (
                "curl -L -sS --max-time 20 "
                f"-A {shlex.quote('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')} "
                f"{shlex.quote(url)}"
            )
            return [
                {
                    "tool": "http_request",
                    "args": {"method": "GET", "url": url, "timeout": 20},
                    "detail": "Fallback HTTP setelah web_extract gagal",
                    "stop_on_success": True,
                },
                {
                    "tool": "terminal",
                    "args": {"command": curl_command, "timeout": 25},
                    "detail": "Fallback curl setelah web_extract gagal",
                    "stop_on_success": True,
                },
            ]

        if tool_name == "http_request" and url:
            curl_command = (
                "curl -L -sS --max-time 20 "
                f"-A {shlex.quote('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')} "
                f"{shlex.quote(url)}"
            )
            return [
                {
                    "tool": "terminal",
                    "args": {"command": curl_command, "timeout": 25},
                    "detail": "Fallback curl setelah HTTP request gagal",
                    "stop_on_success": True,
                },
                {
                    "tool": "browser_open",
                    "args": {"url": url, "wait": 5},
                    "detail": "Fallback Chromium kalau HTTP langsung gagal",
                    "stop_on_success": True,
                },
            ]

        return []

    def _merge_fallback_result(
        self,
        original_tool: str,
        original_result: str,
        fallbacks: List[Dict[str, Any]],
        recovered: bool,
    ) -> str:
        payload = {
            "recovered": recovered,
            "primary_tool": original_tool,
            "primary_result": self._tool_result_data(original_result),
            "fallbacks": fallbacks,
        }
        if not recovered:
            payload["error"] = "Primary tool and automatic fallbacks failed"
        return json.dumps(payload, ensure_ascii=False, default=str)

    def _extract_result_files(self, value: Any) -> List[str]:
        """Find local files returned by tools so UIs can upload them."""
        found: List[str] = []

        def visit(item: Any):
            if isinstance(item, dict):
                for key, child in item.items():
                    if key in {"output", "file", "path", "screenshot", "audio_path", "video_path", "image_path"}:
                        visit(child)
                    elif isinstance(child, (dict, list, tuple)):
                        visit(child)
            elif isinstance(item, (list, tuple)):
                for child in item:
                    visit(child)
            elif isinstance(item, str):
                path = os.path.expanduser(item.strip().strip("\"'"))
                if os.path.isfile(path) and path not in found:
                    found.append(path)

        visit(value)
        return found

    def _build_prompt(
        self,
        user_msg: str = "",
        include_history: bool = True,
        tool_names: Optional[List[str]] = None,
    ) -> str:
        active_tools = tool_names or [s["function"]["name"] for s in self.tools_schema]
        tools_desc = build_tools_description(active_tools)
        tool_policy = (
            "\n\nACTIVE TOOL POLICY:\n"
            "- Only call tools listed in AVAILABLE TOOLS DETAIL below.\n"
            "- For simple tasks, use at most one or two tools, then answer.\n"
            "- After any successful tool result, decide whether the user's original request is satisfied.\n"
            "- Do not call diagnostic, memory, planning, or delegation tools unless the user explicitly asks for them.\n"
            "- Final answers must be grounded in observed tool evidence when tools were used.\n"
        )
        base_prompt = re.sub(
            r"\nAVAILABLE TOOLS \(48\):.*?\n\nRULES:",
            "\nRULES:",
            SYSTEM_PROMPT,
            flags=re.DOTALL,
        )
        sys_prompt = base_prompt + tool_policy + f"\nAVAILABLE TOOLS DETAIL:\n{tools_desc}\n"

        parts = [sys_prompt]

        mem = self.memory.summary()
        if mem and mem != "(empty)":
            parts.append(f"\n# PERSISTENT MEMORY:\n{mem}\n")

        lessons = self._recent_agent_lessons()
        if lessons:
            parts.append(
                "\n# RECENT AGENT LESSONS:\n"
                "Use these as lightweight operating hints. Do not mention them unless relevant.\n"
                f"{lessons}\n"
            )

        if include_history and self.history:
            parts.append("\n--- CONVERSATION HISTORY ---")
            for msg in self.history[-20:]:
                role = msg["role"]
                content = msg["content"][:1500]
                parts.append(f"\n[{role}]:\n{content}")
            parts.append("\n--- END HISTORY ---")

        if user_msg:
            parts.append(f"\n[User]:\n{user_msg}")

        parts.append("\n[Assistant]:")
        return "\n".join(parts)

    def _is_tool_call_marker(self, text: str) -> bool:
        """Check if text contains or MIGHT contain a tool call ANYWHERE."""
        markers = [TOOL_CALL_OPEN, '<tool_call>', '```json', '{"tool']
        if any(m in text for m in markers):
            return True
        # Search for tool call JSON anywhere in text (not just start)
        if '"tool"' in text and '"args"' in text:
            return True
        if '"tool"' in text and '{' in text:
            return True
        stripped = text.strip()
        if stripped.startswith('{') and ('tool' in stripped or 'args' in stripped):
            return True
        if stripped.startswith('{"') and len(stripped) < 300:
            return True
        if stripped.startswith('{') and len(stripped) < 50:
            return True
        # Detect partial JSON tool call start
        if re.search(r'\{\s*"tool"\s*:', text):
            return True
        return False

    def _extract_tool_call_from_text(self, text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Extract tool call JSON from text that may have explanation before it."""
        # Try to find {"tool": ...} pattern anywhere in text
        match = re.search(r'\{\s*"tool"\s*:\s*"([^"]+)"\s*,\s*"args"\s*:\s*\{', text)
        if match:
            tool_name = match.group(1)
            start = match.start()
            # Find balanced braces
            depth = 0
            i = start
            in_string = False
            escape = False
            while i < len(text):
                ch = text[i]
                if escape:
                    escape = False
                elif ch == '\\':
                    escape = True
                elif ch == '"':
                    in_string = not in_string
                elif not in_string:
                    if ch == '{':
                        depth += 1
                    elif ch == '}':
                        depth -= 1
                        if depth == 0:
                            json_str = text[start:i+1]
                            try:
                                obj = json.loads(json_str)
                                if "tool" in obj:
                                    return obj["tool"], obj.get("args", {})
                            except json.JSONDecodeError:
                                pass
                            break
                i += 1
        return None

    def _strip_tool_artifacts(self, text: str) -> str:
        text = re.sub(
            r'<tool_call>\s*\{.*?\}\s*</tool_call>',
            '', text, flags=re.DOTALL
        )
        text = re.sub(
            r'```json\s*\{[^`]*?"tool"[^`]*?\}\s*```',
            '', text, flags=re.DOTALL
        )
        return text.strip()

    def _clean_markdown(self, text: str) -> str:
        """Strip markdown artifacts that don't render in terminal."""
        text = re.sub(r'```\w*\n?(.*?)```', r'\1', text, flags=re.DOTALL)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'\(citation:\d+\)', '', text)

        # Replace @@@@@@@ separators with ──────────
        text = re.sub(r'@{4,}', '────────────────────────────────────────', text)

        # Fix garbled UTF-8 box-drawing chars (âââ -> ───)
        # The byte sequence for ─ (U+2500) in UTF-8 is E2 94 80
        # When misread, it shows as â followed by garbled chars
        text = re.sub(r'â[\x94\x80\x00-\x1F]{0,2}', '─', text)
        text = re.sub(r'â{2,}', '────────────────────────────────────────', text)
        # Single â that's likely a garbled char
        text = re.sub(r'(?<!\w)â(?!\w)', '─', text)

        # Fix common garbled UTF-8 sequences
        replacements = {
            'â\x80\x99': "'",   # right single quote
            'â\x80\x9C': '"',   # left double quote
            'â\x80\x9D': '"',   # right double quote
            'â\x80\x93': '-',   # en dash
            'â\x80\x94': '--',  # em dash
            'Ã¡': 'a',
            'Ã©': 'e',
            'Ã­': 'i',
            'Ã³': 'o',
            'Ãº': 'u',
            'Ã±': 'n',
        }
        for bad, good in replacements.items():
            text = text.replace(bad, good)

        # Catch remaining â sequences (any â followed by non-ASCII)
        text = re.sub(r'â[\x80-\xbf][\x80-\xbf]', '', text)

        # Clean up multiple blank lines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def chat_stream(self, user_msg: str, progress_callback: Optional[ProgressCallback] = None) -> str:
        """
        Full agentic chat loop:
        1. Fix typos in user input
        2. Send prompt to MiMo
        3. Stream response — show think tags dim, hide tool call JSON
        4. If tool call detected -> execute -> feed result back -> loop
        5. If no tool call -> final answer with bordered box
        """
        # Auto-fix typos
        callback = progress_callback or self.progress_callback
        chat_started = time.time()
        last_think_emit = 0.0
        self._emit_progress(callback, "queued", detail="Task masuk antrean agent")
        self._emit_progress(callback, "start", detail="Menerima task dan menyiapkan agent")

        original_msg = user_msg
        user_msg = fix_typo(user_msg)
        if user_msg != original_msg and not self.quiet:
            sys.stdout.write(f"{C.DIM}\u2502 typo corrected: {original_msg} -> {user_msg}{C.X}\n")
        if user_msg != original_msg:
            self._emit_progress(
                callback,
                "input_fixed",
                detail=f"Typo corrected: {self._safe_preview(original_msg)} -> {self._safe_preview(user_msg)}",
            )

        # Fix URL typos in the message
        urls = re.findall(r'https?://\S+', user_msg)
        for url in urls:
            fixed_url = fix_url_typo(url)
            if fixed_url != url:
                user_msg = user_msg.replace(url, fixed_url)
                if not self.quiet:
                    sys.stdout.write(f"{C.DIM}\u2502 url fixed: {url} -> {fixed_url}{C.X}\n")

        learned = self._learn_from_user_message(user_msg)
        if learned:
            self._record_agent_lesson("user_preference", ", ".join(learned), user_msg)
            self._emit_progress(
                callback,
                "memory",
                detail=f"Menyimpan preferensi eksplisit: {', '.join(learned)}",
            )

        self.history.append({"role": "User", "content": user_msg})
        self._emit_progress(callback, "planning", detail="Membangun prompt, memory, dan tool context")

        active_tool_names = self._select_tool_names(user_msg)
        active_tool_set = set(active_tool_names)
        self._emit_progress(
            callback,
            "tool_scope",
            detail=f"Tool aktif: {', '.join(active_tool_names[:12])}" + ("..." if len(active_tool_names) > 12 else ""),
            tools=active_tool_names,
        )

        prompt = self._build_prompt(user_msg, include_history=True, tool_names=active_tool_names)

        full_answer = ""
        tool_calls_count = 0
        spinner = None
        timed_out = False
        effective_max_tool_calls = self._task_tool_budget(user_msg)
        budget_warning_sent = False
        tool_trace: List[str] = []
        empty_response_retries = 0
        invalid_tool_retries = 0
        tool_call_counts: Dict[str, int] = {}
        self._emit_progress(
            callback,
            "budget",
            detail=f"Tool budget task ini {self._tool_budget_label(effective_max_tool_calls)}",
            tool_calls=0,
            max_tool_calls=effective_max_tool_calls,
        )

        def emit_budget_warning_if_needed(current_count: int):
            nonlocal budget_warning_sent
            if self.max_tool_calls <= 0:
                return
            remaining_tool_calls = effective_max_tool_calls - current_count
            if remaining_tool_calls <= 3 and not budget_warning_sent:
                budget_warning_sent = True
                self._emit_progress(
                    callback,
                    "budget_warning",
                    detail=f"Sisa {remaining_tool_calls} tool call, mulai rangkum progres atau finalkan jawaban",
                    tool_calls=current_count,
                    max_tool_calls=effective_max_tool_calls,
                )

        def execute_tool_call(
            current_tool: str,
            current_args: Dict[str, Any],
            current_count: int,
            prefix_event: Optional[str] = None,
            prefix_detail: str = "",
        ) -> Tuple[str, str, float, List[str]]:
            if prefix_event:
                self._emit_progress(
                    callback,
                    prefix_event,
                    tool=current_tool,
                    detail=prefix_detail or self._fallback_hint(current_tool, current_args, ""),
                    tool_calls=current_count,
                    max_tool_calls=effective_max_tool_calls,
                )

            args_summary = self._summarize_tool_args(current_tool, current_args)
            self._emit_progress(
                callback,
                "tool_start",
                tool=current_tool,
                detail=args_summary,
                args=args_summary,
                tool_calls=current_count,
                max_tool_calls=effective_max_tool_calls,
            )

            if not self.quiet:
                sys.stdout.write("\r\033[2K")
                _print_preparing(current_tool)

            tool_start = time.time()
            tool_result = call_tool(current_tool, current_args)
            tool_duration = time.time() - tool_start
            tool_status = self._tool_result_status(tool_result)
            tool_files: List[str] = []
            try:
                tool_files = self._extract_result_files(json.loads(tool_result))
            except Exception:
                tool_files = []

            self._emit_progress(
                callback,
                "tool_result",
                tool=current_tool,
                detail=self._summarize_tool_result(tool_result),
                status=tool_status,
                duration=tool_duration,
                tool_calls=current_count,
                max_tool_calls=effective_max_tool_calls,
                files=tool_files,
                next_step=self._fallback_hint(current_tool, current_args, tool_result),
            )
            tool_trace.append(
                f"{current_count}. {current_tool} {tool_status}: {self._summarize_tool_result(tool_result)}"
            )

            if not self.quiet:
                _print_tool_execution(current_tool, current_args, tool_duration)
                _print_tool_result(current_tool, tool_result)

            return tool_result, tool_status, tool_duration, tool_files

        while tool_calls_count < effective_max_tool_calls:
            elapsed = time.time() - chat_started
            if self.max_runtime and elapsed > self.max_runtime:
                timed_out = True
                self._emit_progress(
                    callback,
                    "timeout",
                    detail=f"Task dihentikan setelah {int(elapsed)}s agar tidak stuck",
                )
                full_answer += (
                    f"\nTask dihentikan setelah {int(elapsed)}s agar tidak stuck.\n"
                    "Yang sudah dicoba ada di progress. Coba pecah task atau kirim ulang dengan target yang lebih spesifik."
                )
                break

            if not self.quiet:
                spinner = Spinner("Thinking", style="thinking", color=C.C)
                spinner.start()
            self._emit_progress(
                callback,
                "model_start",
                detail="MiMo sedang menentukan langkah berikutnya",
                tool_calls=tool_calls_count,
                max_tool_calls=effective_max_tool_calls,
            )

            response = ""
            answer_parts = []
            tool_parts = []
            think_parts = []
            first_chunk = True
            safe_buffer = ""
            is_tool_mode = False

            for kind, text in self.client.chat_stream(
                prompt, web_search=self.web_search, enable_thinking=self.show_thinking
            ):
                if first_chunk and spinner:
                    spinner.stop()
                    spinner = None
                    first_chunk = False

                if kind == "error":
                    self._emit_progress(callback, "model_error", detail=self._safe_preview(text, 220))
                    if not self.quiet:
                        sys.stdout.write(f"\n{C.R}Error: {text}{C.X}\n")
                    break

                elif kind == "think":
                    think_parts.append(text)
                    now = time.time()
                    if now - last_think_emit >= 5:
                        self._emit_progress(callback, "thinking", detail="MiMo masih menganalisis langkah")
                        last_think_emit = now
                    if self.show_thinking and not self.quiet:
                        compact = text.replace('\n', ' ').strip()
                        if len(compact) > 80:
                            compact = compact[:80] + "..."
                        if compact:
                            sys.stdout.write(f"\r\033[2K{C.THINK}\u2502 {compact}{C.X}")
                            sys.stdout.flush()

                elif kind == "tool":
                    tool_parts.append(text)
                    is_tool_mode = True

                elif kind == "answer":
                    response += text
                    answer_parts.append(text)

                    if is_tool_mode:
                        continue

                    # Buffer ALL text — don't flush until we know it's not a tool call
                    safe_buffer += text

                    # Check if buffer contains tool call markers
                    if self._is_tool_call_marker(safe_buffer):
                        is_tool_mode = True
                        continue

                    # Show thinking indicator while buffering
                    if len(safe_buffer) > 100 and not self.quiet:
                        # Just show a subtle "processing" indicator
                        pass

            # Stream ended — check if this is a tool call or final answer
            if spinner:
                spinner.stop()

            full_response = "".join(answer_parts) + "".join(tool_parts)

            # Try multiple parsing strategies
            tool_call = parse_tool_call(full_response)

            # Fallback: extract tool call from text that has explanation before JSON
            if tool_call is None:
                tool_call = self._extract_tool_call_from_text(full_response)

            if tool_call is None:
                answer_text = "".join(answer_parts)
                cleaned_answer = self._clean_markdown(answer_text)
                cleaned_answer = re.sub(r'\(citation:\d+\)', '', cleaned_answer)
                if not cleaned_answer.strip():
                    empty_response_retries += 1
                    fallback_call = self._empty_response_fallback_call(user_msg, empty_response_retries)
                    if fallback_call and tool_calls_count < effective_max_tool_calls:
                        tool_call = fallback_call
                        self._emit_progress(
                            callback,
                            "fallback",
                            tool=tool_call[0],
                            detail="Model tidak memberi jawaban/tool call; menjalankan fallback otomatis dari URL user",
                            tool_calls=tool_calls_count,
                            max_tool_calls=effective_max_tool_calls,
                        )
                    elif empty_response_retries <= 2:
                        self._emit_progress(
                            callback,
                            "retry",
                            detail="Model memberi response kosong; minta langkah konkret berikutnya",
                            tool_calls=tool_calls_count,
                            max_tool_calls=effective_max_tool_calls,
                        )
                        self.history.append({
                            "role": "Tool",
                            "content": (
                                "Previous model turn returned no final answer and no tool call. "
                                "Continue now with either a valid tool call JSON or a concise final answer. "
                                "Do not return an empty response."
                            ),
                        })
                        prompt = self._build_prompt("", include_history=True, tool_names=active_tool_names)
                        continue
                    else:
                        self._emit_progress(
                            callback,
                            "model_error",
                            detail="Model tetap memberi response kosong setelah retry",
                        )
                        full_answer += (
                            "Agent tidak menghasilkan jawaban setelah retry. "
                            "Task belum bisa diselesaikan dari response model kosong."
                        )
                        break

            if tool_call is None:
                # This is a final answer — flush the buffered text
                answer_text = "".join(answer_parts)
                cleaned_answer = self._clean_markdown(answer_text)
                cleaned_answer = re.sub(r'\(citation:\d+\)', '', cleaned_answer)
                self._emit_progress(callback, "finalizing", detail="Menyusun jawaban final")
                if cleaned_answer and not self.quiet:
                    sys.stdout.write(cleaned_answer)
                    sys.stdout.flush()
                full_answer += answer_text
                break

            tool_name, args = tool_call
            if tool_name not in active_tool_set:
                invalid_tool_retries += 1
                self._emit_progress(
                    callback,
                    "retry",
                    tool=tool_name,
                    detail="Model memilih tool di luar scope task; minta pilih tool aktif atau finalkan",
                    tool_calls=tool_calls_count,
                    max_tool_calls=effective_max_tool_calls,
                )
                self.history.append({
                    "role": "Tool",
                    "content": (
                        f"Rejected tool '{tool_name}' because it is outside the active tool scope. "
                        f"Active tools: {', '.join(active_tool_names)}. "
                        "Use one of those tools only, or produce the final answer if enough evidence exists."
                    ),
                })
                if invalid_tool_retries > 2:
                    full_answer += (
                        f"Agent mencoba memakai tool di luar scope task ({tool_name}) berulang kali. "
                        "Task dihentikan supaya tidak muter."
                    )
                    break
                prompt = self._build_prompt("", include_history=True, tool_names=active_tool_names)
                continue

            remaining_runtime = None
            if self.max_runtime:
                remaining_runtime = self.max_runtime - (time.time() - chat_started)
                if remaining_runtime <= 8:
                    timed_out = True
                    self._emit_progress(
                        callback,
                        "timeout",
                        detail="Sisa runtime terlalu kecil untuk menjalankan tool berikutnya",
                    )
                    full_answer += (
                        "Task dihentikan karena sisa runtime terlalu kecil untuk menjalankan tool berikutnya. "
                        "Progress terakhir ada di trace."
                    )
                    break

            args, normalize_notes = self._normalize_tool_args(tool_name, args, remaining_runtime)
            if normalize_notes:
                self._record_agent_lesson(
                    "tool_args_adjusted",
                    f"{tool_name}: {', '.join(normalize_notes)}",
                    self._summarize_tool_args(tool_name, args),
                )
                self._emit_progress(
                    callback,
                    "tool_args_adjusted",
                    tool=tool_name,
                    detail=", ".join(normalize_notes),
                    tool_calls=tool_calls_count,
                    max_tool_calls=effective_max_tool_calls,
                )

            tool_key = self._tool_call_key(tool_name, args)
            tool_call_counts[tool_key] = tool_call_counts.get(tool_key, 0) + 1
            if tool_call_counts[tool_key] > 1:
                self._emit_progress(
                    callback,
                    "retry",
                    tool=tool_name,
                    detail="Tool dan argumen yang sama sudah dipakai; cegah loop berulang",
                    tool_calls=tool_calls_count,
                    max_tool_calls=effective_max_tool_calls,
                )
                self.history.append({
                    "role": "Tool",
                    "content": (
                        f"Rejected repeated tool call '{tool_name}' with the same arguments. "
                        "Use the existing observation, choose a different fallback, or produce the final answer. "
                        "Do not repeat identical tool calls."
                    ),
                })
                if tool_call_counts[tool_key] > 2:
                    full_answer += (
                        f"Agent mengulang tool yang sama ({tool_name}) tanpa progress. "
                        "Task dihentikan supaya tidak muter."
                    )
                    break
                prompt = self._build_prompt("", include_history=True, tool_names=active_tool_names)
                continue

            empty_response_retries = 0
            invalid_tool_retries = 0
            tool_calls_count += 1
            emit_budget_warning_if_needed(tool_calls_count)
            result, result_status, _tool_duration, _result_files = execute_tool_call(
                tool_name,
                args,
                tool_calls_count,
            )

            fallback_records: List[Dict[str, Any]] = []
            if result_status == "error":
                original_result = result
                self._emit_progress(
                    callback,
                    "retry",
                    tool=tool_name,
                    detail=self._fallback_hint(tool_name, args, result),
                    tool_calls=tool_calls_count,
                    max_tool_calls=effective_max_tool_calls,
                )
                for step in self._fallback_steps(tool_name, args, result):
                    if tool_calls_count >= effective_max_tool_calls:
                        break
                    tool_calls_count += 1
                    emit_budget_warning_if_needed(tool_calls_count)
                    fallback_tool = step["tool"]
                    fallback_args = step.get("args", {})
                    fallback_result, fallback_status, fallback_duration, fallback_files = execute_tool_call(
                        fallback_tool,
                        fallback_args,
                        tool_calls_count,
                        prefix_event="fallback",
                        prefix_detail=step.get("detail", ""),
                    )
                    fallback_records.append({
                        "tool": fallback_tool,
                        "args": self._summarize_tool_args(fallback_tool, fallback_args),
                        "status": fallback_status,
                        "duration": round(fallback_duration, 3),
                        "summary": self._summarize_tool_result(fallback_result),
                        "files": fallback_files,
                        "result": self._tool_result_data(fallback_result),
                    })
                    if step.get("stop_on_success", True) and fallback_status == "ok":
                        result = self._merge_fallback_result(
                            tool_name,
                            original_result,
                            fallback_records,
                            recovered=True,
                        )
                        result_status = "ok"
                        break
                if fallback_records and result_status == "error":
                    result = self._merge_fallback_result(
                        tool_name,
                        original_result,
                        fallback_records,
                        recovered=False,
                    )

            # Add tool result to history
            fallback_hint = self._fallback_hint(tool_name, args, result)
            evidence = self._tool_evidence(tool_name, args, result, result_status)
            tool_msg = (
                f"Tool '{tool_name}' returned ({result_status}):\n"
                f"```json\n{result[:3000]}\n```\n"
                f"Local verification: {evidence['verdict']}\n"
                f"Evidence: {evidence['evidence']}\n"
                f"Decision guidance: {evidence['instruction']}\n"
                f"Next planning hint: {fallback_hint}"
            )
            self.history.append({"role": "Tool", "content": tool_msg})

            prompt = self._build_prompt("", include_history=True, tool_names=active_tool_names)

        if self.max_tool_calls > 0 and tool_calls_count >= effective_max_tool_calls:
            self._emit_progress(
                callback,
                "max_tool_calls",
                detail=f"Max tool calls ({effective_max_tool_calls}) tercapai; rangkum progres dan minta lanjut jika perlu",
                tool_calls=tool_calls_count,
                max_tool_calls=effective_max_tool_calls,
            )
            if not full_answer.strip():
                full_answer += (
                    f"\nTool budget task ini habis setelah {effective_max_tool_calls} calls.\n"
                )
            if tool_trace:
                recent_trace = "\n".join(f"- {item}" for item in tool_trace[-8:])
                full_answer += (
                    "\nProgress terakhir:\n"
                    f"{recent_trace}\n\n"
                    "Kirim 'lanjut' untuk meneruskan dari state terakhir."
                )
            if not self.quiet:
                sys.stdout.write(f"\n{C.Y}[Max tool calls ({effective_max_tool_calls}) reached]{C.X}\n")

        # Synthesizing animation before final answer
        if not self.quiet and tool_calls_count > 0:
            _print_synthesizing()

        # Clean and save
        cleaned = self._strip_tool_artifacts(full_answer)
        cleaned = self._clean_markdown(cleaned)

        # Print final answer in bordered box (Hermes-style)
        if cleaned and not self.quiet:
            _print_border(cleaned, color=C.C)

        if cleaned:
            self.history.append({"role": "Assistant", "content": cleaned})
        self._emit_progress(
            callback,
            "final",
            detail="Jawaban final siap",
            duration=time.time() - chat_started,
        )
        self._emit_progress(
            callback,
            "done" if not timed_out else "stopped",
            detail=f"Selesai dalam {int(time.time() - chat_started)}s",
            duration=time.time() - chat_started,
        )
        self._record_session_trace(
            user_msg=user_msg,
            answer=cleaned or full_answer,
            tool_trace=tool_trace,
            status="stopped" if timed_out else "done",
            duration=time.time() - chat_started,
            active_tools=active_tool_names,
        )
        return cleaned or full_answer

    def chat(self, user_msg: str, progress_callback: Optional[ProgressCallback] = None) -> str:
        return self.chat_stream(user_msg, progress_callback=progress_callback)

    def reset(self):
        self.history = []
        self.client.new_conversation()

    def remember(self, key: str, value: str):
        if key == "fact":
            self.memory.add_fact(value)
        elif key == "pref":
            if "=" in value:
                k, v = value.split("=", 1)
                self.memory.set_pref(k.strip(), v.strip())
            else:
                self.memory.add_fact(value)
        else:
            self.memory.add_note(value)


if __name__ == "__main__":
    agent = MiMoAgent()
    print(f"{C.BOLD}MiMo Agent{C.X} \u2014 model: {agent.client.model}\n")
    while True:
        try:
            user_input = input(f"{C.BOLD}{C.C}You:{C.X} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if user_input.lower() == "reset":
            agent.reset()
            print(f"{C.G}history cleared{C.X}\n")
            continue
        print(f"{C.BOLD}{C.G}MiMo:{C.X} ", end="", flush=True)
        try:
            agent.chat_stream(user_input)
        except KeyboardInterrupt:
            print(f"\n{C.Y}interrupted{C.X}")
        print("\n")
