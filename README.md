# 🤖 MiMo Agent v6.0 — Unlimited AI Assistant

**204 runtime-registered tools | 14,108+ lines of code | 38 modules**

Powered by MiMo v2.5 Pro via session cookie — **no API key needed, no rate limits, no token costs.**

---

## 🚀 Why MiMo Agent?

- **Unlimited usage** — Uses your Xiaomi account session cookie. No API keys, no billing, no token limits.
- **204 built-in tools** — Code execution, browser automation, web search, file management, crypto tools, and more.
- **Telegram native** — Full-featured Telegram bot with streaming responses, file uploads, media support.
- **Multi-agent** — Supervisor/Planner system breaks complex tasks into sub-tasks and executes them in parallel.
- **Self-learning** — Learns from errors and improves over time.
- **Multi-chain crypto** — NFT hunting, airdrop automation, DeFi interactions across Base, Soneium, Polygon, and more.

---

## 📋 Prerequisites

- Python 3.10+
- A Xiaomi account (with MiMo access)
- A Telegram Bot Token (from @BotFather)

---

## 🔧 Installation

```bash
# Clone the repo
git clone https://github.com/bactiar291/mimo-agent.git
cd mimo-agent

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

---

## 🍪 Getting Your Session Cookie

MiMo Agent uses your Xiaomi account session cookie to access MiMo v2.5 Pro. This gives you **unlimited AI usage** without API keys or billing.

### Step 1: Open MiMo AI Studio

1. Go to [https://aistudio.xiaomimimo.com](https://aistudio.xiaomimimo.com)
2. Log in with your Xiaomi account
3. Make sure you can chat with MiMo

### Step 2: Open Browser DevTools

1. Press `F12` or right-click → "Inspect" to open DevTools
2. Go to the **Application** tab (Chrome) or **Storage** tab (Firefox)

### Step 3: Copy Your Cookies

1. In the left sidebar, expand **Cookies**
2. Click on `https://aistudio.xiaomimimo.com`
3. Find and copy these two values:
   - `serviceToken` — This is your main session token
   - `userId` — Your Xiaomi user ID

### Step 4: Save the Cookie

Create the config file:

```bash
mkdir -p config
```

Create `config/session_cookie.txt` with this format:

```
serviceToken=YOUR_SERVICE_TOKEN_HERE
userId=YOUR_USER_ID_HERE
```

Replace `YOUR_SERVICE_TOKEN_HERE` and `YOUR_USER_ID_HERE` with the values you copied.

> ⚠️ **Keep this file private!** Anyone with your session cookie can access your Xiaomi account.

---

## 📱 Setting Up Telegram Bot

### Step 1: Create a Bot

1. Open Telegram and search for [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Follow the prompts to name your bot
4. Copy the **bot token** (looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Configure the Bot

Create `config/telegram.json`:

```json
{
    "bot_token": "YOUR_BOT_TOKEN_HERE",
    "allowed_users": ["YOUR_TELEGRAM_USER_ID"]
}
```

To find your Telegram user ID:
1. Search for [@userinfobot](https://t.me/userinfobot) on Telegram
2. Send `/start`
3. It will reply with your user ID

### Step 3: Run the Bot

```bash
# Start the Telegram gateway
python start_tg.py
```

Your bot is now live! Send any message to your bot on Telegram and MiMo Agent will respond.

---

## 💻 CLI Mode

You can also use MiMo Agent directly from the terminal:

```bash
python core/main.py
```

This starts an interactive chat session in your terminal.

---

## 🛠️ Available Tools (204 total)

### Code & Development
- Python code execution
- Shell command execution
- File read/write/edit
- Code analysis and debugging

### Browser & Web
- Web page browsing and interaction
- Form filling and clicking
- Screenshot capture
- Multi-search (DuckDuckGo, SearXNG, Brave)

### Crypto & Blockchain
- Multi-chain wallet management
- NFT minting and trading
- DeFi interactions
- Airdrop automation
- Contract analysis

### Telegram & Communication
- Message sending
- File uploads
- Media handling (photos, videos, audio)
- Inline keyboards

### System & Automation
- Scheduled tasks (cron)
- Background process management
- Notification system
- Sub-agent spawning

### Knowledge & Memory
- Persistent memory across sessions
- Session search (FTS5)
- Skill system
- Context compression

---

## 📁 Project Structure

```
mimo-agent/
├── core/                    # Core agent modules
│   ├── main.py              # CLI entry point
│   ├── agent.py             # Agentic conversation loop
│   └── mimo_client.py       # MiMo session client
├── tools/                   # Tool implementations
│   ├── tools.py             # Runtime tool registry
│   ├── supervisor.py        # Supervisor/Planner system
│   ├── vision.py            # Vision/Image analysis
│   ├── voice.py             # Voice/TTS
│   └── ...                  # 25+ more modules
├── lib/                     # Library modules
│   ├── browser_engine.py    # Hybrid browser
│   ├── search_engine.py     # Multi-search
│   └── todo_store.py        # Todo management
├── config/                  # Configuration
│   ├── session_cookie.txt   # MiMo cookie
│   └── telegram.json        # Telegram config
├── start_tg.py              # Telegram gateway
└── requirements.txt         # Dependencies
```

---

## 🔒 Security

- Command safety checks before terminal execution
- Path sandbox (ALLOWED_BASES restriction)
- Cookie chmod 600 enforcement
- Input validation
- User allowlist for Telegram access

---

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MIMO_COOKIE_PATH` | Path to session cookie file | `config/session_cookie.txt` |
| `TELEGRAM_CONFIG_PATH` | Path to Telegram config | `config/telegram.json` |
| `MAX_RUNTIME` | Max agent runtime in seconds | `3600` |
| `TOOL_BUDGET` | Max tool calls per session | `200` |

### Cookie Refresh

Session cookies expire after some time. If you get authentication errors:

1. Go back to [https://aistudio.xiaomimimo.com](https://aistudio.xiaomimimo.com)
2. Log in again if needed
3. Repeat the cookie extraction steps above
4. Update `config/session_cookie.txt` with the new values

---

## 🐳 Docker

```bash
docker build -t mimo-agent .
docker run -d \
    -v $(pwd)/config:/app/config \
    -p 8080:8080 \
    mimo-agent
```

---

## 📊 Stats

- **204** runtime-registered tools
- **14,108+** lines of code
- **38** modules
- **0** API costs — completely free to run

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

---

## 📄 License

MIT License — See [LICENSE](LICENSE) for details.

---

## 🙏 Credits

- **MiMo v2.5 Pro** by Xiaomi — The AI model powering this agent
- **DrissionPage** — Browser automation
- **Playwright** — SPA rendering
- **DuckDuckGo** — Free web search

---

**Made with ❤️ by [bactiar291](https://github.com/bactiar291)**
