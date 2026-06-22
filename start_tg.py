#!/usr/bin/env python3
"""
start_tg.py — Telegram Gateway for MiMo Agent
Handles Telegram bot integration with subagent support.
"""
from __future__ import annotations

import json
import os
import re
import signal
import sys
import time
import asyncio
import logging
import queue
import glob
import mimetypes
import textwrap
from typing import Dict, Any, List

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ─── Configuration ──────────────────────────────────────────────────────
CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")
TELEGRAM_CONFIG = os.path.join(CONFIG_DIR, "telegram.json")
ASSET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "telegram")
STATUS_CARD_PATTERN = os.path.join(ASSET_DIR, "mimo_status_*.png")
STATUS_CARD = os.path.join(ASSET_DIR, "mimo_status_0.png")
TELEGRAM_TOKEN_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b")
TELEGRAM_BOT_URL_RE = re.compile(r"bot\d{6,}:[A-Za-z0-9_-]+")
TELEGRAM_MESSAGE_LIMIT = 3900
PROCESS_UPDATE_INTERVAL = 1.2
PROCESS_ANIMATION_INTERVAL = 2.4
PROCESS_HEARTBEAT_SECONDS = 10
TELEGRAM_AGENT_RUNTIME = int(os.environ.get("MIMO_TELEGRAM_AGENT_RUNTIME", "900"))
TELEGRAM_REQUEST_TIMEOUT = int(os.environ.get("MIMO_TELEGRAM_REQUEST_TIMEOUT", "120"))
# 0 means runtime-based execution: no fixed tool-count cap, while anti-loop and per-tool timeout guards stay active.
TELEGRAM_MAX_TOOL_CALLS = int(os.environ.get("MIMO_TELEGRAM_MAX_TOOL_CALLS", "0"))
TELEGRAM_UPLOAD_LIMIT_BYTES = 49 * 1024 * 1024
UPLOAD_EXTENSIONS = {
    ".mp3", ".m4a", ".wav", ".ogg", ".oga", ".opus",
    ".png", ".jpg", ".jpeg", ".webp", ".gif",
    ".mp4", ".mov", ".webm",
    ".pdf", ".txt", ".csv", ".json", ".zip",
}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".oga", ".opus"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
PATH_RE = re.compile(
    r"(?P<path>(?:/tmp|/root|~)[^\s`'\"<>|]*\."
    r"(?:mp3|m4a|wav|ogg|oga|opus|png|jpg|jpeg|webp|gif|mp4|mov|webm|pdf|txt|csv|json|zip))",
    re.IGNORECASE,
)


def redact_tokens(value):
    """Redact Telegram tokens before logs are written."""
    if not isinstance(value, str):
        return value
    value = TELEGRAM_BOT_URL_RE.sub("bot<redacted>", value)
    return TELEGRAM_TOKEN_RE.sub("<redacted>", value)


class RedactSecretsFilter(logging.Filter):
    """Keep Telegram bot tokens out of gateway logs."""

    def filter(self, record):
        record.msg = redact_tokens(record.msg)
        if isinstance(record.args, dict):
            record.args = {key: redact_tokens(val) for key, val in record.args.items()}
        elif isinstance(record.args, tuple):
            record.args = tuple(redact_tokens(arg) for arg in record.args)
        return True

def load_config() -> Dict[str, Any]:
    """Load Telegram configuration."""
    if os.path.exists(TELEGRAM_CONFIG):
        with open(TELEGRAM_CONFIG, "r") as f:
            return json.load(f)
    return {}

def setup_logging():
    """Setup logging for Telegram gateway."""
    redact_filter = RedactSecretsFilter()
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler()
        ]
    )
    root_logger = logging.getLogger()
    root_logger.addFilter(redact_filter)
    for handler in root_logger.handlers:
        handler.addFilter(redact_filter)

    for logger_name in ("httpx", "httpcore", "telegram", "telegram.ext"):
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    return logging.getLogger(__name__)


def ignore_sighup():
    """Allow the gateway to survive after the launcher shell exits."""
    if hasattr(signal, "SIGHUP"):
        signal.signal(signal.SIGHUP, signal.SIG_IGN)

# ─── Telegram Bot ──────────────────────────────────────────────────────

class MiMoTelegramBot:
    """Telegram bot with subagent support (DeerFlow/OpenClaw pattern)."""
    
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.logger = setup_logging()
        self.agent = None
        self.subagents = {}  # Track subagent tasks
        self.agent_lock = asyncio.Lock()
        self.last_files_by_chat = {}
        
    def start(self):
        """Start the Telegram bot."""
        try:
            # Import telegram library
            from telegram import Update
            from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
            
            # Create application
            application = Application.builder().token(self.token).post_init(self._post_init).build()
            
            # Add handlers
            application.add_handler(CommandHandler("start", self.cmd_start))
            application.add_handler(CommandHandler("help", self.cmd_help))
            application.add_handler(CommandHandler("status", self.cmd_status))
            application.add_handler(CommandHandler("tools", self.cmd_tools))
            application.add_handler(CommandHandler("delegate", self.cmd_delegate))
            application.add_handler(CommandHandler("tasks", self.cmd_tasks))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            
            # Start bot
            self.logger.info(f"✅ Telegram gateway aktif!")
            self.logger.info(f"   Chat ID: {self.chat_id}")
            
            # Run the bot. python-telegram-bot's run_polling() is synchronous.
            application.run_polling(drop_pending_updates=True)
            
        except Exception as e:
            self.logger.error(f"❌ Error starting bot: {e}")
            raise

    def _telegram_command_specs(self):
        """Commands shown by Telegram when the user types '/'."""
        return [
            ("start", "Start MiMo Agent"),
            ("help", "Show features and commands"),
            ("status", "Show model, tools, and subagent status"),
            ("tools", "Show total tools and tool categories"),
            ("delegate", "Delegate a task to a subagent"),
            ("tasks", "List delegated tasks"),
        ]

    async def _post_init(self, application):
        """Register Telegram slash-command menu after the bot starts."""
        try:
            from telegram import BotCommand
            commands = [BotCommand(command, description) for command, description in self._telegram_command_specs()]
            await application.bot.set_my_commands(commands)
            self.logger.info("✅ Telegram command menu registered (%s commands)", len(commands))
        except Exception as e:
            self.logger.warning("Could not register Telegram command menu: %s", e)

    def _tool_count(self) -> int:
        try:
            from tools.tools import get_tools_schema
            return len(get_tools_schema())
        except Exception:
            return 0

    def _tool_audit_summary(self) -> Dict[str, int]:
        try:
            from tools.audit_harness import TOOLS, classify_tool
            counts: Dict[str, int] = {}
            for name in TOOLS:
                category = classify_tool(name)
                counts[category] = counts.get(category, 0) + 1
            return counts
        except Exception:
            return {}

    def _help_text(self, tool_count: int = None) -> str:
        tool_count = self._tool_count() if tool_count is None else tool_count
        return (
            "📚 **MiMo Agent Help**\n\n"
            f"**Tools: {tool_count}** runtime-registered tools\n"
            "Model: mimo-v2.5-pro\n\n"
            "**Commands:**\n"
            "/start — Start bot\n"
            "/help — Show this help\n"
            "/status — Show model, tools, audit summary\n"
            "/tools — Show tool categories\n"
            "/delegate <task> — Delegate task to subagent\n"
            "/tasks — List delegated tasks\n\n"
            "**Features:**\n"
            "• Dynamic tool registry\n"
            "• Multi-agent delegation\n"
            "• Session search / recall\n"
            "• Memory + skills\n"
            "• Browser/web automation\n"
            "• Vision/Image + Voice/TTS\n"
            "• Cron, webhooks, MCP, checkpoints\n\n"
            "Ketik pesan biasa untuk chat langsung."
        )

    def _status_text(self, tool_count: int = None, audit_summary: Dict[str, int] = None) -> str:
        tool_count = self._tool_count() if tool_count is None else tool_count
        audit_summary = self._tool_audit_summary() if audit_summary is None else audit_summary
        return (
            "📊 **MiMo Agent Status**\n\n"
            f"• Tools: {tool_count}\n"
            f"• Safe smoke: {audit_summary.get('safe_smoke', 0)}\n"
            f"• External/stateful: {audit_summary.get('external_or_stateful', 0)}\n"
            f"• Destructive/write: {audit_summary.get('destructive_or_write', 0)}\n"
            f"• Expected-fail guarded: {audit_summary.get('expected_failure', 0)}\n"
            f"• Subagents: {len(self.subagents)}\n"
            "• Model: mimo-v2.5-pro\n"
            "• Web: on\n"
            "• Think: on\n\n"
            "All systems operational! ✅"
        )
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        await update.message.reply_text(
            "🤖 **MiMo Agent** — Super Agentic Assistant\n\n"
            "Saya MiMo, model bahasa besar dari Xiaomi LLM Core Team.\n\n"
            + self._help_text(),
            parse_mode='Markdown'
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        await update.message.reply_text(self._help_text(), parse_mode='Markdown')
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        try:
            await update.message.reply_text(self._status_text(), parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Error getting status: {e}")

    async def cmd_tools(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /tools command — show total tools and categories."""
        try:
            tool_count = self._tool_count()
            audit = self._tool_audit_summary()
            text = (
                "🧰 **MiMo Tools**\n\n"
                f"Total tools: {tool_count}\n"
                f"Safe smoke: {audit.get('safe_smoke', 0)}\n"
                f"External/stateful: {audit.get('external_or_stateful', 0)}\n"
                f"Destructive/write guarded: {audit.get('destructive_or_write', 0)}\n"
                f"Expected-fail guarded: {audit.get('expected_failure', 0)}\n\n"
                "Core features:\n"
                "• Web/search + browser automation\n"
                "• File/code/git/terminal tools\n"
                "• Memory, skills, session search\n"
                "• Delegate/subagents, cron, webhooks\n"
                "• Vision, voice/TTS, MCP, checkpoints"
            )
            await update.message.reply_text(text, parse_mode='Markdown')
        except Exception as e:
            await update.message.reply_text(f"❌ Error getting tools: {e}")
    
    async def cmd_delegate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delegate command — DeerFlow-inspired subagent delegation."""
        try:
            # Get task from command args
            task = " ".join(context.args) if context.args else ""
            
            if not task:
                await update.message.reply_text(
                    "❌ Please provide a task.\n"
                    "Usage: /delegate <task description>"
                )
                return
            
            # Create subagent task
            import uuid
            task_id = str(uuid.uuid4())[:8]
            
            self.subagents[task_id] = {
                "task": task,
                "status": "running",
                "chat_id": update.effective_chat.id
            }
            
            await update.message.reply_text(
                f"🚀 Task Delegated\n\n"
                f"Task ID: {task_id}\n"
                f"Task: {task}\n"
                f"Status: Running\n\n"
                "Subagent is working on this task..."
            )
            
            asyncio.create_task(self.run_subagent(task_id, task, update))
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error delegating task: {e}")
    
    async def run_subagent(self, task_id: str, task: str, update: Update):
        """Run subagent task (DeerFlow pattern)."""
        try:
            response = await asyncio.to_thread(self._run_subagent_response, task, task_id)
            
            # Update status
            self.subagents[task_id]["status"] = "completed"
            self.subagents[task_id]["result"] = response
            
            # Notify user
            await update.message.reply_text(
                f"✅ Task Completed\n\n"
                f"Task ID: {task_id}\n"
                f"Result:\n{response[:3000]}"
            )
            
        except Exception as e:
            self.subagents[task_id]["status"] = "failed"
            self.subagents[task_id]["error"] = str(e)
            
            await update.message.reply_text(
                f"❌ Task Failed\n\n"
                f"Task ID: {task_id}\n"
                f"Error: {e}"
            )

    def _run_subagent_response(self, task: str, task_id: str) -> str:
        """Run an isolated quiet MiMoAgent instance for Telegram /delegate."""
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from core.agent import MiMoAgent

        agent = MiMoAgent(
            model="mimo-v2.5-pro",
            web_search=True,
            show_thinking=True,
            quiet=True,
            max_runtime=TELEGRAM_AGENT_RUNTIME,
            request_timeout=TELEGRAM_REQUEST_TIMEOUT,
            max_tool_calls=TELEGRAM_MAX_TOOL_CALLS,
        )
        return agent.chat(
            f"{task}\n\n"
            "[Telegram delegated subagent context: kerjakan task ini secara mandiri. "
            f"Task ID: {task_id}. Jawab ringkas dengan hasil dan bukti tool yang relevan.]"
        )
    
    async def cmd_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /tasks command — list active tasks."""
        if not self.subagents:
            await update.message.reply_text("📋 No active tasks.")
            return
        
        tasks_text = "📋 **Active Tasks**\n\n"
        
        for task_id, task_info in self.subagents.items():
            status_icon = "✅" if task_info["status"] == "completed" else "❌" if task_info["status"] == "failed" else "⏳"
            tasks_text += f"• `{task_id}` — {status_icon} {task_info['status']}\n"
            tasks_text += f"  Task: {task_info['task']}\n\n"
        
        await update.message.reply_text(tasks_text, parse_mode='Markdown')

    async def _sleep_or_stop(self, stop_event: asyncio.Event, seconds: float) -> bool:
        """Sleep until timeout or stop. Returns True when stopped."""
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    def _format_elapsed(self, seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s"
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"

    def _tool_stage(self, tool_name: str) -> str:
        if tool_name == "http_request":
            return "HTTP"
        if tool_name == "terminal":
            return "CURL/SHELL"
        if tool_name == "execute_python":
            return "API DEBUG"
        if tool_name.startswith("browser_"):
            return "CHROMIUM"
        return "TOOL"

    def _format_event_line(self, event: Dict[str, Any]) -> str:
        kind = event.get("event", "progress")
        detail = str(event.get("detail", "") or "").strip()
        tool = event.get("tool", "")

        if len(detail) > 90:
            detail = detail[:89] + "…"

        # Tool-specific emojis (Hermes-style)
        tool_emojis = {
            "web_search": "🌐",
            "web_extract": "📄",
            "read_file": "📖",
            "write_file": "✏️",
            "terminal": "💻",
            "browser_open": "🌐",
            "browser_click": "👆",
            "browser_type": "⌨️",
            "sandbox_execute": "🐍",
            "delegate_task": "🚀",
            "session_search": "🔍",
            "vision_analyze": "👁️",
            "voice_tts": "🔊",
            "memory_enhanced": "🧠",
            "thinking_analyze": "💭",
            "supervisor_plan": "📋",
        }
        
        emoji = tool_emojis.get(tool, "⚙️")

        if kind == "queued":
            return f"📥 Queued: {detail or 'Task masuk antrean'}"
        if kind == "budget":
            return f"⚙️ Mode: {detail}"
        if kind == "budget_warning":
            return f"⚠️ Budget: {detail}"
        if kind == "tool_start":
            return f"{emoji} {tool} args: {detail}"
        if kind == "tool_args_adjusted":
            return f"🧯 Guard {tool}: {detail}"
        if kind in ("tool_end", "tool_result"):
            duration = event.get("duration", 0)
            status = str(event.get("status", "ok")).upper()
            icon = "✅" if status == "OK" else "❌"
            next_step = str(event.get("next_step", "") or "").strip()
            if len(next_step) > 70:
                next_step = next_step[:69] + "…"
            line = f"{icon} {tool} {status} ({duration:.1f}s): {detail}"
            if next_step:
                line += f" | next: {next_step}"
            return line
        if kind == "retry":
            return f"🔄 Retry needed {tool}: {detail}"
        if kind == "fallback":
            return f"↪ Fallback {tool}: {detail}"
        if kind == "model_start":
            return "🧠 MiMo sedang berpikir..."
        if kind == "thinking":
            return "💭 Menganalisis..."
        if kind == "planning":
            return "📋 Membuat rencana..."
        if kind == "tool_scope":
            return f"🎯 Tools: {detail or 'Tool aktif dipilih sesuai task'}"
        if kind == "finalizing":
            return "📝 Menyusun jawaban..."
        if kind == "final":
            return f"🏁 Final: {detail or 'Jawaban final siap'}"
        if kind == "browser_lifecycle":
            tmp_removed = event.get("tmp_removed")
            suffix = f" ({tmp_removed} tmp)" if tmp_removed is not None else ""
            return f"🧹 Browser: {detail}{suffix}"
        if kind == "timeout":
            return f"⏰ Timeout: {detail}"
        if kind == "model_error":
            return f"❌ Error: {detail}"
        if kind == "max_tool_calls":
            return f"⚠️ Limit tercapai: {detail}"
        if kind in ("done", "stopped"):
            return f"✅ Selesai: {detail}"
        if detail:
            return f"→ {kind.upper()} {detail}"
        return f"→ {kind.upper()}"

    def _event_stage(self, event: Dict[str, Any]) -> str:
        kind = event.get("event", "progress")
        tool = str(event.get("tool", "") or "")
        if kind in ("queued", "start", "planning", "budget"):
            return "PLANNING"
        if kind == "tool_scope":
            return "PLANNING"
        if kind == "tool_args_adjusted":
            return "ATTENTION"
        if kind in ("model_start", "thinking"):
            return "THINKING"
        if kind == "tool_start":
            return self._tool_stage(tool)
        if kind in ("tool_end", "tool_result"):
            if event.get("status") == "error":
                return "ATTENTION"
            return f"{self._tool_stage(tool)} DONE"
        if kind in ("retry", "fallback"):
            return "FALLBACK"
        if kind == "finalizing":
            return "FINALIZING"
        if kind == "browser_lifecycle":
            return "BROWSER"
        if kind in ("final", "done", "stopped"):
            return "DONE"
        if kind in ("timeout", "model_error", "max_tool_calls", "budget_warning"):
            return "ATTENTION"
        return kind.upper()


    def _render_simple_card(self, events, started, idle, frame_index, chat_key):
        """Render a simple, clean card for basic tasks."""
        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return self._process_card_path(frame_index)
        
        try:
            width, height = 600, 200
            bg = (11, 16, 24)
            panel = (18, 26, 38)
            text = (235, 241, 245)
            muted = (139, 153, 171)
            accent = (46, 204, 113)
            
            image = Image.new("RGB", (width, height), bg)
            draw = ImageDraw.Draw(image)
            
            def font(size, bold=False):
                names = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                ]
                for name in names:
                    if os.path.exists(name):
                        return ImageFont.truetype(name, size)
                return ImageFont.load_default()
            
            title_font = font(28, True)
            body_font = font(20)
            
            # Simple layout
            draw.rectangle((20, 20, 580, 180), fill=panel, outline=(39, 53, 72), width=2)
            draw.rectangle((20, 20, 580, 28), fill=accent)
            
            draw.text((40, 45), "🤖 MiMo", fill=text, font=title_font)
            
            elapsed = self._format_elapsed(time.monotonic() - started)
            status = "masih jalan" if idle >= PROCESS_HEARTBEAT_SECONDS else "lagi jalan"
            draw.text((40, 90), f"MiMo {status}...", fill=text, font=body_font)
            draw.text((40, 125), f"Elapsed {elapsed}", fill=muted, font=body_font)
            
            safe_chat = re.sub(r"[^A-Za-z0-9_-]+", "_", chat_key or "default")[:40]
            # Use unique filename to avoid Telegram cache
            import time as time_mod
            timestamp = int(time_mod.time() * 1000) % 100000
            output_path = f"/tmp/mimo_tg_simple_{safe_chat}_{timestamp}.png"
            image.save(output_path, "PNG", optimize=True)
            return output_path
        except Exception as e:
            self.logger.debug("Simple card render failed: %s", e)
            return self._process_card_path(frame_index)

    def _render_process_card(
        self,
        events: List[Dict[str, Any]],
        started: float,
        idle: float,
        frame_index: int,
        chat_key: str,
    ) -> str:
        """Render a Telegram process card image for the current agent step."""
        # Detect simple vs complex task
        tool_events = [e for e in events if e.get("event") in ("tool_start", "tool_end", "tool_result")]
        is_simple = len(tool_events) <= 2
        
        if is_simple:
            return self._render_simple_card(events, started, idle, frame_index, chat_key)

        # User-facing Telegram progress should stay calm and simple even for
        # complex tasks; detailed executor traces are too noisy in chat.
        return self._render_simple_card(events, started, idle, frame_index, chat_key)
        
        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return self._process_card_path(frame_index)

        try:
            width, height = 900, 280
            bg = (11, 16, 24)
            panel = (18, 26, 38)
            text = (235, 241, 245)
            muted = (139, 153, 171)
            accent_frames = [
                (46, 204, 113),
                (52, 152, 219),
                (241, 196, 15),
                (231, 76, 60),
            ]
            accent = accent_frames[frame_index % len(accent_frames)]
            stage_colors = {
                "PLANNING": (52, 152, 219),
                "THINKING": (155, 89, 182),
                "HTTP": (26, 188, 156),
                "CURL/SHELL": (230, 126, 34),
                "API DEBUG": (241, 196, 15),
                "CHROMIUM": (46, 204, 113),
                "FALLBACK": (230, 126, 34),
                "BROWSER": (149, 165, 166),
                "FINALIZING": (52, 152, 219),
                "DONE": (46, 204, 113),
                "ATTENTION": (231, 76, 60),
            }

            image = Image.new("RGB", (width, height), bg)
            draw = ImageDraw.Draw(image)

            def font(size: int, bold: bool = False):
                names = [
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
                ]
                for name in names:
                    if os.path.exists(name):
                        return ImageFont.truetype(name, size)
                return ImageFont.load_default()

            title_font = font(34, True)
            stage_font = font(24, True)
            body_font = font(22)
            small_font = font(17)
            mono_font = font(17)

            current = events[-1] if events else {"event": "start", "detail": "Menyiapkan task"}
            stage = self._event_stage(current)
            stage_color = stage_colors.get(stage, accent)
            elapsed = self._format_elapsed(time.monotonic() - started)
            status = "WAITING" if idle >= PROCESS_HEARTBEAT_SECONDS else "ACTIVE"
            step_events = [event for event in events if event.get("event") not in {"thinking"}]
            step_count = max(1, len(step_events) or 1)

            draw.rectangle((28, 26, 872, 254), fill=panel, outline=(39, 53, 72), width=2)
            draw.rectangle((28, 26, 872, 34), fill=stage_color)
            draw.text((54, 58), "MiMo Agent Executor", fill=text, font=title_font)
            draw.text((54, 105), f"STEP {step_count:02d}", fill=stage_color, font=stage_font)
            draw.text((190, 105), stage, fill=text, font=stage_font)
            draw.text((54, 145), f"Elapsed {elapsed}  |  {status}", fill=muted, font=small_font)

            dot_x = 700
            for i in range(4):
                color = accent_frames[(frame_index + i) % len(accent_frames)]
                radius = 12 + (4 if i == frame_index % 4 else 0)
                draw.ellipse((dot_x + i * 34, 70, dot_x + i * 34 + radius, 70 + radius), fill=color)

            bar_x, bar_y, bar_w, bar_h = 54, 180, 792, 16
            draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_w, bar_y + bar_h), radius=7, fill=(34, 45, 61))
            fill_w = int(bar_w * ((frame_index % 12) + 1) / 12)
            draw.rounded_rectangle((bar_x, bar_y, bar_x + fill_w, bar_y + bar_h), radius=7, fill=stage_color)

            detail = str(current.get("detail", "") or self._format_event_line(current))
            detail = re.sub(r"\s+", " ", detail).strip()
            y = 228
            for line in textwrap.wrap(detail, width=65)[:1]:
                draw.text((54, y), line, fill=text, font=body_font)
                y += 28

            safe_chat = re.sub(r"[^A-Za-z0-9_-]+", "_", chat_key or "default")[:40]
            # Use unique filename to avoid Telegram cache
            import time as time_mod
            timestamp = int(time_mod.time() * 1000) % 100000
            output_path = f"/tmp/mimo_tg_process_{safe_chat}_{timestamp}.png"
            image.save(output_path, "PNG", optimize=True)
            return output_path
        except Exception as e:
            self.logger.debug("Dynamic process card render failed: %s", e)
            return self._process_card_path(frame_index)

    def _process_caption(self, events: List[Dict[str, Any]], started: float, idle: float) -> str:
        """Tiny Telegram progress caption.

        Keep noisy executor/tool traces out of chat. The detailed trace stays in
        logs/tests; Telegram only needs to reassure the user that MiMo is still
        working.
        """
        elapsed = self._format_elapsed(time.monotonic() - started)
        if idle >= PROCESS_HEARTBEAT_SECONDS:
            return f"MiMo masih jalan... ({elapsed})"
        dot_count = int(time.monotonic() - started) % 3 + 1
        return f"MiMo lagi jalan{'.' * dot_count} ({elapsed})"

    def _process_card_path(self, frame_index: int = 0) -> str:
        frames = sorted(glob.glob(STATUS_CARD_PATTERN))
        if not frames and os.path.exists(STATUS_CARD):
            frames = [STATUS_CARD]
        if not frames:
            return ""
        return frames[frame_index % len(frames)]

    async def _send_process_card(self, update, caption: str, frame_index: int = 0, card_path: str = ""):
        card_path = card_path or self._process_card_path(frame_index)
        if card_path:
            try:
                with open(card_path, "rb") as image:
                    return await update.message.reply_photo(photo=image, caption=caption)
            except Exception as e:
                self.logger.debug("Progress card send failed: %s", e)
        return await update.message.reply_text(caption)

    async def _edit_process_card(self, status_message, caption: str, frame_index: int = 0, card_path: str = ""):
        try:
            if getattr(status_message, "photo", None):
                card_path = card_path or self._process_card_path(frame_index)
                if card_path:
                    try:
                        from telegram import InputMediaPhoto
                        with open(card_path, "rb") as image:
                            media = InputMediaPhoto(media=image, caption=caption)
                            await status_message.edit_media(media=media)
                            return
                    except Exception as e:
                        message = str(e).lower()
                        if "message is not modified" not in message:
                            self.logger.debug("Progress media update failed: %s", e)
                await status_message.edit_caption(caption=caption)
            else:
                await status_message.edit_text(caption)
        except Exception as e:
            message = str(e).lower()
            if "message is not modified" not in message:
                self.logger.debug("Progress update failed: %s", e)

    async def _process_feed(self, update, context, progress_queue, stop_event: asyncio.Event):
        """Show a single auto-cleaned process card fed by real agent events."""
        try:
            from telegram.constants import ChatAction
        except Exception:
            ChatAction = None

        status_message = None
        chat_key = self._chat_key(update)
        start_time = time.monotonic()
        last_typing = 0.0
        last_update = 0.0
        last_event_time = start_time
        frame_index = 0
        events: List[Dict[str, Any]] = []

        try:
            initial_card = self._render_process_card(events, start_time, 0.0, frame_index, chat_key)
            status_message = await self._send_process_card(
                update,
                self._process_caption(events, start_time, 0.0),
                frame_index,
                initial_card,
            )

            while not stop_event.is_set() or not progress_queue.empty():
                now = time.monotonic()
                changed = False

                while True:
                    try:
                        event = progress_queue.get_nowait()
                    except queue.Empty:
                        break
                    events.append(event)
                    last_event_time = now
                    changed = True

                # Keep typing animation active (every 2 seconds)
                if ChatAction and now - last_typing >= 2.0:
                    try:
                        await context.bot.send_chat_action(
                            chat_id=update.effective_chat.id,
                            action=ChatAction.TYPING,
                        )
                    except Exception as e:
                        self.logger.debug("Typing action failed: %s", e)
                    last_typing = now

                idle = now - last_event_time
                heartbeat = idle >= PROCESS_HEARTBEAT_SECONDS and now - last_update >= PROCESS_HEARTBEAT_SECONDS
                animate = (
                    bool(getattr(status_message, "photo", None))
                    and now - last_update >= PROCESS_ANIMATION_INTERVAL
                )
                if status_message and (changed or heartbeat or animate or now - last_update >= 20):
                    frame_index += 1
                    card_path = self._render_process_card(events, start_time, idle, frame_index, chat_key)
                    await self._edit_process_card(
                        status_message,
                        self._process_caption(events, start_time, idle),
                        frame_index,
                        card_path,
                    )
                    last_update = now

                if await self._sleep_or_stop(stop_event, PROCESS_UPDATE_INTERVAL):
                    break

            while not progress_queue.empty():
                try:
                    events.append(progress_queue.get_nowait())
                except queue.Empty:
                    break

            if status_message:
                frame_index += 1
                card_path = self._render_process_card(events, start_time, 0.0, frame_index, chat_key)
                await self._edit_process_card(
                    status_message,
                    self._process_caption(events, start_time, 0.0),
                    frame_index,
                    card_path,
                )
            return status_message

        except Exception as e:
            self.logger.debug("Process feed failed: %s", e)
            return status_message

    def _telegram_context_message(self, message: str) -> str:
        return (
            f"{message}\n\n"
            "[Telegram gateway context: pesan ini datang dari chat Telegram yang sudah authenticated. "
            "Jangan minta bot token atau chat id untuk mengirim hasil ke chat ini. "
            "Jika kamu membuat audio, screenshot, gambar, atau dokumen lokal, sebutkan path file lokalnya; "
            "gateway Telegram akan upload file itu otomatis ke chat yang sama. "
            "Jika user bilang 'kirim di sini', gunakan file lokal terakhir yang relevan dari percakapan.]"
        )

    def _get_agent_response(self, message: str, progress_callback=None) -> str:
        """Run the sync MiMo agent for Telegram without terminal UI output."""
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from core.agent import MiMoAgent
        try:
            from lib import browser_engine
        except Exception:
            browser_engine = None

        if not self.agent:
            self.agent = MiMoAgent(
                model="mimo-v2.5-pro",
                web_search=True,
                show_thinking=True,
                quiet=True,
                max_runtime=TELEGRAM_AGENT_RUNTIME,
                request_timeout=TELEGRAM_REQUEST_TIMEOUT,
                max_tool_calls=TELEGRAM_MAX_TOOL_CALLS,
            )

        if browser_engine:
            browser_engine.begin_task("telegram")
        try:
            return self.agent.chat(
                self._telegram_context_message(message),
                progress_callback=progress_callback,
            )
        finally:
            if browser_engine:
                status = browser_engine.end_task("telegram", close_now=True)
                if progress_callback:
                    progress_callback({
                        "event": "browser_lifecycle",
                        "detail": "Browser ditutup setelah task Telegram dan /tmp/DrissionPage dibersihkan",
                        "status": status.get("status", "closed"),
                        "tmp_removed": status.get("tmp_removed", 0),
                        "idle_timeout_seconds": status.get("idle_timeout_seconds"),
                    })

    def _chat_key(self, update) -> str:
        chat = getattr(update, "effective_chat", None)
        return str(getattr(chat, "id", self.chat_id or "default"))

    def _valid_upload_file(self, path: str) -> bool:
        path = os.path.abspath(os.path.expanduser(path.strip()))
        ext = os.path.splitext(path)[1].lower()
        if ext not in UPLOAD_EXTENSIONS:
            return False
        if not os.path.isfile(path):
            return False
        return os.path.getsize(path) <= TELEGRAM_UPLOAD_LIMIT_BYTES

    def _dedupe_files(self, files: List[str]) -> List[str]:
        result = []
        seen = set()
        for path in files:
            clean = os.path.abspath(os.path.expanduser(str(path).strip().strip("\"'.,);]}>")))
            if clean in seen or not self._valid_upload_file(clean):
                continue
            seen.add(clean)
            result.append(clean)
        return result

    def _extract_upload_files(self, text: str) -> List[str]:
        if not text:
            return []
        candidates = [match.group("path") for match in PATH_RE.finditer(text)]
        return self._dedupe_files(candidates)

    def _remember_files(self, chat_key: str, files: List[str]):
        files = self._dedupe_files(files)
        if not files:
            return
        existing = self.last_files_by_chat.get(chat_key, [])
        self.last_files_by_chat[chat_key] = self._dedupe_files(existing + files)[-10:]

    def _wants_last_file_sent(self, message: str) -> bool:
        text = (message or "").lower()
        send_words = ("kirim", "send", "upload", "post", "drop")
        here_words = ("sini", "tele", "telegram", "chat ini", "di sini", "kesini", "ke sini")
        file_words = ("file", "audio", "suara", "tts", "mp3", "screenshot", "ss", "gambar", "foto", "dokumen")
        return any(word in text for word in send_words) and (
            any(word in text for word in here_words) or any(word in text for word in file_words)
        )

    async def _send_file_to_chat(self, update, path: str):
        ext = os.path.splitext(path)[1].lower()
        filename = os.path.basename(path)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"

        with open(path, "rb") as file_obj:
            if ext in AUDIO_EXTENSIONS:
                return await update.message.reply_audio(
                    audio=file_obj,
                    filename=filename,
                    caption=filename,
                )
            if ext in IMAGE_EXTENSIONS:
                return await update.message.reply_photo(
                    photo=file_obj,
                    caption=filename,
                )
            if ext in VIDEO_EXTENSIONS:
                return await update.message.reply_video(
                    video=file_obj,
                    filename=filename,
                    caption=filename,
                )
            return await update.message.reply_document(
                document=file_obj,
                filename=filename,
                caption=f"{filename} ({mime})",
            )

    async def _send_attachments(self, update, files: List[str]) -> int:
        sent = 0
        for path in self._dedupe_files(files):
            try:
                await self._send_file_to_chat(update, path)
                sent += 1
            except Exception as e:
                self.logger.debug("Attachment send failed for %s: %s", path, e)
                await update.message.reply_text(f"Gagal kirim file: {path}\n{e}")
        return sent

    def _split_message(self, text: str, limit: int = TELEGRAM_MESSAGE_LIMIT) -> List[str]:
        """Split long Telegram replies without cutting normal paragraphs first."""
        if len(text) <= limit:
            return [text]

        chunks = []
        current = ""
        for paragraph in text.split("\n\n"):
            piece = paragraph + "\n\n"
            if len(piece) > limit:
                if current:
                    chunks.append(current.rstrip())
                    current = ""
                for index in range(0, len(piece), limit):
                    chunks.append(piece[index:index + limit].rstrip())
                continue
            if len(current) + len(piece) > limit:
                chunks.append(current.rstrip())
                current = piece
            else:
                current += piece

        if current.strip():
            chunks.append(current.rstrip())
        return chunks or [text[:limit]]

    async def _send_response(self, update, response: str):
        """Send final response safely, including long answers."""
        response = (response or "").strip()
        if not response:
            response = "✅ Task selesai, tapi agent tidak menghasilkan teks jawaban. Coba tanyakan lebih spesifik."

        for chunk in self._split_message(response):
            await update.message.reply_text(chunk)
        
        # Cleanup old images after sending response
        try:
            import glob as glob_mod
            for f in glob_mod.glob("/tmp/mimo_tg_*.png"):
                try:
                    if os.path.getmtime(f) < time.time() - 1800:  # 30 minutes
                        os.remove(f)
                except:
                    pass
        except:
            pass
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages."""
        status_message = None
        stop_event = asyncio.Event()
        feed_task = None
        progress_queue = queue.Queue()
        current_files: List[str] = []

        try:
            message = update.message.text
            self.logger.info("Received message (%s chars)", len(message))
            chat_key = self._chat_key(update)

            def progress_callback(event):
                event_files = event.get("files") or []
                current_files.extend(event_files)
                self._remember_files(chat_key, event_files)
                progress_queue.put(event)

            feed_task = asyncio.create_task(
                self._process_feed(update, context, progress_queue, stop_event)
            )

            async with self.agent_lock:
                response = await asyncio.to_thread(
                    self._get_agent_response,
                    message,
                    progress_callback,
                )

            stop_event.set()
            status_message = await feed_task

            response_files = self._extract_upload_files(response)
            self._remember_files(chat_key, response_files)
            upload_files = response_files or self._dedupe_files(current_files)
            if not upload_files and self._wants_last_file_sent(message):
                upload_files = self.last_files_by_chat.get(chat_key, [])

            # Delete progress card (clean output)
            if status_message:
                try:
                    await status_message.delete()
                except:
                    pass

            # Send only final response (clean)
            if (response or "").strip():
                await self._send_response(update, response)
            elif not upload_files:
                await self._send_response(update, response)

            if upload_files:
                await self._send_attachments(update, upload_files)
            
        except Exception as e:
            stop_event.set()
            if feed_task:
                try:
                    status_message = await feed_task
                except Exception:
                    status_message = None
            if status_message:
                try:
                    await status_message.delete()
                except Exception:
                    pass
            self.logger.error(f"Error handling message: {e}")
            await update.message.reply_text(f"❌ Error: {e}")

# ─── Main ──────────────────────────────────────────────────────────────

def main():
    """Main entry point."""
    ignore_sighup()

    # Load config
    config = load_config()
    
    token = config.get("telegram_token", "")
    chat_id = config.get("telegram_chat_id", "")
    
    if not token:
        print("❌ No Telegram token configured!")
        print("Run: mimo setup")
        sys.exit(1)
    
    # Create and start bot
    bot = MiMoTelegramBot(token, chat_id)
    
    print(f"✅ Telegram gateway aktif!")
    print("   Token: configured")
    print(f"   Chat ID: {chat_id}")
    
    bot.start()

if __name__ == "__main__":
    main()

# ─── Auto-Cleanup Old Images ──────────────────────────────────────────────
import glob as glob_mod

def cleanup_old_images():
    """Clean up mimo images older than 30 minutes."""
    pattern = "/tmp/mimo_tg_*.png"
    count = 0
    for f in glob_mod.glob(pattern):
        try:
            if os.path.getmtime(f) < time.time() - 1800:  # 30 minutes
                os.remove(f)
                count += 1
        except:
            pass
    return count
