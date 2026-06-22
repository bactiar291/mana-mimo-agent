# 🤖 MiMo Agent — Unlimited AI Assistant

**204+ tools | No API key needed | Free forever**

Powered by MiMo v2.5 Pro via session cookie — **unlimited usage, zero cost.**

> **By [Bactiar 291](https://github.com/bactiar291)** — Open source, free to use, contributions welcome!

---

## ✨ What Can It Do?

- **204+ Tools** — file ops, web scraping, browser automation, crypto, NFT hunting, DeFi, Telegram, Discord, and more
- **Telegram Gateway** — run as a personal AI assistant in Telegram
- **Multi-Chain Crypto** — Base, Soneium, Polygon, Arbitrum, Optimism, BSC, Avalanche
- **NFT Hunting** — auto-scan free mints, audit contracts, mint & list
- **Browser Automation** — Playwright + DrissionPage, anti-detection
- **Self-Learning** — auto-improve from errors, skill system
- **Persistent Memory** — remembers across sessions
- **Cron Jobs** — schedule any task to run automatically
- **Multi-Agent** — delegate tasks to sub-agents in parallel
- **Voice/TTS** — text-to-speech with edge-tts
- **Vision** — analyze images and screenshots

---

## 🚀 Quick Start

### Step 1: Get Session Cookie (FREE — No API Key!)

MiMo Agent uses MiMo v2.5 Pro via session cookie — **completely free, no API key required, unlimited usage.**

**How to get the session cookie:**

1. Open [aistudio.xiaomimimo.com](https://aistudio.xiaomimimo.com/) in your browser
2. Log in with your Xiaomi account (create one if needed)
3. Press **F12** to open DevTools
4. Go to **Application** tab → **Cookies** → `https://aistudio.xiaomimimo.com`
5. Find and copy these values:
   - `session` — this is your main session token
   - `user` — your user ID (optional but recommended)
6. **Save these values** — you'll need them in Step 3

> ⚠️ **Important:** The session cookie expires after some time. If the agent stops working, repeat Step 1 to get a fresh cookie.

### Step 2: Create Telegram Bot

1. Open Telegram → search [@BotFather](https://t.me/BotFather)
2. Send `/newbot`
3. Enter a name for your bot (e.g., "My AI Assistant")
4. Enter a username (must end with "bot", e.g., "my_assistant_bot")
5. **Copy the bot token** — looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`

### Step 3: Install & Configure

```bash
# Clone the repo
git clone https://github.com/bactiar291/mimo-agent.git
cd mimo-agent

# Install dependencies
pip install -r requirements.txt

# Create .env file with your credentials
cat > .env << 'EOF'
MIMO_SESSION=paste_your_session_cookie_here
MIMO_USER=paste_your_user_id_here
TELEGRAM_BOT_TOKEN=paste_your_bot_token_here
EOF
```

### Step 4: Run

```bash
# Run in Telegram mode (recommended)
python start_tg.py

# Or run in CLI mode
python core/agent.py
```

**That's it!** Open Telegram, find your bot, and start chatting. The agent has full access to 204+ tools and will execute any task you give it.

---

## 🛠️ Available Tools (204+)

| Category | Tools |
|----------|-------|
| **File System** | read, write, edit, search, list, patch |
| **Web** | search, extract, browse, scrape |
| **Browser** | click, type, navigate, screenshot, snapshot |
| **Crypto** | wallet ops, swap, bridge, stake |
| **NFT** | scan mints, audit contracts, mint, list |
| **DeFi** | Aerodrome, Velodrome, Uniswap, Sushi |
| **Telegram** | send, receive, manage groups |
| **System** | terminal, process, cron, memory |
| **AI** | delegate tasks, vision, TTS |

---

## 🔧 Architecture

```
mimo-agent/
├── core/
│   ├── agent.py          # Main agent loop
│   ├── tools/            # 204+ tool implementations
│   └── memory/           # Persistent memory system
├── telegram/
│   └── gateway.py        # Telegram bot integration
├── browser/
│   ├── playwright.py     # Playwright automation
│   └── drission.py       # DrissionPage (anti-detect)
├── crypto/
│   ├── chains.py         # Multi-chain support
│   └── nft_hunter.py     # NFT scanning & minting
├── skills/               # Reusable skill procedures
└── start_tg.py           # Entry point (Telegram mode)
```

---

## 📖 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `MIMO_SESSION` | Session cookie from MiMo AI Studio | ✅ |
| `MIMO_USER` | User ID (optional) | ❌ |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token from BotFather | ✅ |
| `OPENAI_API_KEY` | OpenAI API key (optional, for fallback) | ❌ |
| `ETHERSCAN_API_KEY` | For contract verification | ❌ |

### Advanced Configuration

Edit `config.yaml` for:
- Model selection
- Tool enable/disable
- Memory settings
- Cron schedules
- Chain RPCs

---

## 🤝 Contributing — Developers Welcome!

**This is an open-source project. Anyone can contribute!**

Whether you're a beginner or an experienced developer, your contributions are valued. Help us make MiMo Agent better for everyone.

### How to Contribute

1. **Fork** this repository
2. **Clone** your fork (`git clone https://github.com/YOUR_USERNAME/mimo-agent.git`)
3. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
4. **Make** your changes
5. **Test** your changes
6. **Commit** (`git commit -m 'Add amazing feature'`)
7. **Push** (`git push origin feature/amazing-feature`)
8. **Open** a Pull Request

### What We Need

- 🔗 More chain integrations (Solana, Tron, TON, etc.)
- 🎨 Better UI/UX for Telegram commands
- 📊 Portfolio tracking & analytics
- 🔐 Security auditing tools
- 📱 Mobile-friendly interfaces
- 🌐 Multi-language support
- 🧪 Tests and documentation
- 🐛 Bug fixes
- 📖 Documentation improvements

### Code Style

- Python 3.10+
- Type hints preferred
- Docstrings for public functions
- Keep tools modular and self-contained

### No Permission Needed

- Found a bug? Fix it and submit a PR
- Want a new feature? Build it and submit a PR
- Improve documentation? Submit a PR
- Add tests? Submit a PR

**You don't need to ask permission. Just build and submit.**

---

## 📜 License

MIT License — free to use, modify, and distribute.

---

## 🙏 Acknowledgments

- [Xiaomi MiMo](https://aistudio.xiaomimimo.com/) — for the amazing AI model
- [Playwright](https://playwright.dev/) — for browser automation
- [web3.py](https://web3py.readthedocs.io/) — for blockchain interaction

---

## ⭐ Star This Repo

If you find this useful, give it a star! It helps others discover the project.

**Made with ❤️ by [Bactiar 291](https://github.com/bactiar291)**
