"""
enhanced_memory.py — Enhanced Memory System
User profile, environment, facts, preferences memory.
"""
import json
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

# ─── Memory Storage ──────────────────────────────────────────────────────
MEMORY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "memory")
os.makedirs(MEMORY_DIR, exist_ok=True)

def memory_enhanced(action: str = "list", category: str = "all", key: str = "", value: str = "") -> str:
    """Enhanced memory with categories."""
    try:
        memory_file = os.path.join(MEMORY_DIR, "enhanced_memory.json")
        
        if os.path.exists(memory_file):
            with open(memory_file, "r") as f:
                memory = json.load(f)
        else:
            memory = {"user": {}, "environment": {}, "facts": [], "preferences": {}, "updated": ""}
        
        if action == "add":
            if category == "user":
                memory["user"][key] = value
            elif category == "environment":
                memory["environment"][key] = value
            elif category == "facts":
                if value not in memory["facts"]:
                    memory["facts"].append(value)
            elif category == "preferences":
                memory["preferences"][key] = value
            
            memory["updated"] = datetime.now().isoformat()
            with open(memory_file, "w") as f:
                json.dump(memory, f, indent=2)
            
            return json.dumps({"success": True, "action": "added", "category": category, "key": key})
        
        elif action == "get":
            if category == "user":
                return json.dumps({"success": True, "data": memory.get("user", {})})
            elif category == "environment":
                return json.dumps({"success": True, "data": memory.get("environment", {})})
            elif category == "facts":
                return json.dumps({"success": True, "data": memory.get("facts", [])})
            elif category == "preferences":
                return json.dumps({"success": True, "data": memory.get("preferences", {})})
            else:
                return json.dumps({"success": True, "data": memory})
        
        elif action == "list":
            return json.dumps({
                "success": True,
                "user_keys": list(memory.get("user", {}).keys()),
                "env_keys": list(memory.get("environment", {}).keys()),
                "facts_count": len(memory.get("facts", [])),
                "pref_keys": list(memory.get("preferences", {}).keys()),
                "updated": memory.get("updated", "")
            })
        
        elif action == "delete":
            if category == "user" and key in memory.get("user", {}):
                del memory["user"][key]
            elif category == "environment" and key in memory.get("environment", {}):
                del memory["environment"][key]
            elif category == "facts":
                if value in memory.get("facts", []):
                    memory["facts"].remove(value)
            elif category == "preferences" and key in memory.get("preferences", {}):
                del memory["preferences"][key]
            
            memory["updated"] = datetime.now().isoformat()
            with open(memory_file, "w") as f:
                json.dump(memory, f, indent=2)
            
            return json.dumps({"success": True, "action": "deleted", "category": category})
        
        else:
            return json.dumps({"success": False, "error": "Invalid action"})
    
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def memory_profile(action: str = "get", key: str = "", value: str = "") -> str:
    """User profile memory."""
    return memory_enhanced(action, "user", key, value)

def memory_environment(action: str = "get", key: str = "", value: str = "") -> str:
    """Environment memory."""
    return memory_enhanced(action, "environment", key, value)

def memory_facts(action: str = "list", value: str = "") -> str:
    """Facts memory."""
    return memory_enhanced(action, "facts", "", value)

def memory_preferences(action: str = "get", key: str = "", value: str = "") -> str:
    """Preferences memory."""
    return memory_enhanced(action, "preferences", key, value)

def register_enhanced_memory_tools(register_tool):
    """Register enhanced memory tools."""
    register_tool(
        name="memory_enhanced",
        description="Enhanced memory with categories (user, environment, facts, preferences)",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: add, get, list, delete", "default": "list"},
                "category": {"type": "string", "description": "Category: user, environment, facts, preferences", "default": "all"},
                "key": {"type": "string", "description": "Memory key", "default": ""},
                "value": {"type": "string", "description": "Memory value", "default": ""}
            }
        },
        handler=lambda args: memory_enhanced(args.get("action", "list"), args.get("category", "all"), args.get("key", ""), args.get("value", ""))
    )
    
    register_tool(
        name="memory_profile",
        description="User profile memory",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: add, get, list, delete", "default": "get"},
                "key": {"type": "string", "description": "Profile key", "default": ""},
                "value": {"type": "string", "description": "Profile value", "default": ""}
            }
        },
        handler=lambda args: memory_profile(args.get("action", "get"), args.get("key", ""), args.get("value", ""))
    )
    
    register_tool(
        name="memory_environment",
        description="System environment memory",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: add, get, list, delete", "default": "get"},
                "key": {"type": "string", "description": "Environment key", "default": ""},
                "value": {"type": "string", "description": "Environment value", "default": ""}
            }
        },
        handler=lambda args: memory_environment(args.get("action", "get"), args.get("key", ""), args.get("value", ""))
    )
    
    register_tool(
        name="memory_facts",
        description="Learned facts memory",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: add, list, delete", "default": "list"},
                "value": {"type": "string", "description": "Fact value", "default": ""}
            }
        },
        handler=lambda args: memory_facts(args.get("action", "list"), args.get("value", ""))
    )
    
    register_tool(
        name="memory_preferences",
        description="User preferences memory",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: add, get, list, delete", "default": "get"},
                "key": {"type": "string", "description": "Preference key", "default": ""},
                "value": {"type": "string", "description": "Preference value", "default": ""}
            }
        },
        handler=lambda args: memory_preferences(args.get("action", "get"), args.get("key", ""), args.get("value", ""))
    )
