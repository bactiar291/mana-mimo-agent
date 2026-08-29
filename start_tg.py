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
# How often the feed loop wakes up. Small enough that the spinner reads as motion.
PROCESS_UPDATE_INTERVAL = 0.7
# Minimum gap between two edits of the same status message (Bot API rate safety).
PROCESS_EDIT_MIN_INTERVAL = 1.1
# Telegram clears the "typing…" bubble after ~5s, so refresh it well before that.
TYPING_REFRESH_SECONDS = 3.5
PROCESS_ANIMATION_INTERVAL = 2.4
PROCESS_HEARTBEAT_SECONDS = 10
# How many collapsed action lines the live timeline keeps visible (Hermes-style).
PROCESS_TIMELINE_LINES = 12
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
    
    def __init__(self, token: str, owner_chat_id: str, admin_chat_ids=None, admin_password: str = ""):
        self.token = token
        self.owner_chat_id = str(owner_chat_id).strip()
        self.admin_chat_ids = {str(chat_id).strip() for chat_id in (admin_chat_ids or []) if str(chat_id).strip()}
        self.allowed_chat_ids = {self.owner_chat_id, *self.admin_chat_ids} if self.owner_chat_id else set(self.admin_chat_ids)
        self.admin_password = str(admin_password or "").strip()
        self.unlocked_admin_chats = set()
        self.admin_unlock_timestamps = {}
        self.logger = setup_logging()
        self.agent = None
        self.subagents = {}  # Track subagent tasks
        self.agent_lock = asyncio.Lock()
        self.last_files_by_chat = {}
        self._access_denied_notice_sent = set()
        self._admin_unlock_notice_sent = set()

    def _chat_role(self, update) -> str | None:
        chat = getattr(update, "effective_chat", None)
        chat_id = str(getattr(chat, "id", ""))
        if not chat_id:
            return None
        if chat_id == self.owner_chat_id:
            return "owner"
        if chat_id in self.admin_chat_ids:
            return "admin"
        return None

    def _is_allowed_chat(self, update) -> bool:
        role = self._chat_role(update)
        if role == "owner":
            return True
        chat = getattr(update, "effective_chat", None)
        chat_id = str(getattr(chat, "id", ""))
        return bool(chat_id and chat_id in self.unlocked_admin_chats)

    def _is_unlocked_admin(self, update) -> bool:
        chat = getattr(update, "effective_chat", None)
        chat_id = str(getattr(chat, "id", ""))
        return bool(chat_id and chat_id in self.unlocked_admin_chats)

    def _is_admin_chat(self, update) -> bool:
        return self._chat_role(update) == "admin"

    async def _deny_unauthorized(self, update, reason: str = ""):
        try:
            msg = ""
            if reason:
                msg = reason
            if getattr(update, "message", None) and msg:
                await update.message.reply_text(msg)
        except Exception:
            pass

    async def _prompt_admin_unlock(self, update):
        chat = getattr(update, "effective_chat", None)
        chat_id = str(getattr(chat, "id", ""))
        if not chat_id or chat_id in self._admin_unlock_notice_sent:
            return
        self._admin_unlock_notice_sent.add(chat_id)
        try:
            if getattr(update, "message", None):
                await update.message.reply_text("🔐 Admin mode. Kirim: `unlock <password>`", parse_mode='Markdown')
        except Exception:
            pass

    def _unlock_admin_chat(self, update, password: str) -> bool:
        chat = getattr(update, "effective_chat", None)
        chat_id = str(getattr(chat, "id", ""))
        if not chat_id:
            return False
        if self.admin_password and password == self.admin_password:
            self.unlocked_admin_chats.add(chat_id)
            self.admin_unlock_timestamps[chat_id] = time.time()
            return True
        return False

    def _is_admin_unlocked(self, update) -> bool:
        chat = getattr(update, "effective_chat", None)
        chat_id = str(getattr(chat, "id", ""))
        if not chat_id or chat_id not in self.unlocked_admin_chats:
            return False
        ttl = 600
        ts = self.admin_unlock_timestamps.get(chat_id, 0)
        if ts and (time.time() - ts) <= ttl:
            return True
        self.unlocked_admin_chats.discard(chat_id)
        self.admin_unlock_timestamps.pop(chat_id, None)
        return False

    def _refresh_admin_unlock(self, update):
        chat = getattr(update, "effective_chat", None)
        chat_id = str(getattr(chat, "id", ""))
        if chat_id in self.unlocked_admin_chats:
            self.admin_unlock_timestamps[chat_id] = time.time()
        
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
            self.logger.info(f"   Owner Chat ID: {self.owner_chat_id}")
            
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

    def _tool_profile_name(self) -> str:
        try:
            from tools.tool_profile import active_profile
            return active_profile()
        except Exception:
            return "unknown"

    def _help_text(self, tool_count: int = None) -> str:
        tool_count = self._tool_count() if tool_count is None else tool_count
        return (
            "📚 **MiMo Agent Help**\n\n"
            f"**Tools: {tool_count}** aktif (profil: {self._tool_profile_name()})\n"
            "Model: mimo-v2.5-pro\n\n"
            "**Commands:**\n"
            "/start — Start bot\n"
            "/help — Show this help\n"
            "/status — Show model, tools, audit summary\n"
            "/tools — Show tool categories\n"
            "/delegate <task> — Delegate task to subagent\n"
            "/tasks — List delegated tasks\n\n"
            "**Yang benar-benar jalan:**\n"
            "• File, code, git, terminal, Python\n"
            "• Web search + extract + HTTP request\n"
            "• Browser automation (Chromium headless)\n"
            "• Memory, skills, todo, delegasi subagent\n"
            "• OCR (tesseract), screenshot, TTS (edge-tts)\n\n"
            "Ketik pesan biasa untuk chat langsung."
        )

    def _status_text(self, tool_count: int = None, audit_summary: Dict[str, int] = None) -> str:
        tool_count = self._tool_count() if tool_count is None else tool_count
        audit_summary = self._tool_audit_summary() if audit_summary is None else audit_summary
        return (
            "📊 MiMo Agent Status\n\n"
            f"• Tools: {tool_count}\n"
            f"• Profil tool: {self._tool_profile_name()}\n"
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
        if not self._is_allowed_chat(update):
            await self._deny_unauthorized(update)
            return
        if self._chat_role(update) == "admin" and not self._is_admin_unlocked(update):
            await self._prompt_admin_unlock(update)
            return
        await update.message.reply_text(
            "🤖 MiMo Agent\n\n"
            "Saya MiMo, model bahasa besar dari Xiaomi LLM Core Team.\n\n"
            + self._help_text()
        )
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command."""
        if not self._is_allowed_chat(update):
            await self._deny_unauthorized(update)
            return
        if self._chat_role(update) == "admin" and not self._is_admin_unlocked(update):
            await self._prompt_admin_unlock(update)
            return
        await update.message.reply_text(self._help_text())
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        if not self._is_allowed_chat(update):
            await self._deny_unauthorized(update)
            return
        if self._chat_role(update) == "admin" and not self._is_admin_unlocked(update):
            await self._prompt_admin_unlock(update)
            return
        try:
            role = self._chat_role(update)
            text = self._status_text()
            if role == "admin":
                text += "\n\nRole: admin"
            elif role == "owner":
                text += "\n\nRole: owner"
            await update.message.reply_text(text)
        except Exception as e:
            await update.message.reply_text(f"❌ Error getting status: {e}")

    async def cmd_tools(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /tools command — show total tools and categories."""
        if not self._is_allowed_chat(update):
            await self._deny_unauthorized(update)
            return
        if self._chat_role(update) == "admin" and not self._is_admin_unlocked(update):
            await self._prompt_admin_unlock(update)
            return
        try:
            tool_count = self._tool_count()
            audit = self._tool_audit_summary()
            text = (
                "🧰 MiMo Tools\n\n"
                f"Total tools aktif: {tool_count}\n"
                f"Profil: {self._tool_profile_name()}\n"
                f"Safe smoke: {audit.get('safe_smoke', 0)}\n"
                f"External/stateful: {audit.get('external_or_stateful', 0)}\n"
                f"Destructive/write guarded: {audit.get('destructive_or_write', 0)}\n"
                f"Expected-fail guarded: {audit.get('expected_failure', 0)}\n\n"
                "Kategori:\n"
                "• File/code/git/terminal/Python\n"
                "• Web search, extract, HTTP, download\n"
                "• Browser automation (Chromium headless)\n"
                "• Memory, skills, todo, delegasi subagent\n"
                "• OCR + screenshot + TTS (binary-backed)\n\n"
                "Set MIMO_TOOL_PROFILE=full untuk membuka seluruh registry lama."
            )
            await update.message.reply_text(text)
        except Exception as e:
            await update.message.reply_text(f"❌ Error getting tools: {e}")
    
    async def cmd_delegate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /delegate command — DeerFlow-inspired subagent delegation."""
        if not self._is_allowed_chat(update):
            await self._deny_unauthorized(update)
            return
        if self._chat_role(update) == "admin" and not self._is_admin_unlocked(update):
            await self._prompt_admin_unlock(update)
            return
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
        if not self._is_allowed_chat(update):
            await self._deny_unauthorized(update)
            return
        if self._chat_role(update) == "admin" and not self._is_admin_unlocked(update):
            await self._prompt_admin_unlock(update)
            return
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

    def _sanitize_progress_detail(self, value: Any, limit: int = 180) -> str:
        """Keep live Telegram telemetry useful without leaking credentials."""
        text = str(value or "")
        text = redact_tokens(text)
        # Credentials may appear in commands, headers, URLs, or tool arguments.
        text = re.sub(
            r"(?i)(authorization\s*[:=]\s*(?:bearer|basic)\s+)([^\s'\"`,;]+)",
            r"\1[REDACTED]",
            text,
        )
        text = re.sub(
            r"(?i)(x-api-key|api[_-]?key|access[_-]?token|refresh[_-]?token|session|cookie|password|secret)"
            r"(\s*[:=]\s*)([^\s'\"`,;&]+)",
            r"\1\2[REDACTED]",
            text,
        )
        text = re.sub(
            r"(?i)([?&](?:token|access_token|api_key|key|signature|sig|password|secret|session)=)([^&#\s]+)",
            r"\1[REDACTED]",
            text,
        )
        text = re.sub(r"\s+", " ", text).strip()
        return text if len(text) <= limit else text[:limit - 1] + "…"

    def _short_path(self, detail: str) -> str:
        """Hermes-style target: keep 'name.py L10-42', drop long parent dirs."""
        detail = (detail or "").strip()
        if not detail:
            return ""
        lines_suffix = ""
        match = re.search(r"\s(L\d+(?:-\d+|\+)?)$", detail)
        if match:
            lines_suffix = " " + match.group(1)
            detail = detail[: match.start()].strip()
        if detail.startswith("/") and detail.count("/") > 2:
            detail = os.path.basename(detail) or detail
        return f"{detail}{lines_suffix}"

    def _tool_activity_line(self, tool: str, detail: str) -> str:
        """Translate real tool starts into short Hermes-style, privacy-safe activity."""
        detail = self._sanitize_progress_detail(detail, 120)
        if tool == "skill_view":
            return f"📚 Reading skill {detail or '…'}"
        if tool in {"skills_list", "skill_auto_load"}:
            return "📚 Checking available skills"
        if tool == "read_file":
            return f"📖 Reading {self._short_path(detail) or 'file'}"
        if tool in {"write_file", "append_file"}:
            return f"✍️ Writing {self._short_path(detail) or 'file'}"
        if tool in {"patch_file", "replace_in_file"}:
            return f"🔧 Editing {self._short_path(detail) or 'file'}"
        if tool == "search_files":
            path_match = re.search(r"(?:\bin\s+|\bpath[=:]\s*)([^\s,]+)", detail, re.IGNORECASE)
            path = path_match.group(1) if path_match else "project files"
            return f"🔎 Searching files in {path}"
        if tool in {"todo", "kanban_task", "kanban_move", "kanban_complete", "supervisor_plan", "supervisor_execute", "supervisor_adapt"}:
            return "📋 Updating tasks"
        if tool == "web_search":
            # Search terms can contain private identifiers; show the action, not the query.
            return "🌐 Searching web"
        if tool == "web_extract":
            return "📄 Reading web page"
        if tool in {"browser_open", "nodriver_open"}:
            host_match = re.search(r"https?://([^/\s?#]+)", detail, re.IGNORECASE)
            host = host_match.group(1) if host_match else "website"
            return f"🌐 Opening {host}"
        if tool in {"browser_click", "nodriver_click"}:
            return "👆 Clicking page element"
        if tool in {"browser_type", "nodriver_type"}:
            return "⌨️ Filling page form"
        if tool.startswith("browser_") or tool.startswith("nodriver_"):
            return "🌐 Using browser"
        if tool == "terminal":
            cmd = self._sanitize_progress_detail(detail, 60)
            return f"💻 Running terminal{f' {cmd}' if cmd else ''}"
        if tool in {"execute_python", "sandbox_execute"}:
            head = self._sanitize_progress_detail(detail, 48)
            return f"🐍 Running code{f' {head}…' if head else ''}"
        if tool == "session_search":
            return "🔍 Searching session history"
        if tool == "delegate_task":
            return "🚀 Delegating subtask"
        if tool in {"memory", "memory_enhanced"}:
            return "🧠 Updating memory"
        if tool == "vision_analyze":
            return "👁️ Analyzing image"
        if tool in {"voice_tts", "text_to_speech"}:
            return "🔊 Generating audio"
        return f"⚙️ Running {tool or 'tool'}"

    def _format_event_line(self, event: Dict[str, Any]) -> str:
        kind = event.get("event", "progress")
        detail = self._sanitize_progress_detail(event.get("detail", ""), 120)
        tool = self._sanitize_progress_detail(event.get("tool", ""), 60)

        if len(detail) > 90:
            detail = detail[:89] + "…"

        if kind == "queued":
            return f"📥 Queued: {detail or 'Task masuk antrean'}"
        if kind == "budget":
            return f"⚙️ Mode: {detail}"
        if kind == "budget_warning":
            return f"⚠️ Budget: {detail}"
        if kind == "tool_start":
            return self._tool_activity_line(tool, detail)
        if kind == "tool_args_adjusted":
            return f"🧯 Guard {tool}: {detail}"
        if kind in ("tool_end", "tool_result"):
            duration = event.get("duration", 0)
            status = str(event.get("status", "ok")).upper()
            icon = "✅" if status == "OK" else "❌"
            action = self._tool_activity_line(tool, "").split(" • ", 1)[0]
            next_step = str(event.get("next_step", "") or "").strip()
            if len(next_step) > 70:
                next_step = next_step[:69] + "…"
            line = f"{icon} {action} {status} ({duration:.1f}s): {detail}"
            if next_step:
                line += f" | next: {self._sanitize_progress_detail(next_step, 70)}"
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

    def _progress_message_for_event(self, event: Dict[str, Any]) -> Optional[str]:
        """Return one safe Telegram message for one real execution event.

        Planning and model-thought events are intentionally quiet: the chat receives
        only observable task steps, in the order the agent actually emits them.
        """
        visible_events = {
            "tool_start", "tool_end", "tool_result", "tool_args_adjusted",
            "retry", "fallback", "timeout", "model_error", "browser_lifecycle",
        }
        if event.get("event") not in visible_events:
            return None
        return self._sanitize_progress_detail(self._format_event_line(event), TELEGRAM_MESSAGE_LIMIT)

    def _process_caption(self, events: List[Dict[str, Any]], started: float, idle: float) -> str:
        """Render a compact, truthful live execution timeline for Telegram."""
        elapsed = self._format_elapsed(time.monotonic() - started)
        # Braille spinner: 10 frames at ~8 fps reads as continuous motion while the
        # message is edited in place, the same feel as the Hermes CLI spinner.
        spinner_frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        frame = spinner_frames[int(time.monotonic() * 8) % len(spinner_frames)]
        current = events[-1] if events else {"event": "queued", "detail": "Task diterima"}
        current_line = self._format_event_line(current)
        current_line = self._sanitize_progress_detail(current_line, 280)
        stage = self._event_stage(current)
        tool_calls = current.get("tool_calls")
        max_tool_calls = current.get("max_tool_calls")
        tool_progress = ""
        if isinstance(tool_calls, int):
            cap = "∞" if not isinstance(max_tool_calls, int) or max_tool_calls >= 1_000_000 else str(max_tool_calls)
            tool_progress = f" • tool {tool_calls}/{cap}"

        # Keep high-signal execution evidence. Suppress repetitive thinking and
        # planning chatter, but retain actual tool starts/results/errors/fallbacks.
        trace_events = [
            event for event in events
            if event.get("event") in {
                "tool_start", "tool_args_adjusted",
                "retry", "fallback", "timeout", "model_error", "browser_lifecycle",
            }
        ]
        # Collapse consecutive identical actions into "line (×N)" the way the Hermes
        # timeline does, so a loop of reads/edits stays readable instead of scrolling.
        collapsed: List[List[Any]] = []
        for event in trace_events:
            line = self._sanitize_progress_detail(self._format_event_line(event), 280)
            if not line:
                continue
            if collapsed and collapsed[-1][0] == line:
                collapsed[-1][1] += 1
            else:
                collapsed.append([line, 1])

        trace_lines: List[str] = []
        for line, count in collapsed[-PROCESS_TIMELINE_LINES:]:
            trace_lines.append(line if count == 1 else f"{line} (×{count})")

        total_actions = sum(count for _, count in collapsed)
        hidden = total_actions - sum(
            count for _, count in collapsed[-PROCESS_TIMELINE_LINES:]
        )

        lines = [
            f"🤖 MiMo Agent • LIVE {frame}",
            f"⏱ {elapsed} • {stage}{tool_progress}",
            "",
            "▶️ Sekarang",
            current_line,
        ]
        if trace_lines:
            lines.extend(["", f"📜 Timeline ({total_actions} aksi)"])
            if hidden > 0:
                lines.append(f"… {hidden} aksi sebelumnya")
            lines.extend(trace_lines)
        if idle >= PROCESS_HEARTBEAT_SECONDS:
            lines.extend(["", "⌛ Menunggu respons tool/model — task masih aktif."])

        caption = "\n".join(lines)
        return caption[:TELEGRAM_MESSAGE_LIMIT - 24] + ("…" if len(caption) >= TELEGRAM_MESSAGE_LIMIT else "")

    def _process_card_path(self, frame_index: int = 0) -> str:
        frames = sorted(glob.glob(STATUS_CARD_PATTERN))
        if not frames and os.path.exists(STATUS_CARD):
            frames = [STATUS_CARD]
        if not frames:
            return ""
        return frames[frame_index % len(frames)]

    async def _send_process_card(self, update, caption: str, frame_index: int = 0, card_path: str = ""):
        """Send lightweight text-only progress, not photo cards.

        User asked for Hermes-style live typing/progress instead of image reloads.
        We still keep the progress feed + typing indicator, but the visible message is
        always plain text so Telegram updates feel native and smoother.
        """
        return await update.message.reply_text(caption)

    async def _edit_process_card(self, status_message, caption: str, frame_index: int = 0, card_path: str = ""):
        try:
            await status_message.edit_text(caption)
        except Exception as e:
            message = str(e).lower()
            if "message is not modified" not in message:
                self.logger.debug("Progress update failed: %s", e)

    async def _process_feed(self, update, context, progress_queue, stop_event: asyncio.Event):
        """Hermes-style live status: ONE message, edited smoothly in place.

        Instead of spamming the chat with one message per tool event, the gateway
        keeps a single status message and rewrites it as the task progresses. The
        spinner keeps animating even while a slow tool is running, so the chat
        never looks frozen, and Telegram's native typing indicator stays warm.

        Returns the status message so the caller can delete it before sending the
        real answer.
        """
        try:
            from telegram.constants import ChatAction
        except Exception:
            ChatAction = None

        started = time.monotonic()
        events: List[Dict[str, Any]] = []
        status_message = None
        last_caption = ""
        last_edit = 0.0
        last_typing = 0.0
        last_event_at = started

        try:
            while not stop_event.is_set() or not progress_queue.empty():
                now = time.monotonic()

                # Keep the native "typing…" bubble alive (Telegram expires it ~5s).
                if ChatAction and now - last_typing >= TYPING_REFRESH_SECONDS:
                    try:
                        await context.bot.send_chat_action(
                            chat_id=update.effective_chat.id,
                            action=ChatAction.TYPING,
                        )
                    except Exception as e:
                        self.logger.debug("Typing action failed: %s", e)
                    last_typing = now

                drained = False
                while True:
                    try:
                        events.append(progress_queue.get_nowait())
                        drained = True
                    except queue.Empty:
                        break
                if drained:
                    last_event_at = time.monotonic()

                idle = time.monotonic() - last_event_at
                caption = self._process_caption(events, started, idle)

                # Edit only when the text actually changed and the rate limit allows
                # it. The spinner frame inside the caption changes over time, so this
                # produces smooth motion without hammering the Bot API.
                if caption != last_caption and time.monotonic() - last_edit >= PROCESS_EDIT_MIN_INTERVAL:
                    if status_message is None:
                        try:
                            status_message = await update.message.reply_text(caption)
                            last_caption = caption
                            last_edit = time.monotonic()
                        except Exception as e:
                            self.logger.debug("Progress card send failed: %s", e)
                    else:
                        await self._edit_process_card(status_message, caption)
                        last_caption = caption
                        last_edit = time.monotonic()

                if await self._sleep_or_stop(stop_event, PROCESS_UPDATE_INTERVAL):
                    break

            return status_message
        except Exception as e:
            self.logger.debug("Process feed failed: %s", e)
            return status_message

    def _telegram_context_message(self, message: str) -> str:
        return (
            f"{message}\n\n"
            "[Telegram gateway context: pesan ini datang dari chat Telegram yang sudah authenticated. "
            "Jangan minta bot token atau chat id untuk mengirim hasil ke chat ini. "
            "Gaya balasan harus Hermes-like tapi aman untuk Telegram: pakai bullet list, key: value, dan tabel markdown sederhana bila benar-benar perlu. "
            "Jangan pakai box-drawing terminal, ASCII art, atau tabel Unicode karena sering rusak di chat. "
            "Kalau kamu membuat audio, screenshot, gambar, atau dokumen lokal, sebutkan path file lokalnya; "
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
        return str(getattr(chat, "id", self.owner_chat_id or "default"))

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
        text = (update.message.text or "").strip()
        role = self._chat_role(update)
        chat = getattr(update, "effective_chat", None)
        chat_id = str(getattr(chat, "id", ""))

        # Universal admin trigger: prompt generic password request.
        if text.lower() == "admin":
            await self._prompt_admin_unlock(update)
            return

        # Unlock attempts are only accepted after the chat is already intended to be admin-capable.
        if text.lower().startswith("unlock "):
            password = text.split(" ", 1)[1].strip()
            if self._unlock_admin_chat(update, password):
                await update.message.reply_text("✅ Admin unlocked.")
            return

        # Silent ignore for everyone except owner and unlocked admins.
        if role != "owner" and not self._is_admin_unlocked(update):
            return

        self._refresh_admin_unlock(update)
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
    owner_chat_id = config.get("telegram_chat_id", "")
    admin_chat_ids = config.get("telegram_admin_chat_ids", [])
    admin_password = config.get("telegram_admin_password", "kepungan01")
    
    if not token:
        print("❌ No Telegram token configured!")
        print("Run: mimo setup")
        sys.exit(1)
    
    # Create and start bot
    bot = MiMoTelegramBot(token, owner_chat_id, admin_chat_ids, admin_password)
    
    print(f"✅ Telegram gateway aktif!")
    print("   Token: configured")
    print(f"   Owner chat ID: {owner_chat_id}")
    print(f"   Admin chats: {len(admin_chat_ids) if isinstance(admin_chat_ids, list) else 0}")
    
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
