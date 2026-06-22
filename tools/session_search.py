"""
session_search.py — Session Search with SQLite FTS5
Search past conversations and manage sessions.
"""
import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

# ─── Session Storage ──────────────────────────────────────────────────────
SESSIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

DB_PATH = os.path.join(SESSIONS_DIR, "sessions.db")

def _init_db():
    """Initialize SQLite database with FTS5."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            title TEXT,
            source TEXT,
            started_at REAL,
            last_active REAL,
            message_count INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
            session_id, role, content, timestamp
        )
    """)
    conn.commit()
    conn.close()

_init_db()

def session_search(query: str = "", session_id: str = "", limit: int = 5) -> str:
    """Search sessions or get session details."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        if session_id:
            # Get specific session
            c.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,))
            session = c.fetchone()
            if session:
                c.execute("SELECT role, content, timestamp FROM messages_fts WHERE session_id = ? ORDER BY timestamp", (session_id,))
                messages = [{"role": row[0], "content": row[1], "timestamp": row[2]} for row in c.fetchall()]
                conn.close()
                return json.dumps({
                    "success": True,
                    "session": {
                        "session_id": session[0],
                        "title": session[1],
                        "source": session[2],
                        "started_at": session[3],
                        "last_active": session[4],
                        "message_count": session[5]
                    },
                    "messages": messages
                })
            else:
                conn.close()
                return json.dumps({"success": False, "error": "Session not found"})
        
        elif query:
            # Search in messages
            c.execute("""
                SELECT DISTINCT s.session_id, s.title, s.source, s.started_at, s.last_active, s.message_count
                FROM sessions s
                JOIN messages_fts m ON s.session_id = m.session_id
                WHERE m.content MATCH ?
                ORDER BY s.last_active DESC
                LIMIT ?
            """, (query, limit))
            sessions = []
            for row in c.fetchall():
                sessions.append({
                    "session_id": row[0],
                    "title": row[1],
                    "source": row[2],
                    "started_at": row[3],
                    "last_active": row[4],
                    "message_count": row[5]
                })
            conn.close()
            return json.dumps({"success": True, "sessions": sessions, "count": len(sessions)})
        
        else:
            # List recent sessions
            c.execute("SELECT * FROM sessions ORDER BY last_active DESC LIMIT ?", (limit,))
            sessions = []
            for row in c.fetchall():
                sessions.append({
                    "session_id": row[0],
                    "title": row[1],
                    "source": row[2],
                    "started_at": row[3],
                    "last_active": row[4],
                    "message_count": row[5]
                })
            conn.close()
            return json.dumps({"success": True, "sessions": sessions, "count": len(sessions)})
    
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def session_log(session_id: str, role: str, content: str) -> str:
    """Log a message to session."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Update or create session
        c.execute("""
            INSERT OR REPLACE INTO sessions (session_id, title, source, started_at, last_active, message_count)
            VALUES (?, ?, ?, ?, ?, COALESCE((SELECT message_count FROM sessions WHERE session_id = ?), 0) + 1)
        """, (session_id, f"Session {session_id}", "cli", time.time(), time.time(), session_id))
        
        # Insert message
        c.execute("INSERT INTO messages_fts (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                  (session_id, role, content, time.time()))
        
        conn.commit()
        conn.close()
        return json.dumps({"success": True, "session_id": session_id})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def session_delete(session_id: str) -> str:
    """Delete a session."""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        c.execute("DELETE FROM messages_fts WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
        return json.dumps({"success": True, "deleted": session_id})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_session_search_tools(register_tool):
    """Register session search tools."""
    register_tool(
        name="session_search",
        description="Search past sessions or get session details",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query", "default": ""},
                "session_id": {"type": "string", "description": "Session ID to get details", "default": ""},
                "limit": {"type": "integer", "description": "Max results", "default": 5}
            }
        },
        handler=lambda args: session_search(args.get("query", ""), args.get("session_id", ""), args.get("limit", 5))
    )
    
    register_tool(
        name="session_log",
        description="Log a message to session history",
        parameters={
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID"},
                "role": {"type": "string", "description": "Message role (user/assistant)"},
                "content": {"type": "string", "description": "Message content"}
            },
            "required": ["session_id", "role", "content"]
        },
        handler=lambda args: session_log(args.get("session_id", ""), args.get("role", ""), args.get("content", ""))
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
