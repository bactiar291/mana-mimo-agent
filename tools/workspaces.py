"""
workspaces.py — Agent Workspaces (OpenClaw-inspired)
Isolated workspaces for different tasks.
"""
import json
import os
import shutil
from typing import Any, Dict, List, Optional
from datetime import datetime

# ─── Workspace Storage ──────────────────────────────────────────────────
WORKSPACES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "workspaces")
os.makedirs(WORKSPACES_DIR, exist_ok=True)

class Workspace:
    def __init__(self, name: str, description: str = ""):
        self.workspace_id = f"ws_{name}"
        self.name = name
        self.description = description
        self.path = os.path.join(WORKSPACES_DIR, name)
        self.created_at = datetime.now().isoformat()
        self.active = False
    
    def to_dict(self):
        return {
            "workspace_id": self.workspace_id,
            "name": self.name,
            "description": self.description,
            "path": self.path,
            "created_at": self.created_at,
            "active": self.active
        }

def workspace_create(name: str, description: str = "") -> str:
    """Create a new workspace."""
    try:
        workspace = Workspace(name, description)
        os.makedirs(workspace.path, exist_ok=True)
        
        # Save metadata
        metadata_file = os.path.join(workspace.path, ".workspace.json")
        with open(metadata_file, "w") as f:
            json.dump(workspace.to_dict(), f, indent=2)
        
        return json.dumps({
            "success": True,
            "workspace_id": workspace.workspace_id,
            "name": name,
            "path": workspace.path,
            "message": "Workspace created"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def workspace_switch(name: str) -> str:
    """Switch to a workspace."""
    try:
        workspace_path = os.path.join(WORKSPACES_DIR, name)
        if not os.path.exists(workspace_path):
            return json.dumps({"success": False, "error": "Workspace not found"})
        
        # Update active workspace
        for d in os.listdir(WORKSPACES_DIR):
            ws_path = os.path.join(WORKSPACES_DIR, d)
            metadata_file = os.path.join(ws_path, ".workspace.json")
            
            if os.path.exists(metadata_file):
                with open(metadata_file, "r") as f:
                    ws = json.load(f)
                
                ws["active"] = (d == name)
                
                with open(metadata_file, "w") as f:
                    json.dump(ws, f, indent=2)
        
        return json.dumps({
            "success": True,
            "name": name,
            "path": workspace_path,
            "message": f"Switched to workspace: {name}"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def workspace_list() -> str:
    """List all workspaces."""
    try:
        workspaces = []
        for d in os.listdir(WORKSPACES_DIR):
            ws_path = os.path.join(WORKSPACES_DIR, d)
            metadata_file = os.path.join(ws_path, ".workspace.json")
            
            if os.path.exists(metadata_file):
                with open(metadata_file, "r") as f:
                    workspaces.append(json.load(f))
        
        return json.dumps({"success": True, "workspaces": workspaces, "count": len(workspaces)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def workspace_delete(name: str) -> str:
    """Delete a workspace."""
    try:
        workspace_path = os.path.join(WORKSPACES_DIR, name)
        if os.path.exists(workspace_path):
            shutil.rmtree(workspace_path)
            return json.dumps({"success": True, "name": name, "message": "Workspace deleted"})
        else:
            return json.dumps({"success": False, "error": "Workspace not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def workspace_config(name: str, config: str = "{}") -> str:
    """Update workspace configuration."""
    try:
        workspace_path = os.path.join(WORKSPACES_DIR, name)
        metadata_file = os.path.join(workspace_path, ".workspace.json")
        
        if not os.path.exists(metadata_file):
            return json.dumps({"success": False, "error": "Workspace not found"})
        
        with open(metadata_file, "r") as f:
            ws = json.load(f)
        
        config_dict = json.loads(config) if isinstance(config, str) else config
        ws["config"] = config_dict
        
        with open(metadata_file, "w") as f:
            json.dump(ws, f, indent=2)
        
        return json.dumps({"success": True, "name": name, "config": config_dict})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def workspace_status(name: str = "") -> str:
    """Get workspace status."""
    try:
        if name:
            workspace_path = os.path.join(WORKSPACES_DIR, name)
            metadata_file = os.path.join(workspace_path, ".workspace.json")
            
            if os.path.exists(metadata_file):
                with open(metadata_file, "r") as f:
                    return json.dumps({"success": True, "workspace": json.load(f)})
            else:
                return json.dumps({"success": False, "error": "Workspace not found"})
        else:
            # Return current active workspace
            for d in os.listdir(WORKSPACES_DIR):
                ws_path = os.path.join(WORKSPACES_DIR, d)
                metadata_file = os.path.join(ws_path, ".workspace.json")
                
                if os.path.exists(metadata_file):
                    with open(metadata_file, "r") as f:
                        ws = json.load(f)
                        if ws.get("active"):
                            return json.dumps({"success": True, "workspace": ws})
            
            return json.dumps({"success": True, "workspace": None, "message": "No active workspace"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_workspace_tools(register_tool):
    """Register workspace tools."""
    register_tool(
        name="workspace_create",
        description="Create a new workspace",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Workspace name"},
                "description": {"type": "string", "description": "Description", "default": ""}
            },
            "required": ["name"]
        },
        handler=lambda args: workspace_create(args.get("name", ""), args.get("description", ""))
    )
    
    register_tool(
        name="workspace_switch",
        description="Switch to a workspace",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Workspace name"}
            },
            "required": ["name"]
        },
        handler=lambda args: workspace_switch(args.get("name", ""))
    )
    
    register_tool(
        name="workspace_list",
        description="List all workspaces",
        parameters={"type": "object", "properties": {}},
        handler=lambda args: workspace_list()
    )
    
    register_tool(
        name="workspace_delete",
        description="Delete a workspace",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Workspace name"}
            },
            "required": ["name"]
        },
        handler=lambda args: workspace_delete(args.get("name", ""))
    )
    
    register_tool(
        name="workspace_config",
        description="Update workspace configuration",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Workspace name"},
                "config": {"type": "string", "description": "JSON config"}
            },
            "required": ["name", "config"]
        },
        handler=lambda args: workspace_config(args.get("name", ""), args.get("config", "{}"))
    )
    
    register_tool(
        name="workspace_status",
        description="Get workspace status",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Workspace name", "default": ""}
            }
        },
        handler=lambda args: workspace_status(args.get("name", ""))
    )
