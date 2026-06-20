#!/usr/bin/env python3
"""
mimo_client.py — MiMo session-based client with streaming + tool support.
Handles Hermes-style <tool_call> wrappers and <think> tags.
"""
import requests
import json
import re
import uuid
import os
import sys
import time
from typing import Optional, Generator, List, Tuple

BASE_URL = "https://aistudio.xiaomimimo.com/open-apis/bot/chat"
COOKIE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "session_cookie.txt")

# Tag patterns (using chr() to avoid encoding issues in source)
LT = chr(60)  # <
GT = chr(62)  # >

# Think tags (model internal reasoning)
THINK_OPEN = LT + "think" + GT
THINK_CLOSE = LT + "/think" + GT

# Tool call tags (Hermes-style)
TOOL_CALL_OPEN = LT + "tool_call" + GT
TOOL_CALL_CLOSE = LT + "/tool_call" + GT

# Invoke tags (alternative format)
INVOKE_OPEN = LT + "invoke" + GT
INVOKE_CLOSE = LT + "/invoke" + GT

# All wrapper patterns to strip
WRAPPER_TAGS = [
    (TOOL_CALL_OPEN, TOOL_CALL_CLOSE),
    (INVOKE_OPEN, INVOKE_CLOSE),
]


def load_cookie() -> str:
    env = os.environ.get("XIAOMI_COOKIE")
    if env:
        return env.strip()
    if os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    raise ValueError("Cookie tidak ditemukan. Set XIAOMI_COOKIE atau isi session_cookie.txt")


def extract_ph(cookie: str) -> str:
    m = re.search(r'xiaomichatbot_ph="?([^";]+)"?', cookie)
    return m.group(1) if m else ""


def new_id() -> str:
    return uuid.uuid4().hex


class MiMoClient:
    def __init__(self, cookie: Optional[str] = None, model: str = "mimo-v2.5-pro"):
        self.cookie = cookie or load_cookie()
        self.ph = extract_ph(self.cookie)
        self.model = model
        self.conversation_id = new_id()
        self.headers = {
            "content-type": "application/json",
            "accept": "*/*",
            "accept-language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
            "origin": "https://aistudio.xiaomimimo.com",
            "referer": "https://aistudio.xiaomimimo.com/",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36",
            "x-timezone": "Asia/Jakarta",
            "cookie": self.cookie,
        }
        # State machine: "normal", "in_think", "in_tool_call"
        self._state = "normal"
        self._tool_close_tag = TOOL_CALL_CLOSE

    def new_conversation(self):
        self.conversation_id = new_id()
        self._state = "normal"
        self._tool_close_tag = TOOL_CALL_CLOSE

    def _process_chunk_events(self, chunk: str) -> List[Tuple[str, str]]:
        """
        Process raw chunks into ("answer" | "think" | "tool", text) events.
        """
        if not chunk:
            return []

        events = []
        i = 0
        text = chunk

        def emit(kind: str, s: str):
            if s:
                events.append((kind, s.replace("\x00", "")))

        while i < len(text):
            if self._state == "in_think":
                close_idx = text.find(THINK_CLOSE, i)
                if close_idx == -1:
                    emit("think", text[i:])
                    break
                emit("think", text[i:close_idx])
                self._state = "normal"
                i = close_idx + len(THINK_CLOSE)
            elif self._state == "in_tool_call":
                close_idx = text.find(self._tool_close_tag, i)
                if close_idx == -1:
                    emit("tool", text[i:])
                    break
                emit("tool", text[i:close_idx])
                self._state = "normal"
                i = close_idx + len(self._tool_close_tag)
            else:
                earliest = -1
                opener = None
                opener_len = 0
                closer = None
                for open_tag, close_tag in WRAPPER_TAGS + [(THINK_OPEN, THINK_CLOSE)]:
                    idx = text.find(open_tag, i)
                    if idx != -1 and (earliest == -1 or idx < earliest):
                        earliest = idx
                        opener = open_tag
                        opener_len = len(open_tag)
                        closer = close_tag

                if earliest == -1:
                    emit("answer", text[i:])
                    break
                emit("answer", text[i:earliest])
                if opener == THINK_OPEN:
                    self._state = "in_think"
                else:
                    self._state = "in_tool_call"
                    self._tool_close_tag = closer or TOOL_CALL_CLOSE
                i = earliest + opener_len

        return events

    def _process_chunk(self, chunk: str) -> str:
        """Compatibility path: hide thinking, preserve answer/tool text."""
        parts = []
        for kind, text in self._process_chunk_events(chunk):
            if kind in ("answer", "tool"):
                parts.append(text)
        return "".join(parts)

    def chat_stream(
        self,
        query: str,
        web_search: bool = True,
        enable_thinking: Optional[bool] = None,
        event_mode: Optional[bool] = None,
    ) -> Generator:
        if event_mode is None:
            event_mode = enable_thinking is not None
        thinking_enabled = True if enable_thinking is None else bool(enable_thinking)

        payload = {
            "msgId": new_id(),
            "conversationId": self.conversation_id,
            "query": query,
            "isEditedQuery": False,
            "modelConfig": {
                "enableThinking": thinking_enabled,
                "webSearchStatus": "enabled" if web_search else "disabled",
                "model": self.model,
            },
            "multiMedias": [],
        }
        params = {"xiaomichatbot_ph": self.ph}

        # Reset state
        self._state = "normal"
        self._tool_close_tag = TOOL_CALL_CLOSE

        answer = ""
        try:
            with requests.post(BASE_URL, headers=self.headers, params=params, json=payload, stream=True, timeout=120) as resp:
                event_type = None
                for raw_line in resp.iter_lines(decode_unicode=True):
                    if raw_line is None:
                        continue
                    line = raw_line.strip()
                    if not line:
                        continue
                    if line.startswith("event:"):
                        event_type = line[len("event:"):].strip()
                        continue
                    if line.startswith("data:"):
                        data_str = line[len("data:"):].strip()
                        if event_type == "message":
                            try:
                                obj = json.loads(data_str)
                            except json.JSONDecodeError:
                                continue
                            raw_chunk = obj.get("content", "")
                            if not raw_chunk:
                                continue
                            events = self._process_chunk_events(raw_chunk)
                            for kind, text in events:
                                if event_mode:
                                    yield (kind, text)
                                elif kind in ("answer", "tool"):
                                    yield text
                                    answer += text
                        elif event_type == "finish":
                            break
        except requests.exceptions.RequestException as e:
            if event_mode:
                yield ("error", str(e))
            else:
                yield f"\n[Error: {e}]\n"

        return answer

    def chat(self, query: str, web_search: bool = False) -> str:
        answer = ""
        for chunk in self.chat_stream(query, web_search):
            answer += chunk
        return answer


if __name__ == "__main__":
    client = MiMoClient()
    print(f"MiMo Client — model: {client.model}")
    print()
    print("Test: Halo, siapa kamu?")
    print("MiMo: ", end="", flush=True)
    for chunk in client.chat_stream("Halo, siapa kamu? jawab singkat"):
        print(chunk, end="", flush=True)
    print()
