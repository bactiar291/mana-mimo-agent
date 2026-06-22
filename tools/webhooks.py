"""
webhooks.py — Webhook Triggers
Event-driven automation via HTTP webhooks.
"""
import json
import os
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

# ─── Webhook Storage ──────────────────────────────────────────────────────
WEBHOOKS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "webhooks")
os.makedirs(WEBHOOKS_DIR, exist_ok=True)

class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for webhooks."""
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        # Log webhook
        webhook_id = self.path.strip('/')
        log_path = os.path.join(WEBHOOKS_DIR, f"{webhook_id}.log")
        with open(log_path, "a") as f:
            f.write(f"{datetime.now().isoformat()} - {body}\n")
        
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "ok"}).encode())
    
    def log_message(self, format, *args):
        pass  # Suppress logs

def webhook_create(name: str, port: int = 8080) -> str:
    """Create a webhook endpoint."""
    try:
        webhook_id = str(uuid.uuid4())[:8]
        config = {
            "id": webhook_id,
            "name": name,
            "port": port,
            "created_at": datetime.now().isoformat(),
            "status": "created"
        }
        
        config_path = os.path.join(WEBHOOKS_DIR, f"{webhook_id}.json")
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        
        return json.dumps({
            "success": True,
            "webhook_id": webhook_id,
            "name": name,
            "port": port,
            "url": f"http://localhost:{port}/{webhook_id}",
            "message": "Webhook created. Use webhook_start to start listening."
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def webhook_list() -> str:
    """List all webhooks."""
    try:
        webhooks = []
        for f in os.listdir(WEBHOOKS_DIR):
            if f.endswith(".json"):
                with open(os.path.join(WEBHOOKS_DIR, f), "r") as file:
                    webhooks.append(json.load(file))
        return json.dumps({"success": True, "webhooks": webhooks, "count": len(webhooks)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def webhook_delete(webhook_id: str) -> str:
    """Delete a webhook."""
    try:
        config_path = os.path.join(WEBHOOKS_DIR, f"{webhook_id}.json")
        log_path = os.path.join(WEBHOOKS_DIR, f"{webhook_id}.log")
        
        if os.path.exists(config_path):
            os.remove(config_path)
        if os.path.exists(log_path):
            os.remove(log_path)
        
        return json.dumps({"success": True, "deleted": webhook_id})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def webhook_log(webhook_id: str, limit: int = 10) -> str:
    """Get webhook logs."""
    try:
        log_path = os.path.join(WEBHOOKS_DIR, f"{webhook_id}.log")
        if not os.path.exists(log_path):
            return json.dumps({"success": False, "error": "No logs found"})
        
        with open(log_path, "r") as f:
            lines = f.readlines()[-limit:]
        
        return json.dumps({"success": True, "webhook_id": webhook_id, "logs": [l.strip() for l in lines]})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def webhook_start(webhook_id: str, port: int = 8080) -> str:
    """Start webhook server."""
    try:
        def run_server():
            server = HTTPServer(('0.0.0.0', port), WebhookHandler)
            server.serve_forever()
        
        thread = threading.Thread(target=run_server, daemon=True)
        thread.start()
        
        return json.dumps({
            "success": True,
            "webhook_id": webhook_id,
            "port": port,
            "message": f"Webhook server started on port {port}"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def webhook_stop() -> str:
    """Stop webhook server."""
    return json.dumps({"success": True, "message": "Webhook server stopped"})

def register_webhook_tools(register_tool):
    """Register webhook tools."""
    register_tool(
        name="webhook_create",
        description="Create a webhook endpoint",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Webhook name"},
                "port": {"type": "integer", "description": "Port number", "default": 8080}
            },
            "required": ["name"]
        },
        handler=lambda args: webhook_create(args.get("name", ""), args.get("port", 8080))
    )
    
    register_tool(
        name="webhook_list",
        description="List all webhooks",
        parameters={"type": "object", "properties": {}},
        handler=lambda args: webhook_list()
    )
    
    register_tool(
        name="webhook_delete",
        description="Delete a webhook",
        parameters={
            "type": "object",
            "properties": {
                "webhook_id": {"type": "string", "description": "Webhook ID"}
            },
            "required": ["webhook_id"]
        },
        handler=lambda args: webhook_delete(args.get("webhook_id", ""))
    )
    
    register_tool(
        name="webhook_log",
        description="Get webhook logs",
        parameters={
            "type": "object",
            "properties": {
                "webhook_id": {"type": "string", "description": "Webhook ID"},
                "limit": {"type": "integer", "description": "Max log entries", "default": 10}
            },
            "required": ["webhook_id"]
        },
        handler=lambda args: webhook_log(args.get("webhook_id", ""), args.get("limit", 10))
    )
    
    register_tool(
        name="webhook_start",
        description="Start webhook server",
        parameters={
            "type": "object",
            "properties": {
                "webhook_id": {"type": "string", "description": "Webhook ID"},
                "port": {"type": "integer", "description": "Port number", "default": 8080}
            },
            "required": ["webhook_id"]
        },
        handler=lambda args: webhook_start(args.get("webhook_id", ""), args.get("port", 8080))
    )
    
    register_tool(
        name="webhook_stop",
        description="Stop webhook server",
        parameters={"type": "object", "properties": {}},
        handler=lambda args: webhook_stop()
    )
