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
import sys
import threading
import itertools
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from mimo_client import MiMoClient, LT, GT, THINK_OPEN, THINK_CLOSE
from tools import get_tools_schema, call_tool

# ─── Smooth Spinner ──────────────────────────────────────────────────────────

THINKING_FRAMES = ["\u280b", "\u2819", "\u2839", "\u2838", "\u283c", "\u2834", "\u2826", "\u2827", "\u2807", "\u280f"]
PROGRESS_FRAMES = [
    "\u25b0\u25b1\u25b1\u25b1\u25b1\u25b1\u25b1\u25b1\u25b1\u25b1",
    "\u25b0\u25b0\u25b1\u25b1\u25b1\u25b1\u25b1\u25b1\u25b1\u25b1",
    "\u25b0\u25b0\u25b0\u25b1\u25b1\u25b1\u25b1\u25b1\u25b1\u25b1",
    "\u25b0\u25b0\u25b0\u25b0\u25b1\u25b1\u25b1\u25b1\u25b1\u25b1",
    "\u25b0\u25b0\u25b0\u25b0\u25b0\u25b1\u25b1\u25b1\u25b1\u25b1",
    "\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b1\u25b1\u25b1\u25b1",
    "\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b1\u25b1\u25b1",
    "\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b1\u25b1",
    "\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b1",
    "\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0\u25b0",
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

SYSTEM_PROMPT = """You are MiMo Agent — an advanced agentic AI assistant with 53 tools. You are a problem-solver, not just an answer-giver. You are FAST and EFFICIENT.

TOOL CALL FORMAT — when you need a tool, output EXACTLY this JSON (no markdown wrapping, no explanation before it):
{"tool": "tool_name", "args": {"param": "value"}}

After receiving tool results, continue reasoning and answer naturally in the user's language.

=== SPEED RULES (IMPORTANT!) ===

1. MINIMIZE TOOL CALLS — use the FEWEST tools possible to achieve the goal
2. DON'T EXPLORE UNNECESSARILY — if you know what to do, just DO IT
3. COMBINE STEPS — one browser call is better than three
4. SKIP VERBOSE OUTPUT — don't explain your plan, just execute

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
    │ Username     │ @Gendot6449  │
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


def build_tools_description() -> str:
    schemas = get_tools_schema()
    lines = []
    for s in schemas:
        fn = s["function"]
        name = fn["name"]
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
    "web_search": "\U0001f310",        # 🌐
    "web_extract": "\U0001f4c4",       # 📄
    "read_file": "\U0001f4d6",         # 📖
    "write_file": "\u270f\ufe0f",      # ✏️
    "append_file": "\U0001f4dd",       # 📝
    "patch_file": "\U0001f527",        # 🔧
    "delete_file": "\U0001f5d1\ufe0f", # 🗑️
    "search_files": "\U0001f50d",      # 🔍
    "terminal": "\U0001f4bb",          # 💻
    "execute_python": "\U0001f40d",    # 🐍
    "list_directory": "\U0001f4c1",    # 📁
    "file_info": "\U0001f4cb",         # 📋
    "create_directory": "\U0001f4c2",  # 📂
    "copy_path": "\U0001f4cb",         # 📋
    "move_path": "\U0001f4e6",         # 📦
    "move_to_trash": "\U0001f5d1\ufe0f", # 🗑️
    "find_files": "\U0001f50e",        # 🔎
    "list_tree": "\U0001f333",         # 🌳
    "replace_in_file": "\U0001f504",   # 🔄
    "text_diff": "\U0001f50d",         # 🔍
    "code_outline": "\U0001f4d1",      # 📑
    "project_map": "\U0001f5fa\ufe0f", # 🗺️
    "read_json": "\U0001f4ca",         # 📊
    "write_json": "\U0001f4ca",        # 📊
    "json_query": "\U0001f50d",        # 🔍
    "csv_preview": "\U0001f4ca",       # 📊
    "sqlite_query": "\U0001f5c4\ufe0f", # 🗄️
    "http_request": "\U0001f310",      # 🌐
    "download_file": "\u2b07\ufe0f",   # ⬇️
    "create_archive": "\U0001f4e6",    # 📦
    "extract_archive": "\U0001f4e6",   # 📦
    "git_status": "\U0001f500",        # 🔀
    "git_diff": "\U0001f500",          # 🔀
    "git_log": "\U0001f4dc",           # 📜
    "git_show": "\U0001f4dc",          # 📜
    "current_time": "\u23f0",          # ⏰
    "system_info": "\u2699\ufe0f",     # ⚙️
    "disk_usage": "\U0001f4be",        # 💾
    "process_list": "\U0001f5a5\ufe0f", # 🖥️
    "process_kill": "\u2620\ufe0f",    # ☠️
    "task_board": "\U0001f4cb",        # 📋
    "browser_open": "\U0001f310",      # 🌐
    "browser_get_text": "\U0001f4d6",  # 📖
    "browser_get_links": "\U0001f517", # 🔗
    "browser_click": "\U0001f446",     # 👆
    "browser_type": "\u2328\ufe0f",    # ⌨️
    "browser_evaluate": "\u26a1",      # ⚡
    "browser_wait_for": "\u23f3",      # ⏳
    "browser_close": "\U0001f50c",     # 🔌
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
    icon = TOOL_ICONS.get(tool_name, "\u2699\ufe0f")
    label = TOOL_LABELS.get(tool_name, f"Menjalankan {tool_name}...")
    sys.stdout.write(f"  {C.DIM}\u250a{C.X} {icon} {C.DIM}preparing {tool_name}...\033[0m")
    sys.stdout.flush()


def _print_tool_execution(tool_name: str, args: Dict[str, Any], duration: float):
    """Print tool execution line with command preview and timing (Hermes-style)."""
    icon = TOOL_ICONS.get(tool_name, "\u2699\ufe0f")
    time_str = _format_duration(duration)

    if tool_name in ("terminal", "execute_python"):
        cmd = args.get("command", args.get("code", ""))
        preview = cmd[:80].replace('\n', ' ')
        if len(cmd) > 80:
            preview += "..."
        print(f"\r\033[2K  {C.DIM}\u250a{C.X} {icon} {C.DIM}${preview}{C.X}  {C.DIM}{time_str}{C.X}")
    else:
        arg_preview = ", ".join(f"{k}={str(v)[:30]}" for k, v in list(args.items())[:2])
        print(f"\r\033[2K  {C.DIM}\u250a{C.X} {icon} {C.DIM}{tool_name}({arg_preview}){C.X}  {C.DIM}{time_str}{C.X}")


def _print_tool_result(tool_name: str, result: str):
    """Print tool result status line (Hermes-style)."""
    try:
        data = json.loads(result)
        if "error" in data:
            print(f"  {C.DIM}\u250a{C.X} {C.R}error:{C.X} {C.DIM}{str(data['error'])[:120]}{C.X}")
        else:
            if isinstance(data, dict):
                keys = list(data.keys())[:4]
                preview = ", ".join(keys)
                print(f"  {C.DIM}\u250a{C.X} {C.G}ok{C.X} {C.DIM}({preview}){C.X}")
            else:
                print(f"  {C.DIM}\u250a{C.X} {C.G}ok{C.X}")
    except json.JSONDecodeError:
        lines = result.strip().split('\n')
        print(f"  {C.DIM}\u250a{C.X} {C.G}ok{C.X} {C.DIM}({len(lines)} lines){C.X}")


def _print_synthesizing():
    """Print synthesizing animation (Hermes-style)."""
    frames = ["(◔_◔)", "(◑_◑)", "(◕_◕)", "(◔_◔)"]
    for frame in frames:
        sys.stdout.write(f"\r  {C.DIM}{frame} synthesizing...{C.X}")
        sys.stdout.flush()
        time.sleep(0.15)
    sys.stdout.write("\r\033[2K")
    sys.stdout.flush()


# ─── Agent ───────────────────────────────────────────────────────────────────

class MiMoAgent:
    """Hermes-grade agentic conversation manager."""

    def __init__(self, model: str = "mimo-v2.5-pro", web_search: bool = True,
                 show_thinking: bool = True, quiet: bool = False):
        self.client = MiMoClient(model=model)
        self.history: List[Dict[str, str]] = []
        self.web_search = web_search
        self.show_thinking = show_thinking
        self.quiet = quiet
        self.max_tool_calls = 8
        self.tools_schema = get_tools_schema()
        self.memory = Memory()

    def _build_prompt(self, user_msg: str = "", include_history: bool = True) -> str:
        tools_desc = build_tools_description()
        sys_prompt = SYSTEM_PROMPT + f"\n\nAVAILABLE TOOLS DETAIL:\n{tools_desc}\n"

        parts = [sys_prompt]

        mem = self.memory.summary()
        if mem and mem != "(empty)":
            parts.append(f"\n# PERSISTENT MEMORY:\n{mem}\n")

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

    def chat_stream(self, user_msg: str) -> str:
        """
        Full agentic chat loop:
        1. Fix typos in user input
        2. Send prompt to MiMo
        3. Stream response — show think tags dim, hide tool call JSON
        4. If tool call detected -> execute -> feed result back -> loop
        5. If no tool call -> final answer with bordered box
        """
        # Auto-fix typos
        original_msg = user_msg
        user_msg = fix_typo(user_msg)
        if user_msg != original_msg and not self.quiet:
            sys.stdout.write(f"{C.DIM}\u2502 typo corrected: {original_msg} -> {user_msg}{C.X}\n")

        # Fix URL typos in the message
        urls = re.findall(r'https?://\S+', user_msg)
        for url in urls:
            fixed_url = fix_url_typo(url)
            if fixed_url != url:
                user_msg = user_msg.replace(url, fixed_url)
                if not self.quiet:
                    sys.stdout.write(f"{C.DIM}\u2502 url fixed: {url} -> {fixed_url}{C.X}\n")

        self.history.append({"role": "User", "content": user_msg})

        prompt = self._build_prompt(user_msg, include_history=True)

        full_answer = ""
        tool_calls_count = 0
        spinner = None

        while tool_calls_count < self.max_tool_calls:
            if not self.quiet:
                spinner = Spinner("Thinking", style="thinking", color=C.C)
                spinner.start()

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
                    if not self.quiet:
                        sys.stdout.write(f"\n{C.R}Error: {text}{C.X}\n")
                    break

                elif kind == "think":
                    think_parts.append(text)
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
                # This is a final answer — flush the buffered text
                answer_text = "".join(answer_parts)
                cleaned_answer = self._clean_markdown(answer_text)
                cleaned_answer = re.sub(r'\(citation:\d+\)', '', cleaned_answer)
                if cleaned_answer and not self.quiet:
                    sys.stdout.write(cleaned_answer)
                    sys.stdout.flush()
                full_answer += answer_text
                break

            tool_name, args = tool_call
            tool_calls_count += 1

            # Clear thinking line before showing tool call
            if not self.quiet:
                sys.stdout.write("\r\033[2K")

            if not self.quiet:
                _print_preparing(tool_name)

            # Execute tool with timing
            tool_start = time.time()
            result = call_tool(tool_name, args)
            tool_duration = time.time() - tool_start

            if not self.quiet:
                _print_tool_execution(tool_name, args, tool_duration)
                _print_tool_result(tool_name, result)

            # Add tool result to history
            tool_msg = f"Tool '{tool_name}' returned:\n```json\n{result[:3000]}\n```"
            self.history.append({"role": "Tool", "content": tool_msg})

            prompt = self._build_prompt("", include_history=True)

        if tool_calls_count >= self.max_tool_calls:
            if not self.quiet:
                sys.stdout.write(f"\n{C.Y}[Max tool calls ({self.max_tool_calls}) reached]{C.X}\n")

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
        return cleaned or full_answer

    def chat(self, user_msg: str) -> str:
        return self.chat_stream(user_msg)

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
