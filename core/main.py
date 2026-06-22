#!/usr/bin/env python3
"""
main.py — Agent CLI (Hermes-grade)
Agentic assistant powered by MiMo v2.5 Pro via session cookie.

Features:
- Dynamic tool registry (web, file, terminal, python, browser, search, git, etc.)
- Live thinking display (dim cyan)
- Smooth animations with braille spinners
- Persistent memory across sessions
- Slash commands
- Web search ON by default (DuckDuckGo, free)
- Hybrid browser engine (DrissionPage + Playwright)
- Typo correction
- Clean plain-text output (no markdown)
"""
import os
import sys
import shlex
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent import MiMoAgent, C, Memory


# ─── Slash Commands ──────────────────────────────────────────────────────────

COMMANDS = {
    "/help":     "Tampilkan bantuan",
    "/reset":    "Hapus conversation history",
    "/model":    "Ganti model (usage: /model <nama>)",
    "/tools":    "List tools yang tersedia",
    "/web":      "Toggle web search on/off",
    "/think":    "Toggle thinking display on/off",
    "/browser":  "Toggle browser visible/headless",
    "/history":  "Lihat conversation history",
    "/memory":   "Lihat/simpan memory (/memory [clear|fact <text>|pref <k>=<v>])",
    "/save":     "Simpan conversation ke file",
    "/clear":    "Clear screen",
    "/quit":     "Keluar",
}


# ─── Banner ──────────────────────────────────────────────────────────────────

def banner():
    try:
        from tools.tools import get_tools_schema
        tool_label = f"{len(get_tools_schema())} tools"
    except Exception:
        tool_label = "dynamic tools"
    art = f"""{C.C}
  \u2588\u2588\u2588\u2557   \u2588\u2588\u2588\u2557\u2588\u2588\u2557\u2588\u2588\u2588\u2557   \u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2588\u2588\u2557
  \u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2551\u2588\u2588\u2551\u2588\u2588\u2588\u2588\u2557 \u2588\u2588\u2588\u2588\u2551\u2588\u2588\u2554\u2550\u2550\u2550\u2550\u2557
  \u2588\u2588\u2554\u2588\u2588\u2588\u2588\u2554\u2588\u2588\u2551\u2588\u2588\u2551\u2588\u2588\u2554\u2588\u2588\u2588\u2588\u2554\u2588\u2588\u2551\u2588\u2588\u2551   \u2588\u2588\u2551
  \u2588\u2588\u2551\u255a\u2588\u2588\u2554\u255d\u2588\u2588\u2551\u2588\u2588\u2551\u2588\u2588\u2551\u255a\u2588\u2588\u2554\u255d\u2588\u2588\u2551\u2588\u2588\u2551   \u2588\u2588\u2551
  \u2588\u2588\u2551 \u255a\u2550\u255d \u2588\u2588\u2551\u2588\u2588\u2551\u2588\u2588\u2551 \u255a\u2550\u255d \u2588\u2588\u2551\u255a\u2588\u2588\u2588\u2588\u2588\u2588\u2554\u255d
  \u255a\u2550\u255d     \u255a\u2550\u255d\u255a\u2550\u255d\u255a\u2550\u255d   \u255a\u2550\u255d \u255a\u2550\u2550\u2550\u2550\u2550\u255d
  {C.THINK}            A  G  E  N  T{C.X}
  {C.DIM}Agentic Assistant · {tool_label} · v6.0{C.X}
"""
    print(art)


# ─── Command Handlers ─────────────────────────────────────────────────────────

def show_help():
    print(f"\n{C.BOLD}Commands:{C.X}")
    for cmd, desc in COMMANDS.items():
        print(f"  {C.C}{cmd:<10}{C.X}  {desc}")
    print(f"\n{C.DIM}Ctrl+C interrupt, /quit keluar. Web search ON by default.{C.X}\n")


def show_tools(agent):
    print(f"\n{C.BOLD}Tools ({len(agent.tools_schema)}):{C.X}")
    for s in agent.tools_schema:
        fn = s["function"]
        print(f"  {C.G}{fn['name']:<22}{C.X} {C.DIM}{fn['description'][:60]}{C.X}")
    print()


def show_history(agent):
    print(f"\n{C.BOLD}History ({len(agent.history)} messages):{C.X}")
    for i, msg in enumerate(agent.history[-15:], 1):
        role = msg["role"]
        content = msg["content"][:200].replace("\n", " ")
        color = C.C if role == "User" else C.G if role == "Assistant" else C.Y
        print(f"  {color}{i:>2}.{C.X} {color}{role:<10}{C.X} {content}")
    print()


def handle_memory(agent, args: str):
    parts = args.split(maxsplit=1)
    if not parts:
        print(f"\n{C.BOLD}Memory:{C.X}")
        print(agent.memory.summary())
        print()
        return

    sub = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if sub == "clear":
        agent.memory.clear()
        print(f"{C.G}\u2713 memory cleared{C.X}\n")
    elif sub == "fact":
        if rest:
            agent.memory.add_fact(rest)
            print(f"{C.G}\u2713 fact saved{C.X}\n")
        else:
            print(f"{C.Y}usage: /memory fact <text>{C.X}\n")
    elif sub == "pref":
        if "=" in rest:
            k, v = rest.split("=", 1)
            agent.memory.set_pref(k.strip(), v.strip())
            print(f"{C.G}\u2713 pref saved: {k.strip()} = {v.strip()}{C.X}\n")
        else:
            print(f"{C.Y}usage: /memory pref key=value{C.X}\n")
    elif sub == "note":
        if rest:
            agent.memory.add_note(rest)
            print(f"{C.G}\u2713 note saved{C.X}\n")
        else:
            print(f"{C.Y}usage: /memory note <text>{C.X}\n")
    else:
        print(f"{C.Y}subcommands: clear, fact, pref, note{C.X}\n")


def save_conversation(agent):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"conversation_{ts}.md"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Agent Conversation\n\n")
        f.write(f"Date: {datetime.now().isoformat()}\n")
        f.write(f"Model: {agent.client.model}\n\n")
        for msg in agent.history:
            f.write(f"## {msg['role']}\n\n{msg['content']}\n\n")
    print(f"{C.G}[Saved: {path}]{C.X}\n")


# ─── Main Loop ───────────────────────────────────────────────────────────────

def main():
    banner()

    # Parse args
    model = "mimo-v2.5-pro"
    web_search = True
    show_thinking = True
    quiet = False
    for arg in sys.argv[1:]:
        if arg.startswith("--model="):
            model = arg.split("=", 1)[1]
        elif arg == "--no-web":
            web_search = False
        elif arg == "--no-think":
            show_thinking = False
        elif arg == "--web":
            web_search = True
        elif arg in ("-q", "--quiet"):
            quiet = True

    # Initialize agent
    try:
        agent = MiMoAgent(
            model=model, web_search=web_search,
            show_thinking=show_thinking, quiet=quiet
        )
    except Exception as e:
        print(f"{C.R}Error: {e}{C.X}")
        print(f"\n{C.Y}Pastikan session_cookie.txt ada di folder ini{C.X}")
        sys.exit(1)

    # Status line
    mem_count = len(agent.memory.data["facts"]) + len(agent.memory.data["notes"])
    print(f"{C.DIM}model:{C.X} {C.W}{model}{C.X}  "
          f"{C.DIM}web:{C.X} {C.W}{'on' if web_search else 'off'}{C.X}  "
          f"{C.DIM}think:{C.X} {C.W}{'on' if show_thinking else 'off'}{C.X}  "
          f"{C.DIM}tools:{C.X} {C.W}{len(agent.tools_schema)}{C.X}  "
          f"{C.DIM}memory:{C.X} {C.W}{mem_count} items{C.X}")
    print(f"{C.DIM}Ketik /help untuk commands. Web search aktif by default.{C.X}\n")

    while True:
        try:
            user_input = input(f"{C.BOLD}{C.C}\u276f{C.X} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{C.DIM}bye{C.X}")
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            try:
                cmd_parts = shlex.split(user_input)
            except ValueError:
                cmd_parts = user_input.split()
            cmd = cmd_parts[0].lower()

            if cmd in ("/quit", "/exit", "/q"):
                print(f"{C.DIM}bye{C.X}")
                break
            elif cmd == "/help":
                show_help()
                continue
            elif cmd == "/reset":
                agent.reset()
                print(f"{C.G}\u2713 history cleared{C.X}\n")
                continue
            elif cmd == "/model":
                if len(cmd_parts) > 1:
                    new_model = cmd_parts[1]
                    agent.client.model = new_model
                    print(f"{C.G}\u2713 model: {new_model}{C.X}\n")
                else:
                    print(f"{C.DIM}current: {agent.client.model}{C.X}\n")
                continue
            elif cmd == "/tools":
                show_tools(agent)
                continue
            elif cmd == "/web":
                agent.web_search = not agent.web_search
                state = "ON" if agent.web_search else "OFF"
                print(f"{C.G}\u2713 web search: {state}{C.X}\n")
                continue
            elif cmd == "/think":
                agent.show_thinking = not agent.show_thinking
                state = "ON" if agent.show_thinking else "OFF"
                print(f"{C.G}\u2713 thinking display: {state}{C.X}\n")
                continue
            elif cmd == "/browser":
                from tools import set_browser_visible, BROWSER_VISIBLE
                new_state = not BROWSER_VISIBLE
                set_browser_visible(new_state)
                state = "VISIBLE" if new_state else "HEADLESS"
                print(f"{C.G}\u2713 browser: {state}{C.X}\n")
                continue
            elif cmd == "/history":
                show_history(agent)
                continue
            elif cmd == "/memory":
                args = user_input[len("/memory"):].strip()
                handle_memory(agent, args)
                continue
            elif cmd == "/save":
                save_conversation(agent)
                continue
            elif cmd == "/clear":
                os.system("clear" if os.name != "nt" else "cls")
                banner()
                continue
            else:
                print(f"{C.Y}unknown: {cmd}{C.X}  {C.DIM}/help untuk list{C.X}\n")
                continue

        # Auto-learn from corrections
        correction_keywords = ["jangan", "gak usah", "bukan begitu", "salah",
                               "ganti", "rapihin", "perbaiki", "benerin",
                               "kok aneh", "jelek", "gajelas", "aneh"]
        if any(kw in user_input.lower() for kw in correction_keywords):
            agent.memory.add_note(f"User correction: {user_input[:200]}")

        # Chat
        print()
        sys.stdout.write(f"{C.BOLD}{C.G}Agent{C.X} {C.DIM}\u00bb{C.X} ")
        sys.stdout.flush()

        try:
            agent.chat_stream(user_input)
        except KeyboardInterrupt:
            sys.stdout.write(f"\n{C.Y}\u23f8 interrupted{C.X}")
        except Exception as e:
            sys.stdout.write(f"\n{C.R}error: {e}{C.X}")

        print("\n")


if __name__ == "__main__":
    main()
