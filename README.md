# 🤖 MiMo Agent v6.0 — Super Agentic Assistant

**204 runtime-registered tools | ~14,108 LOC | 38 modules**

Powered by MiMo v2.5 Pro via session cookie (no API key needed).

## Features

### Core Agentic (MiMo Original)
- ✅ Agentic conversation loop with tool calling
- ✅ Streaming output with thinking display
- ✅ Persistent memory system
- ✅ Hybrid browser (DrissionPage + Playwright)
- ✅ Multi-search engine (DuckDuckGo, SearXNG, Brave)
- ✅ 204 runtime-registered tools

### From DeerFlow (ByteDance)
- ✅ Supervisor/Planner system — break complex tasks into sub-tasks
- ✅ Multi-agent orchestration
- ✅ Sandbox execution
- ✅ State machine workflow

### From Hermes Agent (Nous Research)
- ✅ Skill system — reusable procedures
- ✅ Session search — FTS5 search across past conversations
- ✅ Vision/Image analysis
- ✅ Voice/TTS (edge-tts)
- ✅ Kanban multi-agent work queue
- ✅ Webhook triggers
- ✅ MCP server support
- ✅ Enhanced memory (user, environment, facts, preferences)
- ✅ Context compression
- ✅ Credential pool (API key rotation)
- ✅ Filesystem checkpoints

### From OpenClaw
- ✅ Multi-channel router (Telegram, Discord, WhatsApp, Slack)
- ✅ Skill security scanner (SkillSpector)
- ✅ Auto-improve (self-learning from errors)
- ✅ Event system (event-driven automation)
- ✅ Plugin system
- ✅ Agent workspaces
- ✅ Browser automation enhanced (snapshot, stable-tab, stale-ref)

## Quick Start

```bash
cd /root/mimo-agent

# Setup session cookie
nano config/session_cookie.txt

# Setup Telegram token
nano config/telegram.json

# Run CLI
python core/main.py

# Run Telegram gateway
python start_tg.py
```

## Tools

Runtime source of truth is `tools.tools.TOOLS` / `get_tools_schema()`. Current audit:

```bash
python - <<'PY'
from tools.tools import TOOLS, get_tools_schema
print(len(TOOLS), len(get_tools_schema()))
PY
```

Expected output: `204 204`.

To inspect exact runtime names:

```bash
python - <<'PY'
from collections import defaultdict
from tools.tools import TOOLS

groups = defaultdict(list)
for name in sorted(TOOLS):
    groups[name.split("_", 1)[0]].append(name)

for group, names in sorted(groups.items()):
    print(f"\n[{group}]")
    print(", ".join(names))
PY
```

## Architecture

```
/root/mimo-agent/
├── core/                    # Core agent modules
│   ├── main.py              # CLI entry point
│   ├── agent.py             # Agentic conversation loop
│   └── mimo_client.py       # MiMo session client
├── tools/                   # Tool implementations (25 modules)
│   ├── tools.py             # Runtime tool registry
│   ├── extra_tools.py       # Extra tools
│   ├── supervisor.py        # Supervisor/Planner (DeerFlow)
│   ├── session_search.py    # Session search (Hermes)
│   ├── skill_scanner.py     # Skill security (OpenClaw)
│   ├── vision.py            # Vision/Image analysis
│   ├── voice.py             # Voice/TTS
│   ├── webhooks.py          # Webhook triggers
│   ├── enhanced_memory.py   # Enhanced memory
│   ├── session_manager.py   # Session management
│   ├── cron_manager.py      # Scheduled tasks
│   ├── delegation.py        # Subagent spawning
│   ├── notification.py      # Notifications
│   ├── thinking.py          # Chain-of-thought
│   ├── channel_router.py    # Multi-channel (OpenClaw)
│   ├── auto_improve.py      # Self-learning (OpenClaw)
│   ├── event_system.py      # Event-driven (OpenClaw)
│   ├── plugin_system.py     # Plugin system (OpenClaw)
│   ├── context_compressor.py # Context compression (Hermes)
│   ├── credential_pool.py   # API key rotation (Hermes)
│   ├── skill_manager.py     # Skill system (Hermes)
│   ├── kanban.py            # Kanban work queue (Hermes)
│   ├── mcp_client.py        # MCP support (Hermes)
│   ├── sandbox.py           # Code sandbox
│   ├── checkpoints.py       # Filesystem checkpoints (Hermes)
│   └── workspaces.py        # Agent workspaces (OpenClaw)
├── lib/                     # Library modules (5 modules)
│   ├── browser_engine.py    # Hybrid browser
│   ├── search_engine.py     # Multi-search
│   ├── todo_store.py        # Todo management
│   └── upgrade.py           # Self-upgrade
├── config/                  # Configuration
│   ├── session_cookie.txt   # MiMo cookie
│   └── telegram.json        # Telegram config
├── tests/                   # Tests
├── pyproject.toml           # Project config
├── Dockerfile               # Container config
└── start_tg.py              # Telegram gateway
```

## Security

- ✅ Command safety checks before terminal execution
- ✅ Path sandbox (ALLOWED_BASES restriction)
- ✅ Cookie chmod 600 enforcement
- ✅ Skill security scanner
- ✅ Input validation

## Comparison

| Feature | DeerFlow | Hermes | OpenClaw | MiMo Agent |
|---------|----------|--------|----------|------------|
| Multi-agent | ✅ | ✅ | ✅ | ✅ |
| Supervisor/Planner | ✅ | ❌ | ❌ | ✅ |
| Skills | ❌ | ✅ | ✅ | ✅ |
| Session Search | ❌ | ✅ | ❌ | ✅ |
| Vision | ❌ | ✅ | ✅ | ✅ |
| Voice/TTS | ❌ | ✅ | ❌ | ✅ |
| Sandbox | ✅ | ✅ | ✅ | ✅ |
| Kanban | ❌ | ✅ | ❌ | ✅ |
| Webhooks | ❌ | ✅ | ❌ | ✅ |
| MCP | ❌ | ✅ | ✅ | ✅ |
| Memory | ✅ | ✅ | ✅ | ✅ |
| Multi-Channel | ❌ | ✅ | ✅ | ✅ |
| Auto-Improve | ❌ | ❌ | ✅ | ✅ |
| Events | ❌ | ❌ | ✅ | ✅ |
| Plugins | ❌ | ✅ | ✅ | ✅ |
| Workspaces | ❌ | ❌ | ✅ | ✅ |
| Context Compress | ❌ | ✅ | ❌ | ✅ |
| Credential Pool | ❌ | ✅ | ❌ | ✅ |
| Checkpoints | ❌ | ✅ | ❌ | ✅ |

**Total: 204 runtime-registered tools.**

## Credits

- **MiMo v2.5 Pro** by Xiaomi
- **DeerFlow** by ByteDance
- **Hermes Agent** by Nous Research
- **OpenClaw** by OpenClaw Team
- **DrissionPage** for browser automation
- **Playwright** for SPA rendering
- **DuckDuckGo** for free web search
