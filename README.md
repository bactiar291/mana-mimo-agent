# 🤖 MiMo Agent v6.0 — Unlimited AI Assistant

**204 runtime-registered tools | 14,108+ lines of code | 38 modules**

Powered by MiMo v2.5 Pro via session cookie — **no API key needed, no rate limits, no token costs.**

---

## 🚀 What is MiMo Agent?

MiMo Agent is a **fully autonomous AI assistant** that runs on Xiaomi's MiMo v2.5 Pro model — **completely free, unlimited usage, zero API costs.**

Unlike paid AI APIs that charge per token, MiMo Agent uses your Xiaomi account session cookie to access MiMo v2.5 Pro directly. This means:

- ♾️ **Unlimited messages** — No daily/hourly limits
- 💰 **Zero cost** — No API keys, no billing, no token counting
- 🧠 **Smart reasoning** — MiMo v2.5 Pro is competitive with GPT-4 and Claude
- 🔧 **204 built-in tools** — Code execution, browser automation, web search, crypto tools, and more
- 📱 **Telegram native** — Full-featured Telegram bot with streaming, file uploads, media support
- 🤖 **Multi-agent** — Supervisor/Planner system breaks complex tasks into sub-tasks
- 🧬 **Self-learning** — Learns from errors and improves over time
- ⛓️ **Multi-chain crypto** — NFT hunting, airdrop automation, DeFi across Base, Soneium, Polygon, and more

---

## 📋 Prerequisites

- Python 3.10+
- A Xiaomi account (with MiMo access at [aistudio.xiaomimimo.com](https://aistudio.xiaomimimo.com))
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

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

## 🍪 Getting Your Session Cookie (Step-by-Step)

MiMo Agent uses your Xiaomi account session cookie to access MiMo v2.5 Pro. This is what makes it **unlimited and free.**

### Step 1: Open MiMo AI Studio

1. Open your browser (Chrome recommended)
2. Go to **[https://aistudio.xiaomimimo.com](https://aistudio.xiaomimimo.com)**
3. Log in with your Xiaomi account (create one if you don't have it)
4. Make sure you can chat with MiMo — send a test message to verify

### Step 2: Open Browser DevTools

1. Press **F12** on your keyboard (or right-click anywhere → "Inspect")
2. A panel will open on the right side of your browser
3. Click the **Application** tab at the top of the panel
   - If you don't see it, click the `>>` arrows to find it

### Step 3: Find Your Cookies

1. In the left sidebar of the Application tab, expand **Cookies**
2. Click on `https://aistudio.xiaomimimo.com`
3. You'll see a list of cookies — find these two:
   - **`serviceToken`** — This is your main session token (long string)
   - **`userId`** — Your Xiaomi user ID (numbers)

### Step 4: Copy the Values

1. Click on the `serviceToken` row
2. In the "Value" field at the bottom, copy the entire long string
3. Do the same for `userId`

> 💡 **Tip:** You can also get cookies from the **Network** tab:
> 1. Go to the **Network** tab in DevTools
> 2. Send a message in MiMo
> 3. Click on any request to `aistudio.xiaomimimo.com`
> 4. Look at the **Request Headers** → find the `Cookie` header
> 5. Copy the `serviceToken=...` and `userId=...` values

### Step 5: Save the Cookie

Create the config directory and cookie file:

```bash
mkdir -p config
```

Create `config/session_cookie.txt`:

```
serviceToken=YOUR_SERVICE_TOKEN_HERE
userId=YOUR_USER_ID_HERE
```

Replace with your actual values. Example:
```
serviceToken=abc123xyz456...very_long_string...def789
userId=1234567890
```

> ⚠️ **IMPORTANT: Keep this file private!**
> - Anyone with your session cookie can access your Xiaomi account
> - Never share it publicly or commit it to Git
> - The `.gitignore` already excludes `config/` folder

---

## 📱 Setting Up Telegram Bot

### Step 1: Create a Bot

1. Open Telegram and search for **[@BotFather](https://t.me/BotFather)**
2. Send `/newbot`
3. Choose a name for your bot (e.g., "MiMo Agent")
4. Choose a username (must end in "bot", e.g., "mimo_agent_bot")
5. Copy the **bot token** (looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Find Your Telegram User ID

1. Search for **[@userinfobot](https://t.me/userinfobot)** on Telegram
2. Send `/start`
3. It will reply with your user ID (a number like `123456789`)

### Step 3: Configure the Bot

Create `config/telegram.json`:

```json
{
    "bot_token": "YOUR_BOT_TOKEN_HERE",
    "allowed_users": ["YOUR_TELEGRAM_USER_ID"]
}
```

Example:
```json
{
    "bot_token": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz",
    "allowed_users": ["987654321"]
}
```

> 💡 You can add multiple user IDs to allow friends/family to use your bot.

### Step 4: Run the Bot

```bash
python start_tg.py
```

Your bot is now live! Open Telegram, find your bot, and send any message. MiMo Agent will respond with full AI capabilities.

### Step 5 (Optional): Run as Background Service

To keep the bot running 24/7:

```bash
# Using systemd (Linux)
sudo nano /etc/systemd/system/mimo-agent.service
```

Add this content:
```ini
[Unit]
Description=MiMo Agent Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/path/to/mimo-agent
ExecStart=/usr/bin/python3 start_tg.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then enable and start:
```bash
sudo systemctl enable mimo-agent
sudo systemctl start mimo-agent
sudo systemctl status mimo-agent
```

---

## 💻 CLI Mode

Use MiMo Agent directly from your terminal:

```bash
python core/main.py
```

This starts an interactive chat session. Type your message and press Enter.

---

## 🛠️ Available Tools (204 total)

| Category | Tools |
|----------|-------|
| **Code & Development** | Python execution, shell commands, file ops, code analysis, debugging |
| **Browser & Web** | Web browsing, form filling, screenshots, multi-search (DuckDuckGo, SearXNG, Brave) |
| **Crypto & Blockchain** | Multi-chain wallets, NFT minting/trading, DeFi, airdrop automation, contract analysis |
| **Telegram & Communication** | Message sending, file uploads, media handling, inline keyboards |
| **System & Automation** | Cron jobs, background processes, notifications, sub-agent spawning |
| **Knowledge & Memory** | Persistent memory, session search (FTS5), skill system, context compression |

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
│   ├── session_cookie.txt   # MiMo cookie (create this)
│   └── telegram.json        # Telegram config (create this)
├── start_tg.py              # Telegram gateway
└── requirements.txt         # Dependencies
```

---

## 🔒 Security

- ✅ Command safety checks before terminal execution
- ✅ Path sandbox (ALLOWED_BASES restriction)
- ✅ Cookie chmod 600 enforcement
- ✅ Input validation
- ✅ User allowlist for Telegram access
- ✅ `.gitignore` excludes all sensitive config files

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

Session cookies expire after some time (usually days/weeks). If you get authentication errors:

1. Go back to [https://aistudio.xiaomimimo.com](https://aistudio.xiaomimimo.com)
2. Log in again if needed
3. Repeat the cookie extraction steps from [Getting Your Session Cookie](#-getting-your-session-cookie-step-by-step)
4. Update `config/session_cookie.txt` with the new values
5. Restart the bot

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
- **Unlimited** usage via session cookie

---

## 🤝 Contributing

**Developers are welcome to contribute!** MiMo Agent is open-source and we encourage everyone to help improve it.

### How to Contribute

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/amazing-feature`
3. **Commit** your changes: `git commit -m 'Add amazing feature'`
4. **Push** to the branch: `git push origin feature/amazing-feature`
5. **Open** a Pull Request

### What We're Looking For

- 🔧 **New tools** — Add new capabilities to the agent
- 🐛 **Bug fixes** — Fix issues and improve stability
- 📖 **Documentation** — Improve docs, add examples
- 🌐 **Translations** — Help make MiMo Agent multilingual
- ⚡ **Performance** — Optimize speed and resource usage
- 🔗 **Integrations** — Connect with more platforms and services

### Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/mimo-agent.git
cd mimo-agent

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Run tests
python -m pytest tests/

# Start developing!
```

### Code Style

- Follow PEP 8 for Python code
- Add docstrings to new functions
- Write tests for new features
- Keep commits clean and descriptive

---

## 📄 License

MIT License — See [LICENSE](LICENSE) for details.

You are free to:
- ✅ Use commercially
- ✅ Modify
- ✅ Distribute
- ✅ Use privately

---

## 🙏 Credits

- **MiMo v2.5 Pro** by Xiaomi — The AI model powering this agent
- **DrissionPage** — Browser automation
- **Playwright** — SPA rendering
- **DuckDuckGo** — Free web search
- **All contributors** — Thank you for making MiMo Agent better!

---

## ⭐ Star This Repo

If you find MiMo Agent useful, please **star this repo** to help others discover it!

---

**Made with ❤️ by [bactiar291](https://github.com/bactiar291)**
