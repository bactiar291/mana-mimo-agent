# 🤖 MiMo Agent — Modular Agentic AI Assistant

**204 runtime-registered tools | ~14,108 LOC | 38 modules**

Powered by MiMo v2.5 Pro via session cookie (no API key needed).

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

### 1. Get Session Cookie (No API Key Needed!)

MiMo Agent uses MiMo v2.5 Pro via session cookie — **completely free**, no API key required.

**Step-by-step:**

1. Go to [aistudio.xiaomimimo.com](https://aistudio.xiaomimimo.com/)
2. Log in with your Xiaomi account (or create one)
3. Open DevTools (F12) → Application → Cookies
4. Copy these two values:
   - `session` — the session token
   - `user` — the user ID (optional)
5. Save them for the next step

### 2. Install & Configure

```bash
# Clone the repo
git clone https://github.com/bactiar291/mimo-agent.git
cd mimo-agent

# Install dependencies
pip install -r requirements.txt

# Create .env file
cat > .env << 'EOF'
MIMO_SESSION=your_session_cookie_here
MIMO_USER=your_user_id_here
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
EOF
```

### 3. Set Up Telegram Bot

1. Open Telegram → search [@BotFather](https://t.me/BotFather)
2. Send `/newbot` → follow instructions
3. Copy the bot token
4. Add it to your `.env` file as `TELEGRAM_BOT_TOKEN`

### 4. Run

```bash
# Run in Telegram mode
python start_tg.py

# Or run in CLI mode
python core/agent.py
```

**That's it!** Your AI agent is now running in Telegram. Send any message and it will respond with full tool access.

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

## 🤝 Contributing

**All contributions welcome!** This is an open-source project — anyone can add features, fix bugs, or improve documentation.

### How to Contribute

1. **Fork** this repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### What We Need

- 🔗 More chain integrations (Solana, Tron, etc.)
- 🎨 Better UI/UX for Telegram commands
- 📊 Portfolio tracking & analytics
- 🔐 Security auditing tools
- 📱 Mobile-friendly interfaces
- 🌐 Multi-language support
- 🧪 Tests and documentation

### Code Style

- Python 3.10+
- Type hints preferred
- Docstrings for public functions
- Keep tools modular and self-contained

---

## 📜 License

MIT License — free to use, modify, and distribute.

---

## 🙏 Acknowledgments

- [Xiaomi MiMo](https://aistudio.xiaomimimo.com/) — for the amazing AI model
- [OpenAI](https://openai.com/) — for the tool-calling architecture
- [Playwright](https://playwright.dev/) — for browser automation
- [web3.py](https://web3py.readthedocs.io/) — for blockchain interaction

---

## ⭐ Star This Repo

If you find this useful, give it a star! It helps others discover the project.

**Made with ❤️ by [Bactiar 291](https://github.com/bactiar291)**
