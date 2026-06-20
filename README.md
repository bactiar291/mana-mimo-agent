# Agent — Agentic AI Assistant

A powerful agentic AI assistant powered by MiMo v2.5 Pro via session cookie (no API key needed).

## Features

- **53 Built-in Tools**: web search, file ops, terminal, Python, browser automation, git, HTTP, and more
- **Hybrid Browser Engine**: DrissionPage (fast) + Playwright (stable for SPA) with auto-fallback
- **Multi-Search Engine**: DuckDuckGo (free, default) + SearXNG + Brave (optional API key)
- **Agentic Loop**: Auto-calls tools, chains multiple steps, self-corrects on failure
- **Streaming Output**: Real-time response with thinking display
- **Persistent Memory**: Remembers facts, preferences, and corrections across sessions
- **Typo Correction**: Auto-fixes common Indonesian + English typos
- **Clean Output**: Plain text with box-drawing tables, no markdown

## Quick Start

1. **Get MiMo Session Cookie**:
   - Go to https://aistudio.xiaomimimo.com
   - Login with your Xiaomi account
   - Open DevTools (F12) → Application → Cookies
   - Copy the entire cookie string

2. **Setup**:
   ```bash
   # Clone the repo
   git clone https://github.com/yourusername/agent.git
   cd agent
   
   # Install dependencies
   pip install requests DrissionPage playwright
   python -m playwright install chromium
   
   # Add your cookie
   cp session_cookie.txt.example session_cookie.txt
   # Edit session_cookie.txt and paste your cookie
   ```

3. **Run**:
   ```bash
   python main.py
   ```

## Usage

```
python main.py [--model=mimo-v2.5-pro] [--web] [--no-web] [--no-think] [-q]
```

### Commands

| Command | Description |
|---------|-------------|
| `/help` | Show help |
| `/reset` | Clear conversation history |
| `/model` | Show/change model |
| `/tools` | List available tools |
| `/web` | Toggle web search |
| `/think` | Toggle thinking display |
| `/browser` | Toggle browser visible/headless |
| `/history` | Show conversation history |
| `/memory` | View/save memory |
| `/save` | Save conversation to file |
| `/clear` | Clear screen |
| `/quit` | Exit |

### Examples

```
❯ Cari info tentang Bitcoin hari ini
  ┊ 🌐 web_search(query=Bitcoin price today)  250ms
  ┊ ok (results)
  
  Bitcoin saat ini...

❯ Baca file config.py dan jelaskan isinya
  ┊ 📖 read_file(path=config.py)  5ms
  ┊ ok (content, total_lines)
  
  File config.py berisi...

❯ Jalankan ls -la di folder saat ini
  ┊ 💻 $ls -la  120ms
  ┊ ok (output, exit_code)
  
  total 48...

❯ Cek wallet 0xbfc1... di ette.world
  ┊ 🌐 browser_open(url=https://www.ette.world/)  8.9s
  ┊ ok (url, title, content)
  ┊ ⌨️ browser_type(selector=input, text=0xbfc1...)  500ms
  ┊ 👆 browser_click(selector=button)  1.2s
  
  Wallet eligibility: ...
```

## Tools (53)

### Web & Search
- `web_search` — Search via DuckDuckGo (free, no API key)
- `web_extract` — Extract content from URL
- `search_engine_set` — Switch search engine (duckduckgo/searxng/brave)
- `search_engine_status` — Get current search engine

### Browser (Hybrid Engine)
- `browser_open` — Open URL (auto-fallback DrissionPage/Playwright)
- `browser_click` — Click element
- `browser_type` — Type into input field
- `browser_get_text` — Get page text
- `browser_get_links` — Get all links
- `browser_evaluate` — Execute JavaScript
- `browser_wait_for` — Wait for element
- `browser_screenshot` — Take screenshot
- `browser_close` — Close browser
- `browser_status` — Get browser status
- `browser_set_engine` — Switch browser engine

### File Operations
- `read_file` — Read file with line numbers
- `write_file` — Write file (overwrites)
- `patch_file` — Find and replace in file
- `append_file` — Append to file
- `search_files` — Search files by content or name
- `find_files` — Find files by pattern
- `list_directory` — List directory contents
- `list_tree` — Show directory tree
- `file_info` — Get file metadata
- `copy_path` — Copy file/directory
- `move_path` — Move file/directory
- `move_to_trash` — Move to trash
- `create_directory` — Create directory

### Code & Data
- `execute_python` — Execute Python code
- `read_json` — Read and parse JSON
- `write_json` — Write JSON file
- `json_query` — Query JSON with key path
- `csv_preview` — Preview CSV file
- `sqlite_query` — Execute SQLite query
- `code_outline` — Show code structure
- `project_map` — Map project structure

### Terminal & System
- `terminal` — Execute shell command
- `current_time` — Get current time
- `system_info` — Get system information
- `disk_usage` — Check disk usage
- `process_list` — List running processes
- `process_kill` — Kill process

### HTTP & Network
- `http_request` — Make HTTP request
- `download_file` — Download file from URL

### Git
- `git_status` — Show git status
- `git_diff` — Show git diff
- `git_log` — Show git log
- `git_show` — Show git commit

### Archive
- `create_archive` — Create tar.gz archive
- `extract_archive` — Extract archive

### Task Management
- `task_board` — Manage task board (todo/in_progress/done)

## Architecture

```
agent/
├── main.py              # CLI entry point
├── agent.py             # Agentic conversation loop
├── mimo_client.py       # MiMo session client (streaming)
├── tools.py             # 53 tool implementations
├── browser_engine.py    # Hybrid browser (DrissionPage + Playwright)
├── search_engine.py     # Multi-engine search (DDG + SearXNG + Brave)
├── session_cookie.txt   # Your MiMo cookie (gitignored)
├── memory.json          # Persistent memory (gitignored)
├── .gitignore           # Git ignore rules
├── session_cookie.txt.example  # Cookie template
└── README.md            # This file
```

## How It Works

1. User sends message
2. Agent builds prompt with system instructions + tools + history
3. MiMo model responds (may include tool call as JSON)
4. If tool call detected → execute tool → feed result back to model
5. Repeat until model gives final answer (max 8 tool calls)
6. Display answer in bordered box

## Configuration

### Search Engines
```python
# Switch to SearXNG (free, self-hosted)
search_engine_set(engine="searxng", instance="https://searx.be")

# Switch to Brave (needs API key)
search_engine_set(engine="brave", api_key="your-api-key")

# Back to DuckDuckGo (default, free)
search_engine_set(engine="duckduckgo")
```

### Browser Engines
```python
# Switch to Playwright (more stable for SPA)
browser_set_engine(engine="playwright")

# Switch to DrissionPage (faster, default)
browser_set_engine(engine="drission")

# Toggle visible browser (watch automation)
/browser
```

## Requirements

- Python 3.8+
- requests
- DrissionPage
- playwright (optional, for SPA sites)

## License

MIT

## Credits

- MiMo v2.5 Pro by Xiaomi
- DrissionPage for browser automation
- Playwright for SPA rendering
- DuckDuckGo for free web search
