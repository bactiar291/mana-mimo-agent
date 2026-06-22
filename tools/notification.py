"""
notification.py — Notification Tools
Send notifications via Telegram, Discord, etc.
"""
import json
import os
import subprocess
from typing import Any, Dict, List, Optional
from datetime import datetime

def notify_telegram(message: str, chat_id: str = "", token: str = "") -> str:
    """Send notification via Telegram."""
    try:
        if not token:
            # Try to load from config
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "telegram.json")
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config = json.load(f)
                    token = config.get("telegram_token", "")
                    if not chat_id:
                        chat_id = config.get("telegram_chat_id", "")
        
        if not token or not chat_id:
            return json.dumps({"success": False, "error": "Telegram token or chat_id not configured"})
        
        # Send via curl
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = {"chat_id": chat_id, "text": message}
        result = subprocess.run(
            ["curl", "-s", "-X", "POST", url, "-H", "Content-Type: application/json", "-d", json.dumps(data)],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0:
            response = json.loads(result.stdout)
            if response.get("ok"):
                return json.dumps({"success": True, "message_id": response["result"]["message_id"]})
            else:
                return json.dumps({"success": False, "error": response.get("description", "Unknown error")})
        else:
            return json.dumps({"success": False, "error": result.stderr})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def notify_discord(message: str, webhook_url: str = "") -> str:
    """Send notification via Discord webhook."""
    try:
        if not webhook_url:
            return json.dumps({"success": False, "error": "Discord webhook URL not provided"})
        
        data = {"content": message}
        result = subprocess.run(
            [
                "curl", "-sS", "-X", "POST", webhook_url,
                "-H", "Content-Type: application/json",
                "-d", json.dumps(data),
                "-w", "\n%{http_code}",
            ],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0:
            body, _, status = result.stdout.rpartition("\n")
            if status.isdigit() and 200 <= int(status) < 300:
                return json.dumps({"success": True, "message": "Notification sent", "status_code": int(status)})
            return json.dumps({"success": False, "error": body.strip() or "Discord webhook failed", "status_code": int(status) if status.isdigit() else None})
        else:
            return json.dumps({"success": False, "error": result.stderr})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def notify_slack(message: str, webhook_url: str = "") -> str:
    """Send notification via Slack webhook."""
    try:
        if not webhook_url:
            return json.dumps({"success": False, "error": "Slack webhook URL not provided"})
        
        data = {"text": message}
        result = subprocess.run(
            [
                "curl", "-sS", "-X", "POST", webhook_url,
                "-H", "Content-Type: application/json",
                "-d", json.dumps(data),
                "-w", "\n%{http_code}",
            ],
            capture_output=True, text=True, timeout=10
        )
        
        if result.returncode == 0:
            body, _, status = result.stdout.rpartition("\n")
            if status.isdigit() and 200 <= int(status) < 300:
                return json.dumps({"success": True, "message": "Notification sent", "status_code": int(status)})
            return json.dumps({"success": False, "error": body.strip() or "Slack webhook failed", "status_code": int(status) if status.isdigit() else None})
        else:
            return json.dumps({"success": False, "error": result.stderr})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def notify_email(to: str, subject: str, body: str) -> str:
    """Send notification via email."""
    try:
        return json.dumps({
            "success": False,
            "error": "Email notification requires SMTP integration and is not configured",
            "reason": "not_implemented",
            "to": to,
            "subject": subject
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def notify_sms(phone: str, message: str) -> str:
    """Send notification via SMS."""
    try:
        return json.dumps({
            "success": False,
            "error": "SMS notification requires an SMS provider integration and is not configured",
            "reason": "not_implemented",
            "phone": phone
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_notification_tools(register_tool):
    """Register notification tools."""
    register_tool(
        name="notify_telegram",
        description="Send notification via Telegram",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to send"},
                "chat_id": {"type": "string", "description": "Chat ID", "default": ""},
                "token": {"type": "string", "description": "Bot token", "default": ""}
            },
            "required": ["message"]
        },
        handler=lambda args: notify_telegram(args.get("message", ""), args.get("chat_id", ""), args.get("token", ""))
    )
    
    register_tool(
        name="notify_discord",
        description="Send notification via Discord webhook",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to send"},
                "webhook_url": {"type": "string", "description": "Discord webhook URL"}
            },
            "required": ["message", "webhook_url"]
        },
        handler=lambda args: notify_discord(args.get("message", ""), args.get("webhook_url", ""))
    )
    
    register_tool(
        name="notify_slack",
        description="Send notification via Slack webhook",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to send"},
                "webhook_url": {"type": "string", "description": "Slack webhook URL"}
            },
            "required": ["message", "webhook_url"]
        },
        handler=lambda args: notify_slack(args.get("message", ""), args.get("webhook_url", ""))
    )
    
    register_tool(
        name="notify_email",
        description="Send notification via email",
        parameters={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body"}
            },
            "required": ["to", "subject", "body"]
        },
        handler=lambda args: notify_email(args.get("to", ""), args.get("subject", ""), args.get("body", ""))
    )
    
    register_tool(
        name="notify_sms",
        description="Send notification via SMS",
        parameters={
            "type": "object",
            "properties": {
                "phone": {"type": "string", "description": "Phone number"},
                "message": {"type": "string", "description": "SMS message"}
            },
            "required": ["phone", "message"]
        },
        handler=lambda args: notify_sms(args.get("phone", ""), args.get("message", ""))
    )
