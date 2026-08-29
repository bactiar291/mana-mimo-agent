# 🤖 MiMo Agent

**72 verified tools | No API key needed | Runs on a MiMo session cookie**

An agentic assistant that plans, calls tools, and reports what it actually did.
Powered by MiMo v2.5 Pro through the AI Studio web session — no paid API key.

> **By [Bactiar 291](https://github.com/bactiar291)** — Open source, contributions welcome.

---

## ✨ What It Actually Does

Every capability below was executed in a real environment before being listed here.
Nothing is advertised that returns "not implemented" at call time.

- **72 active tools** — files, code, git, shell, Python, web, browser, OCR, TTS, memory, skills, delegation
- **Telegram gateway** — use it as a personal assistant in chat, with a live status card that updates in place while it works
- **Browser automation** — headless anti-detect Chromium via DrissionPage, with a Playwright engine option
- **Web research** — DuckDuckGo search with SearXNG/Wikipedia/Brave fallback, plus page extraction and raw HTTP
- **Persistent memory** — facts, preferences, and profile survive restarts
- **Skills** — reusable markdown procedures the agent can read and write
- **Subagent delegation** — hand an isolated task to a separate agent run
- **Evidence-first answers** — the system prompt forbids describing tool output that was never received

### Honest limits

| Not available | Why |
|---------------|-----|
| Email / SMS notifications | No SMTP or SMS provider is wired up |
| MCP client | JSON-RPC transport is not implemented |
| Audio transcription | Needs the `whisper` CLI, not installed by default |
| Image *content* understanding | `vision_analyze` returns metadata + OCR, not a vision model description |
| Crypto / NFT / DeFi tools | Not part of this repository |

A larger historical registry (204 tools) still ships in the source. Most of it was
unreachable, duplicated, or unimplemented, so it is filtered out by default. Set
`MIMO_TOOL_PROFILE=full` if you want to inspect it.

---

## 🚀 Quick Start

### Step 1: Get your MiMo session cookie (free)

1. Open [aistudio.xiaomimimo.com](https://aistudio.xiaomimimo.com/) and log in with a Xiaomi account
2. Press **F12** → **Application** tab → **Cookies** → `https://aistudio.xiaomimimo.com`
3. Copy the full cookie string (it must include `xiaomichatbot_ph=...` — that value is what the client parses)

> ⚠️ The cookie expires after days or weeks. If the agent starts returning auth errors, grab a fresh one.
> Never share it: it grants full access to your MiMo account.

### Step 2: Create a Telegram bot

1. Message [@BotFather](https://t.me/BotFather) → `/newbot`
2. Pick a name, then a username ending in `bot`
3. Copy the token it returns

### Step 3: Install

```bash
git clone https://github.com/bactiar291/mimo-agent.git
cd mimo-agent

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 4: Configure

The cookie goes in `core/session_cookie.txt` (or the `XIAOMI_COOKIE` env var):

```bash
cp session_cookie.txt.example core/session_cookie.txt
# paste your cookie string into core/session_cookie.txt
```

Telegram settings live in `config/telegram.json`:

```json
{
  "telegram_token": "123456789:ABCdef...",
  "telegram_chat_id": "YOUR_NUMERIC_CHAT_ID",
  "telegram_admin_chat_ids": [],
  "telegram_admin_password": "change-me",
  "model": "mimo-v2.5-pro",
  "web_search": true,
  "show_thinking": true,
  "max_tool_calls": 0
}
```

`max_tool_calls: 0` means runtime-bounded instead of a fixed call cap; the runtime
limit and per-tool timeouts still apply.

### Step 5: Run

```bash
python start_tg.py     # Telegram gateway
python p.py            # CLI chat
```

---

## 🛠️ Tool Surface (72)

| Category | Tools |
|----------|-------|
| **File & code** (22) | `read_file`, `write_file`, `append_file`, `patch_file`, `replace_in_file`, `file_info`, `find_files`, `search_files`, `list_directory`, `list_tree`, `create_directory`, `copy_path`, `move_path`, `move_to_trash`, `text_diff`, `read_json`, `csv_preview`, `code_outline`, `project_map`, `create_archive`, `extract_archive`, `sqlite_query` |
| **Git** (4) | `git_status`, `git_diff`, `git_log`, `git_show` |
| **Shell & system** (6) | `terminal`, `execute_python`, `system_info`, `process_list`, `process_kill`, `disk_usage` |
| **Web** (4) | `web_search`, `web_extract`, `http_request`, `download_file` |
| **Browser** (15) | `browser_open`, `browser_get_text`, `browser_get_links`, `browser_click`, `browser_type`, `browser_press`, `browser_scroll`, `browser_evaluate`, `browser_console`, `browser_snapshot`, `browser_screenshot`, `browser_wait_for`, `browser_status`, `browser_close`, `browser_set_engine` |
| **Media** (7) | `vision_ocr`, `vision_screenshot`, `vision_analyze`, `vision_compare`, `voice_tts`, `voice_list`, `voice_info` |
| **Agent state** (11) | `memory`, `memory_facts`, `memory_preferences`, `memory_profile`, `todo`, `current_time`, `skill_view`, `skill_manage`, `skills_list`, `delegate_task`, `delegate_status` |
| **Notify** (3) | `notify_telegram`, `notify_discord`, `notify_slack` |

`/tools` and `/status` in Telegram report the live count and the active profile.

---

## 🔧 Repository Layout

```
mimo-agent/
├── core/
│   ├── agent.py            # Agent loop, system prompt, tool routing
│   ├── mimo_client.py      # MiMo session client (SSE streaming, think tags)
│   ├── main.py             # CLI entry logic
│   └── session_cookie.txt  # Your cookie (gitignored)
├── tools/
│   ├── tools.py            # Core registry + most tool implementations
│   ├── tool_profile.py     # Which tools are honestly exposed
│   ├── vision.py voice.py  # OCR / screenshot / TTS
│   ├── deep_audit.py       # Executable tool + agent-loop audit
│   └── ...                 # Optional subsystems (filtered out by default)
├── lib/
│   ├── browser_engine.py   # DrissionPage / Playwright driver
│   ├── search_engine.py    # Multi-engine search with fallback
│   └── upgrade.py          # Learning log helpers
├── config/telegram.json    # Gateway config
├── skills/                 # Reusable markdown procedures
├── tests/                  # pytest suite (60 tests)
├── start_tg.py             # Telegram gateway entry point
└── p.py                    # CLI entry point
```

---

## 🧪 Tests & Audit

```bash
python -m pytest tests/ -q          # full suite
python -m tools.deep_audit          # execute every safe tool for real
```

`deep_audit` runs each safe tool with real arguments and reports pass/fail per
tool plus four agent-loop scenarios, so regressions surface as failures instead
of optimistic documentation.

---

## 📖 Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `XIAOMI_COOKIE` | MiMo session cookie (alternative to `core/session_cookie.txt`) | one of the two |
| `MIMO_TOOL_PROFILE` | `lean` (default) or `full` | ❌ |
| `MIMO_VOICE_ENABLED` | Set `0` to unregister TTS tools | ❌ |
| `MIMO_TELEGRAM_AGENT_RUNTIME` | Max seconds per Telegram task (default 900) | ❌ |
| `MIMO_TELEGRAM_REQUEST_TIMEOUT` | Per-model-request timeout (default 120) | ❌ |
| `MIMO_TELEGRAM_MAX_TOOL_CALLS` | `0` = runtime-bounded (default) | ❌ |

---

## 🤝 Contributing

Fork, branch, change, test, PR. No permission needed.

Please keep two rules:

1. **A tool must work before it is registered.** If it needs a binary or credential
   that may be absent, return `{"success": false, "reason": "not_implemented"}` and
   leave it out of `LEAN_TOOLS`.
2. **Documentation must match the code.** If you change the tool surface, update the
   README table and run the test suite.

Style: Python 3.10+, type hints preferred, docstrings on public functions, tools modular.

---

## 📜 License

MIT.

---

## 🙏 Acknowledgments

- [Xiaomi MiMo](https://aistudio.xiaomimimo.com/) — the model
- [DrissionPage](https://github.com/g1879/DrissionPage) & [Playwright](https://playwright.dev/) — browser automation
- [python-telegram-bot](https://python-telegram-bot.org/) — Telegram gateway

**Made with ❤️ by [Bactiar 291](https://github.com/bactiar291)**
