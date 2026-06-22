"""
session_manager.py — Session Management Tools
Manage sessions, history, context.
"""
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

# ─── Session Storage ──────────────────────────────────────────────────────
SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

def session_create(title: str = "", source: str = "cli") -> str:
    """Create a new session."""
    try:
        session_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:6]}"
        
        session = {
            "session_id": session_id,
            "title": title or f"Session {session_id}",
            "source": source,
            "started_at": time.time(),
            "last_active": time.time(),
            "message_count": 0,
            "context": {}
        }
        
        session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        with open(session_file, "w") as f:
            json.dump(session, f, indent=2)
        
        return json.dumps({"success": True, "session_id": session_id, "title": session["title"]})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def session_list(limit: int = 10) -> str:
    """List recent sessions."""
    try:
        sessions = []
        for f in sorted(os.listdir(SESSIONS_DIR), reverse=True)[:limit]:
            if f.endswith(".json"):
                with open(os.path.join(SESSIONS_DIR, f), "r") as file:
                    sessions.append(json.load(file))
        
        return json.dumps({"success": True, "sessions": sessions, "count": len(sessions)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def session_export(session_id: str, output_path: str = "") -> str:
    """Export session to file."""
    try:
        session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if not os.path.exists(session_file):
            return json.dumps({"success": False, "error": "Session not found"})
        
        if not output_path:
            output_path = os.path.join(SESSIONS_DIR, f"{session_id}_export.json")
        
        with open(session_file, "r") as f:
            session = json.load(f)
        
        with open(output_path, "w") as f:
            json.dump(session, f, indent=2)
        
        return json.dumps({"success": True, "exported": output_path})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def session_delete(session_id: str) -> str:
    """Delete a session."""
    try:
        session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if os.path.exists(session_file):
            os.remove(session_file)
            return json.dumps({"success": True, "deleted": session_id})
        else:
            return json.dumps({"success": False, "error": "Session not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def session_rename(session_id: str, new_title: str) -> str:
    """Rename a session."""
    try:
        session_file = os.path.join(SESSIONS_DIR, f"{session_id}.json")
        if not os.path.exists(session_file):
            return json.dumps({"success": False, "error": "Session not found"})
        
        with open(session_file, "r") as f:
            session = json.load(f)
        
        session["title"] = new_title
        
        with open(session_file, "w") as f:
            json.dump(session, f, indent=2)
        
        return json.dumps({"success": True, "session_id": session_id, "new_title": new_title})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_session_manager_tools(register_tool):
    """Register session manager tools."""
    register_tool(
        name="session_create",
        description="Create a new session",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Session title", "default": ""},
                "source": {"type": "string", "description": "Session source", "default": "cli"}
            }
        },
        handler=lambda args: session_create(args.get("title", ""), args.get("source", "cli"))
    )
    
    register_tool(
        name="session_list",
        description="List recent sessions",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results", "default": 10}
            }
        },
        handler=lambda args: session_list(args.get("limit", 10))
    )
    
    register_tool(
        name="session_export",
        description="Export session to file",
        parameters={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "output_path": {"type": "string", "description": "Output file path", "default": ""}
            },
            "required": ["session_id"]
        },
        handler=lambda args: session_export(args.get("session_id", ""), args.get("output_path", ""))
    )
    
    register_tool(
        name="session_delete",
        description="Delete a session",
        parameters={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID to delete"}
            },
            "required": ["session_id"]
        },
        handler=lambda args: session_delete(args.get("session_id", ""))
    )
    
    register_tool(
        name="session_rename",
        description="Rename a session",
        parameters={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "new_title": {"type": "string", "description": "New title"}
            },
            "required": ["session_id", "new_title"]
        },
        handler=lambda args: session_rename(args.get("session_id", ""), args.get("new_title", ""))
    )
