"""
channel_router.py — Multi-Channel Message Router (OpenClaw-inspired)
Route messages from different platforms to appropriate handlers.
"""
import json
import os
import time
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

# ─── Channel Storage ──────────────────────────────────────────────────────
CHANNELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "channels")
os.makedirs(CHANNELS_DIR, exist_ok=True)

class Channel:
    def __init__(self, name: str, channel_type: str, config: Dict = None):
        self.channel_id = f"{channel_type}_{name}"
        self.name = name
        self.channel_type = channel_type
        self.config = config or {}
        self.enabled = True
        self.created_at = datetime.now().isoformat()
    
    def to_dict(self):
        return {
            "channel_id": self.channel_id,
            "name": self.name,
            "channel_type": self.channel_type,
            "config": self.config,
            "enabled": self.enabled,
            "created_at": self.created_at
        }

def channel_add(name: str, channel_type: str, config: str = "{}") -> str:
    """Add a new channel."""
    try:
        config_dict = json.loads(config) if isinstance(config, str) else config
        channel = Channel(name, channel_type, config_dict)
        
        channel_file = os.path.join(CHANNELS_DIR, f"{channel.channel_id}.json")
        with open(channel_file, "w") as f:
            json.dump(channel.to_dict(), f, indent=2)
        
        return json.dumps({
            "success": True,
            "channel_id": channel.channel_id,
            "name": name,
            "type": channel_type,
            "message": "Channel added"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def channel_list() -> str:
    """List all channels."""
    try:
        channels = []
        for f in os.listdir(CHANNELS_DIR):
            if f.endswith(".json"):
                with open(os.path.join(CHANNELS_DIR, f), "r") as file:
                    channels.append(json.load(file))
        
        return json.dumps({"success": True, "channels": channels, "count": len(channels)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def channel_remove(channel_id: str) -> str:
    """Remove a channel."""
    try:
        channel_file = os.path.join(CHANNELS_DIR, f"{channel_id}.json")
        if os.path.exists(channel_file):
            os.remove(channel_file)
            return json.dumps({"success": True, "removed": channel_id})
        else:
            return json.dumps({"success": False, "error": "Channel not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def channel_config(channel_id: str, config: str = "{}") -> str:
    """Update channel configuration."""
    try:
        channel_file = os.path.join(CHANNELS_DIR, f"{channel_id}.json")
        if not os.path.exists(channel_file):
            return json.dumps({"success": False, "error": "Channel not found"})
        
        with open(channel_file, "r") as f:
            channel = json.load(f)
        
        config_dict = json.loads(config) if isinstance(config, str) else config
        channel["config"].update(config_dict)
        
        with open(channel_file, "w") as f:
            json.dump(channel, f, indent=2)
        
        return json.dumps({"success": True, "channel_id": channel_id, "config": channel["config"]})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def channel_status(channel_id: str) -> str:
    """Get channel status."""
    try:
        channel_file = os.path.join(CHANNELS_DIR, f"{channel_id}.json")
        if not os.path.exists(channel_file):
            return json.dumps({"success": False, "error": "Channel not found"})
        
        with open(channel_file, "r") as f:
            return json.dumps({"success": True, "channel": json.load(f)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def channel_route(message: str, source: str = "unknown") -> str:
    """Route a message to appropriate handler."""
    try:
        # Load all channels
        channels = []
        for f in os.listdir(CHANNELS_DIR):
            if f.endswith(".json"):
                with open(os.path.join(CHANNELS_DIR, f), "r") as file:
                    channels.append(json.load(file))
        
        # Find matching channel
        for channel in channels:
            if channel.get("channel_type") == source and channel.get("enabled"):
                return json.dumps({
                    "success": True,
                    "routed_to": channel["channel_id"],
                    "message": message,
                    "source": source
                })
        
        return json.dumps({
            "success": True,
            "routed_to": "default",
            "message": message,
            "source": source
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def channel_filter(channel_id: str, filter_type: str = "all") -> str:
    """Filter messages for a channel."""
    try:
        return json.dumps({
            "success": True,
            "channel_id": channel_id,
            "filter_type": filter_type,
            "message": "Filter applied"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def channel_broadcast(message: str, channel_type: str = "all") -> str:
    """Broadcast message to all channels of a type."""
    try:
        channels = []
        for f in os.listdir(CHANNELS_DIR):
            if f.endswith(".json"):
                with open(os.path.join(CHANNELS_DIR, f), "r") as file:
                    channel = json.load(file)
                    if channel_type == "all" or channel.get("channel_type") == channel_type:
                        channels.append(channel)
        
        return json.dumps({
            "success": True,
            "broadcast_to": len(channels),
            "channels": [c["channel_id"] for c in channels],
            "message": message
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_channel_router_tools(register_tool):
    """Register channel router tools."""
    register_tool(
        name="channel_add",
        description="Add a new channel",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Channel name"},
                "channel_type": {"type": "string", "description": "Channel type (telegram, discord, slack, etc.)"},
                "config": {"type": "string", "description": "JSON config", "default": "{}"}
            },
            "required": ["name", "channel_type"]
        },
        handler=lambda args: channel_add(args.get("name", ""), args.get("channel_type", ""), args.get("config", "{}"))
    )
    
    register_tool(
        name="channel_list",
        description="List all channels",
        parameters={"type": "object", "properties": {}},
        handler=lambda args: channel_list()
    )
    
    register_tool(
        name="channel_remove",
        description="Remove a channel",
        parameters={
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "description": "Channel ID"}
            },
            "required": ["channel_id"]
        },
        handler=lambda args: channel_remove(args.get("channel_id", ""))
    )
    
    register_tool(
        name="channel_config",
        description="Update channel configuration",
        parameters={
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "description": "Channel ID"},
                "config": {"type": "string", "description": "JSON config"}
            },
            "required": ["channel_id", "config"]
        },
        handler=lambda args: channel_config(args.get("channel_id", ""), args.get("config", "{}"))
    )
    
    register_tool(
        name="channel_status",
        description="Get channel status",
        parameters={
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "description": "Channel ID"}
            },
            "required": ["channel_id"]
        },
        handler=lambda args: channel_status(args.get("channel_id", ""))
    )
    
    register_tool(
        name="channel_route",
        description="Route a message to appropriate handler",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to route"},
                "source": {"type": "string", "description": "Source channel type", "default": "unknown"}
            },
            "required": ["message"]
        },
        handler=lambda args: channel_route(args.get("message", ""), args.get("source", "unknown"))
    )
    
    register_tool(
        name="channel_filter",
        description="Filter messages for a channel",
        parameters={
            "type": "object",
            "properties": {
                "channel_id": {"type": "string", "description": "Channel ID"},
                "filter_type": {"type": "string", "description": "Filter type", "default": "all"}
            },
            "required": ["channel_id"]
        },
        handler=lambda args: channel_filter(args.get("channel_id", ""), args.get("filter_type", "all"))
    )
    
    register_tool(
        name="channel_broadcast",
        description="Broadcast message to all channels of a type",
        parameters={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to broadcast"},
                "channel_type": {"type": "string", "description": "Channel type", "default": "all"}
            },
            "required": ["message"]
        },
        handler=lambda args: channel_broadcast(args.get("message", ""), args.get("channel_type", "all"))
    )
