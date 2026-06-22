"""
security.py — Security Approval System
Ask for approval before executing dangerous operations.
Supports Telegram (inline keyboard) and CLI (y/n prompt).
"""
import json
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

# ─── Dangerous Patterns ──────────────────────────────────────────────────

DANGEROUS_COMMANDS = [
    r';\s*rm\s',           # ; rm
    r'&&\s*rm\s',          # && rm
    r'\|\s*rm\s',          # | rm
    r'rm\s+-rf\s+/',       # rm -rf /
    r'rm\s+-rf\s+\*',      # rm -rf *
    r'mkfs\.',             # mkfs (format disk)
    r'dd\s+if=',           # dd (disk write)
    r'chmod\s+777',        # chmod 777
    r'curl.*\|\s*(ba)?sh', # curl | sh
    r'wget.*\|\s*(ba)?sh', # wget | sh
    r'eval\s*\(',          # eval()
    r'exec\s*\(',          # exec()
    r'__import__',         # __import__
    r'os\.system\(',       # os.system()
    r'subprocess\.call',   # subprocess.call
    r'>\s*/dev/sd',        # write to disk
    r'mount\s',            # mount
    r'umount\s',           # umount
    r'fdisk\s',            # fdisk
    r'iptables\s',         # iptables
    r'systemctl\s+(stop|disable|mask)',  # stop services
    r'kill\s+-9\s+1\s',   # kill init
    r':()\s*\{\s*:\|:\s*&\s*\};:',  # fork bomb
]

SENSITIVE_PATHS = [
    r'/etc/shadow',
    r'/etc/passwd',
    r'/etc/sudoers',
    r'/root/\.ssh/',
    r'/root/\.gnupg/',
    r'\.env$',
    r'session_cookie',
    r'api_key',
    r'secret',
    r'password',
    r'token',
    r'credentials',
]

# ─── Security Check ──────────────────────────────────────────────────────

def check_dangerous_command(command: str) -> Tuple[bool, str]:
    """Check if a command is dangerous. Returns (is_dangerous, reason)."""
    for pattern in DANGEROUS_COMMANDS:
        if re.search(pattern, command, re.IGNORECASE):
            return True, f"Dangerous pattern: {pattern}"
    return False, ""

def check_sensitive_path(path: str) -> Tuple[bool, str]:
    """Check if a path is sensitive. Returns (is_sensitive, reason)."""
    for pattern in SENSITIVE_PATHS:
        if re.search(pattern, path, re.IGNORECASE):
            return True, f"Sensitive path: {pattern}"
    return False, ""

def check_command_safety(command: str) -> Dict[str, Any]:
    """Full safety check for a command."""
    is_dangerous, reason = check_dangerous_command(command)
    
    if is_dangerous:
        return {
            "safe": False,
            "reason": reason,
            "command": command,
            "needs_approval": True
        }
    
    # Check for pipe chains
    if '|' in command:
        parts = command.split('|')
        for part in parts:
            is_dangerous, reason = check_dangerous_command(part.strip())
            if is_dangerous:
                return {
                    "safe": False,
                    "reason": f"Dangerous in pipe: {reason}",
                    "command": command,
                    "needs_approval": True
                }
    
    # Check for && chains
    if '&&' in command:
        parts = command.split('&&')
        for part in parts:
            is_dangerous, reason = check_dangerous_command(part.strip())
            if is_dangerous:
                return {
                    "safe": False,
                    "reason": f"Dangerous in chain: {reason}",
                    "command": command,
                    "needs_approval": True
                }
    
    return {
        "safe": True,
        "reason": "",
        "command": command,
        "needs_approval": False
    }

def check_path_safety(path: str) -> Dict[str, Any]:
    """Full safety check for a file path."""
    is_sensitive, reason = check_sensitive_path(path)
    
    if is_sensitive:
        return {
            "safe": False,
            "reason": reason,
            "path": path,
            "needs_approval": True
        }
    
    return {
        "safe": True,
        "reason": "",
        "path": path,
        "needs_approval": False
    }

# ─── Approval Interface ──────────────────────────────────────────────────

class SecurityApproval:
    """Handles security approval requests."""
    
    def __init__(self, mode: str = "cli"):
        """
        mode: 'cli' for terminal y/n, 'telegram' for inline keyboard
        """
        self.mode = mode
        self.telegram_bot = None
        self.telegram_chat_id = None
    
    def set_telegram(self, bot, chat_id: str):
        """Set Telegram bot for approval requests."""
        self.telegram_bot = bot
        self.telegram_chat_id = chat_id
    
    def request_approval(self, operation: str, details: str, risk_level: str = "medium") -> bool:
        """
        Request approval for a dangerous operation.
        Returns True if approved, False if denied.
        """
        if self.mode == "cli":
            return self._cli_approval(operation, details, risk_level)
        elif self.mode == "telegram":
            return self._telegram_approval(operation, details, risk_level)
        else:
            # Default: deny
            return False
    
    def _cli_approval(self, operation: str, details: str, risk_level: str) -> bool:
        """CLI approval with y/n prompt."""
        print(f"\n⚠️  SECURITY APPROVAL REQUIRED")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"Operation: {operation}")
        print(f"Details:   {details}")
        print(f"Risk:      {risk_level.upper()}")
        print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        while True:
            try:
                response = input("Approve? (y/n): ").strip().lower()
                if response in ['y', 'yes']:
                    print("✅ Approved")
                    return True
                elif response in ['n', 'no']:
                    print("❌ Denied")
                    return False
                else:
                    print("Please enter 'y' or 'n'")
            except (EOFError, KeyboardInterrupt):
                print("\n❌ Denied (interrupted)")
                return False
    
    def _telegram_approval(self, operation: str, details: str, risk_level: str) -> bool:
        """Telegram approval with inline keyboard."""
        if not self.telegram_bot or not self.telegram_chat_id:
            print("⚠️ Telegram not configured, defaulting to deny")
            return False
        
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            import asyncio
            
            # Create message
            message = (
                f"⚠️ **SECURITY APPROVAL REQUIRED**\n\n"
                f"**Operation:** {operation}\n"
                f"**Details:** {details}\n"
                f"**Risk:** {risk_level.upper()}\n\n"
                f"Do you want to approve this operation?"
            )
            
            # Create keyboard
            keyboard = [
                [
                    InlineKeyboardButton("✅ Approve", callback_data="approve"),
                    InlineKeyboardButton("❌ Deny", callback_data="deny"),
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send message
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            msg = loop.run_until_complete(
                self.telegram_bot.send_message(
                    chat_id=self.telegram_chat_id,
                    text=message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            )
            
            print(f"📱 Approval request sent to Telegram (msg_id: {msg.message_id})")
            print("⏳ Telegram callback approval is not implemented; denying by default")
            return False
            
        except Exception as e:
            print(f"❌ Telegram approval failed: {e}")
            return False

# ─── Global Instance ──────────────────────────────────────────────────────

_approval = SecurityApproval(mode="cli")

def get_approval_system() -> SecurityApproval:
    """Get the global approval system."""
    return _approval

def set_approval_mode(mode: str) -> Dict[str, Any]:
    """Set approval mode: 'cli' or 'telegram'."""
    global _approval
    if mode not in {"cli", "telegram"}:
        return {"success": False, "error": "Mode must be 'cli' or 'telegram'"}
    _approval = SecurityApproval(mode=mode)
    return {"success": True, "mode": mode}

def request_command_approval(command: str) -> bool:
    """Request approval for a terminal command."""
    check = check_command_safety(command)
    
    if check["safe"]:
        return True
    
    return _approval.request_approval(
        operation="Terminal Command",
        details=command,
        risk_level="high" if "rm -rf" in command else "medium"
    )

def request_path_approval(path: str) -> bool:
    """Request approval for file access."""
    check = check_path_safety(path)
    
    if check["safe"]:
        return True
    
    return _approval.request_approval(
        operation="File Access",
        details=path,
        risk_level="high" if "shadow" in path or "ssh" in path else "medium"
    )

# ─── Register Tools ──────────────────────────────────────────────────────

def register_security_tools(register_tool):
    """Register security tools."""
    register_tool(
        name="security_check_command",
        description="Check if a command is safe to execute",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command to check"}
            },
            "required": ["command"]
        },
        handler=lambda args: json.dumps(check_command_safety(args.get("command", "")))
    )
    
    register_tool(
        name="security_check_path",
        description="Check if a file path is safe to access",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to check"}
            },
            "required": ["path"]
        },
        handler=lambda args: json.dumps(check_path_safety(args.get("path", "")))
    )
    
    register_tool(
        name="security_set_mode",
        description="Set security approval mode",
        parameters={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "description": "Mode: cli or telegram"}
            },
            "required": ["mode"]
        },
        handler=lambda args: json.dumps(set_approval_mode(args.get("mode", "cli")))
    )
