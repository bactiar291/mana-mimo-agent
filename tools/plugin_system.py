"""
plugin_system.py — Plugin System (OpenClaw-inspired)
Load, manage, and execute plugins.
"""
import json
import os
import importlib
import importlib.util
import sys
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

# ─── Plugin Storage ──────────────────────────────────────────────────────
PLUGINS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "plugins")
os.makedirs(PLUGINS_DIR, exist_ok=True)

class Plugin:
    def __init__(self, name: str, path: str, config: Dict = None):
        self.plugin_id = f"plugin_{name}"
        self.name = name
        self.path = path
        self.config = config or {}
        self.enabled = True
        self.loaded = False
        self.module = None
        self.created_at = datetime.now().isoformat()
    
    def to_dict(self):
        return {
            "plugin_id": self.plugin_id,
            "name": self.name,
            "path": self.path,
            "config": self.config,
            "enabled": self.enabled,
            "loaded": self.loaded,
            "created_at": self.created_at
        }

def plugin_install(name: str, path: str, config: str = "{}") -> str:
    """Install a plugin."""
    try:
        config_dict = json.loads(config) if isinstance(config, str) else config
        plugin = Plugin(name, path, config_dict)
        
        # Save plugin config
        plugin_file = os.path.join(PLUGINS_DIR, f"{plugin.plugin_id}.json")
        with open(plugin_file, "w") as f:
            json.dump(plugin.to_dict(), f, indent=2)
        
        return json.dumps({
            "success": True,
            "plugin_id": plugin.plugin_id,
            "name": name,
            "message": "Plugin installed"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def plugin_list() -> str:
    """List all plugins."""
    try:
        plugins = []
        for f in os.listdir(PLUGINS_DIR):
            if f.endswith(".json"):
                with open(os.path.join(PLUGINS_DIR, f), "r") as file:
                    plugins.append(json.load(file))
        
        return json.dumps({"success": True, "plugins": plugins, "count": len(plugins)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def plugin_enable(plugin_id: str) -> str:
    """Enable a plugin."""
    try:
        plugin_file = os.path.join(PLUGINS_DIR, f"{plugin_id}.json")
        if not os.path.exists(plugin_file):
            return json.dumps({"success": False, "error": "Plugin not found"})
        
        with open(plugin_file, "r") as f:
            plugin = json.load(f)
        
        plugin["enabled"] = True
        
        with open(plugin_file, "w") as f:
            json.dump(plugin, f, indent=2)
        
        return json.dumps({"success": True, "plugin_id": plugin_id, "enabled": True})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def plugin_disable(plugin_id: str) -> str:
    """Disable a plugin."""
    try:
        plugin_file = os.path.join(PLUGINS_DIR, f"{plugin_id}.json")
        if not os.path.exists(plugin_file):
            return json.dumps({"success": False, "error": "Plugin not found"})
        
        with open(plugin_file, "r") as f:
            plugin = json.load(f)
        
        plugin["enabled"] = False
        
        with open(plugin_file, "w") as f:
            json.dump(plugin, f, indent=2)
        
        return json.dumps({"success": True, "plugin_id": plugin_id, "enabled": False})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def plugin_config(plugin_id: str, config: str = "{}") -> str:
    """Update plugin configuration."""
    try:
        plugin_file = os.path.join(PLUGINS_DIR, f"{plugin_id}.json")
        if not os.path.exists(plugin_file):
            return json.dumps({"success": False, "error": "Plugin not found"})
        
        with open(plugin_file, "r") as f:
            plugin = json.load(f)
        
        config_dict = json.loads(config) if isinstance(config, str) else config
        plugin["config"].update(config_dict)
        
        with open(plugin_file, "w") as f:
            json.dump(plugin, f, indent=2)
        
        return json.dumps({"success": True, "plugin_id": plugin_id, "config": plugin["config"]})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def plugin_remove(plugin_id: str) -> str:
    """Remove a plugin."""
    try:
        plugin_file = os.path.join(PLUGINS_DIR, f"{plugin_id}.json")
        if os.path.exists(plugin_file):
            os.remove(plugin_file)
            return json.dumps({"success": True, "removed": plugin_id})
        else:
            return json.dumps({"success": False, "error": "Plugin not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def plugin_reload(plugin_id: str) -> str:
    """Reload a plugin."""
    try:
        plugin_file = os.path.join(PLUGINS_DIR, f"{plugin_id}.json")
        if not os.path.exists(plugin_file):
            return json.dumps({"success": False, "error": "Plugin not found"})
        
        with open(plugin_file, "r") as f:
            plugin = json.load(f)
        
        # Reload module if loaded
        if plugin.get("loaded") and plugin.get("path"):
            try:
                spec = importlib.util.spec_from_file_location(plugin_id, plugin["path"])
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                plugin["loaded"] = True
            except Exception as e:
                return json.dumps({"success": False, "error": f"Failed to reload: {e}"})
        
        return json.dumps({"success": True, "plugin_id": plugin_id, "reloaded": True})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def plugin_info(plugin_id: str) -> str:
    """Get plugin info."""
    try:
        plugin_file = os.path.join(PLUGINS_DIR, f"{plugin_id}.json")
        if not os.path.exists(plugin_file):
            return json.dumps({"success": False, "error": "Plugin not found"})
        
        with open(plugin_file, "r") as f:
            return json.dumps({"success": True, "plugin": json.load(f)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_plugin_system_tools(register_tool):
    """Register plugin system tools."""
    register_tool(
        name="plugin_install",
        description="Install a plugin",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Plugin name"},
                "path": {"type": "string", "description": "Plugin file path"},
                "config": {"type": "string", "description": "JSON config", "default": "{}"}
            },
            "required": ["name", "path"]
        },
        handler=lambda args: plugin_install(args.get("name", ""), args.get("path", ""), args.get("config", "{}"))
    )
    
    register_tool(
        name="plugin_list",
        description="List all plugins",
        parameters={"type": "object", "properties": {}},
        handler=lambda args: plugin_list()
    )
    
    register_tool(
        name="plugin_enable",
        description="Enable a plugin",
        parameters={
            "type": "object",
            "properties": {
                "plugin_id": {"type": "string", "description": "Plugin ID"}
            },
            "required": ["plugin_id"]
        },
        handler=lambda args: plugin_enable(args.get("plugin_id", ""))
    )
    
    register_tool(
        name="plugin_disable",
        description="Disable a plugin",
        parameters={
            "type": "object",
            "properties": {
                "plugin_id": {"type": "string", "description": "Plugin ID"}
            },
            "required": ["plugin_id"]
        },
        handler=lambda args: plugin_disable(args.get("plugin_id", ""))
    )
    
    register_tool(
        name="plugin_config",
        description="Update plugin configuration",
        parameters={
            "type": "object",
            "properties": {
                "plugin_id": {"type": "string", "description": "Plugin ID"},
                "config": {"type": "string", "description": "JSON config"}
            },
            "required": ["plugin_id", "config"]
        },
        handler=lambda args: plugin_config(args.get("plugin_id", ""), args.get("config", "{}"))
    )
    
    register_tool(
        name="plugin_remove",
        description="Remove a plugin",
        parameters={
            "type": "object",
            "properties": {
                "plugin_id": {"type": "string", "description": "Plugin ID"}
            },
            "required": ["plugin_id"]
        },
        handler=lambda args: plugin_remove(args.get("plugin_id", ""))
    )
    
    register_tool(
        name="plugin_reload",
        description="Reload a plugin",
        parameters={
            "type": "object",
            "properties": {
                "plugin_id": {"type": "string", "description": "Plugin ID"}
            },
            "required": ["plugin_id"]
        },
        handler=lambda args: plugin_reload(args.get("plugin_id", ""))
    )
    
    register_tool(
        name="plugin_info",
        description="Get plugin info",
        parameters={
            "type": "object",
            "properties": {
                "plugin_id": {"type": "string", "description": "Plugin ID"}
            },
            "required": ["plugin_id"]
        },
        handler=lambda args: plugin_info(args.get("plugin_id", ""))
    )
