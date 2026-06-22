"""
event_system.py — Event-Driven Automation (OpenClaw-inspired)
Create, listen, and emit events for automation.
"""
import json
import os
import time
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

# ─── Event Storage ──────────────────────────────────────────────────────
EVENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "events")
os.makedirs(EVENTS_DIR, exist_ok=True)
LISTENERS_DIR = os.path.join(EVENTS_DIR, "listeners")
os.makedirs(LISTENERS_DIR, exist_ok=True)

class Event:
    def __init__(self, name: str, event_type: str = "custom", data: Dict = None):
        self.event_id = str(uuid.uuid4())[:8]
        self.name = name
        self.event_type = event_type
        self.data = data or {}
        self.timestamp = datetime.now().isoformat()
    
    def to_dict(self):
        return {
            "event_id": self.event_id,
            "name": self.name,
            "event_type": self.event_type,
            "data": self.data,
            "timestamp": self.timestamp
        }

def event_create(name: str, event_type: str = "custom", data: str = "{}") -> str:
    """Create a new event."""
    try:
        data_dict = json.loads(data) if isinstance(data, str) else data
        event = Event(name, event_type, data_dict)
        
        event_file = os.path.join(EVENTS_DIR, f"{event.event_id}.json")
        with open(event_file, "w") as f:
            json.dump(event.to_dict(), f, indent=2)
        
        return json.dumps({
            "success": True,
            "event_id": event.event_id,
            "name": name,
            "type": event_type,
            "message": "Event created"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def event_listen(event_name: str, callback: str = "") -> str:
    """Listen for an event."""
    try:
        if not event_name:
            return json.dumps({"success": False, "error": "event_name required"})
        listener_id = str(uuid.uuid4())[:8]
        listener = {
            "listener_id": listener_id,
            "event_name": event_name,
            "callback": callback,
            "created_at": datetime.now().isoformat(),
            "active": True,
        }
        listener_file = os.path.join(LISTENERS_DIR, f"{listener_id}.json")
        with open(listener_file, "w") as f:
            json.dump(listener, f, indent=2)
        return json.dumps({
            "success": True,
            "listener_id": listener_id,
            "event_name": event_name,
            "callback": callback,
            "message": f"Listener registered for event: {event_name}"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def event_emit(event_name: str, data: str = "{}") -> str:
    """Emit an event."""
    try:
        data_dict = json.loads(data) if isinstance(data, str) else data
        
        # Create event
        event = Event(event_name, "emitted", data_dict)
        
        # Save event
        event_file = os.path.join(EVENTS_DIR, f"{event.event_id}.json")
        with open(event_file, "w") as f:
            json.dump(event.to_dict(), f, indent=2)

        matched_listeners = []
        for filename in os.listdir(LISTENERS_DIR):
            if not filename.endswith(".json"):
                continue
            listener_path = os.path.join(LISTENERS_DIR, filename)
            with open(listener_path, "r") as f:
                listener = json.load(f)
            if listener.get("active") and listener.get("event_name") in {event_name, "*"}:
                listener["last_event_id"] = event.event_id
                listener["last_seen_at"] = datetime.now().isoformat()
                with open(listener_path, "w") as f:
                    json.dump(listener, f, indent=2)
                matched_listeners.append({
                    "listener_id": listener.get("listener_id"),
                    "callback": listener.get("callback", ""),
                })
        
        return json.dumps({
            "success": True,
            "event_id": event.event_id,
            "name": event_name,
            "listeners_notified": len(matched_listeners),
            "listeners": matched_listeners,
            "message": "Event emitted"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def event_list(limit: int = 10) -> str:
    """List recent events."""
    try:
        events = []
        for f in sorted(os.listdir(EVENTS_DIR), reverse=True)[:limit]:
            if f.endswith(".json"):
                with open(os.path.join(EVENTS_DIR, f), "r") as file:
                    events.append(json.load(file))
        
        return json.dumps({"success": True, "events": events, "count": len(events)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def event_delete(event_id: str) -> str:
    """Delete an event."""
    try:
        event_file = os.path.join(EVENTS_DIR, f"{event_id}.json")
        if os.path.exists(event_file):
            os.remove(event_file)
            return json.dumps({"success": True, "deleted": event_id})
        else:
            return json.dumps({"success": False, "error": "Event not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def event_chain(events: str) -> str:
    """Chain multiple events."""
    try:
        events_list = json.loads(events) if isinstance(events, str) else events
        
        chain_id = str(uuid.uuid4())[:8]
        chain = {
            "chain_id": chain_id,
            "events": events_list,
            "created_at": datetime.now().isoformat()
        }
        
        chain_file = os.path.join(EVENTS_DIR, f"chain_{chain_id}.json")
        with open(chain_file, "w") as f:
            json.dump(chain, f, indent=2)
        
        return json.dumps({
            "success": True,
            "chain_id": chain_id,
            "events_count": len(events_list),
            "message": "Event chain created"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def event_log(event_id: str) -> str:
    """Get event log."""
    try:
        event_file = os.path.join(EVENTS_DIR, f"{event_id}.json")
        if os.path.exists(event_file):
            with open(event_file, "r") as f:
                return json.dumps({"success": True, "event": json.load(f)})
        else:
            return json.dumps({"success": False, "error": "Event not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def event_replay(chain_id: str) -> str:
    """Replay an event chain."""
    try:
        chain_file = os.path.join(EVENTS_DIR, f"chain_{chain_id}.json")
        if os.path.exists(chain_file):
            with open(chain_file, "r") as f:
                chain = json.load(f)
            
            replayed = []
            for item in chain.get("events", []):
                if isinstance(item, str):
                    name = item
                    event_type = "replayed"
                    data = {}
                else:
                    name = item.get("name") or item.get("event_name") or "replayed_event"
                    event_type = item.get("event_type", "replayed")
                    data = item.get("data", {})
                event = Event(name, event_type, data)
                event_file = os.path.join(EVENTS_DIR, f"{event.event_id}.json")
                with open(event_file, "w") as out:
                    json.dump(event.to_dict(), out, indent=2)
                replayed.append(event.event_id)

            return json.dumps({
                "success": True,
                "chain_id": chain_id,
                "replayed_event_ids": replayed,
                "count": len(replayed),
                "message": "Chain replayed"
            })
        else:
            return json.dumps({"success": False, "error": "Chain not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_event_system_tools(register_tool):
    """Register event system tools."""
    register_tool(
        name="event_create",
        description="Create a new event",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Event name"},
                "event_type": {"type": "string", "description": "Event type", "default": "custom"},
                "data": {"type": "string", "description": "JSON data", "default": "{}"}
            },
            "required": ["name"]
        },
        handler=lambda args: event_create(args.get("name", ""), args.get("event_type", "custom"), args.get("data", "{}"))
    )
    
    register_tool(
        name="event_listen",
        description="Listen for an event",
        parameters={
            "type": "object",
            "properties": {
                "event_name": {"type": "string", "description": "Event name to listen for"},
                "callback": {"type": "string", "description": "Callback function", "default": ""}
            },
            "required": ["event_name"]
        },
        handler=lambda args: event_listen(args.get("event_name", ""), args.get("callback", ""))
    )
    
    register_tool(
        name="event_emit",
        description="Emit an event",
        parameters={
            "type": "object",
            "properties": {
                "event_name": {"type": "string", "description": "Event name"},
                "data": {"type": "string", "description": "JSON data", "default": "{}"}
            },
            "required": ["event_name"]
        },
        handler=lambda args: event_emit(args.get("event_name", ""), args.get("data", "{}"))
    )
    
    register_tool(
        name="event_list",
        description="List recent events",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results", "default": 10}
            }
        },
        handler=lambda args: event_list(args.get("limit", 10))
    )
    
    register_tool(
        name="event_delete",
        description="Delete an event",
        parameters={
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "Event ID"}
            },
            "required": ["event_id"]
        },
        handler=lambda args: event_delete(args.get("event_id", ""))
    )
    
    register_tool(
        name="event_chain",
        description="Chain multiple events",
        parameters={
            "type": "object",
            "properties": {
                "events": {"type": "string", "description": "JSON array of event names"}
            },
            "required": ["events"]
        },
        handler=lambda args: event_chain(args.get("events", "[]"))
    )
    
    register_tool(
        name="event_log",
        description="Get event log",
        parameters={
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "Event ID"}
            },
            "required": ["event_id"]
        },
        handler=lambda args: event_log(args.get("event_id", ""))
    )
    
    register_tool(
        name="event_replay",
        description="Replay an event chain",
        parameters={
            "type": "object",
            "properties": {
                "chain_id": {"type": "string", "description": "Chain ID"}
            },
            "required": ["chain_id"]
        },
        handler=lambda args: event_replay(args.get("chain_id", ""))
    )
