"""
checkpoints.py — Filesystem Checkpoints (Hermes-inspired)
Create and manage filesystem state snapshots.
"""
import json
import os
import shutil
import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime

# ─── Checkpoint Storage ──────────────────────────────────────────────────
CHECKPOINTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "checkpoints")
os.makedirs(CHECKPOINTS_DIR, exist_ok=True)

def checkpoint_create(name: str, path: str = ".", description: str = "") -> str:
    """Create a filesystem checkpoint."""
    try:
        checkpoint_id = f"{name}_{int(datetime.now().timestamp())}"
        checkpoint_dir = os.path.join(CHECKPOINTS_DIR, checkpoint_id)
        os.makedirs(checkpoint_dir, exist_ok=True)
        
        # Copy files
        if os.path.isdir(path):
            shutil.copytree(path, os.path.join(checkpoint_dir, "files"), dirs_exist_ok=True)
        else:
            shutil.copy2(path, checkpoint_dir)
        
        # Save metadata
        metadata = {
            "checkpoint_id": checkpoint_id,
            "name": name,
            "path": path,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "type": "directory" if os.path.isdir(path) else "file"
        }
        
        with open(os.path.join(checkpoint_dir, "metadata.json"), "w") as f:
            json.dump(metadata, f, indent=2)
        
        return json.dumps({
            "success": True,
            "checkpoint_id": checkpoint_id,
            "name": name,
            "path": path,
            "message": "Checkpoint created"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def checkpoint_list() -> str:
    """List all checkpoints."""
    try:
        checkpoints = []
        for d in os.listdir(CHECKPOINTS_DIR):
            checkpoint_dir = os.path.join(CHECKPOINTS_DIR, d)
            metadata_file = os.path.join(checkpoint_dir, "metadata.json")
            
            if os.path.exists(metadata_file):
                with open(metadata_file, "r") as f:
                    checkpoints.append(json.load(f))
        
        return json.dumps({"success": True, "checkpoints": checkpoints, "count": len(checkpoints)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def checkpoint_restore(checkpoint_id: str, target_path: str = "") -> str:
    """Restore a checkpoint."""
    try:
        checkpoint_dir = os.path.join(CHECKPOINTS_DIR, checkpoint_id)
        metadata_file = os.path.join(checkpoint_dir, "metadata.json")
        
        if not os.path.exists(metadata_file):
            return json.dumps({"success": False, "error": "Checkpoint not found"})
        
        with open(metadata_file, "r") as f:
            metadata = json.load(f)
        
        source_path = os.path.join(checkpoint_dir, "files")
        if not target_path:
            target_path = metadata.get("path", ".")
        
        # Restore files
        if os.path.isdir(source_path):
            shutil.copytree(source_path, target_path, dirs_exist_ok=True)
        else:
            shutil.copy2(source_path, target_path)
        
        return json.dumps({
            "success": True,
            "checkpoint_id": checkpoint_id,
            "restored_to": target_path,
            "message": "Checkpoint restored"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def checkpoint_diff(checkpoint_id: str, current_path: str = ".") -> str:
    """Compare checkpoint with current state."""
    try:
        checkpoint_dir = os.path.join(CHECKPOINTS_DIR, checkpoint_id)
        metadata_file = os.path.join(checkpoint_dir, "metadata.json")
        
        if not os.path.exists(metadata_file):
            return json.dumps({"success": False, "error": "Checkpoint not found"})
        
        with open(metadata_file, "r") as f:
            metadata = json.load(f)
        
        # Simple diff - list files
        checkpoint_files = set()
        files_dir = os.path.join(checkpoint_dir, "files")
        if os.path.exists(files_dir):
            for root, dirs, files in os.walk(files_dir):
                for file in files:
                    rel_path = os.path.relpath(os.path.join(root, file), files_dir)
                    checkpoint_files.add(rel_path)
        
        current_files = set()
        if os.path.exists(current_path):
            for root, dirs, files in os.walk(current_path):
                for file in files:
                    rel_path = os.path.relpath(os.path.join(root, file), current_path)
                    if not rel_path.startswith("data/"):
                        current_files.add(rel_path)
        
        added = current_files - checkpoint_files
        removed = checkpoint_files - current_files
        
        return json.dumps({
            "success": True,
            "checkpoint_id": checkpoint_id,
            "added": list(added)[:10],
            "removed": list(removed)[:10],
            "added_count": len(added),
            "removed_count": len(removed)
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def checkpoint_delete(checkpoint_id: str) -> str:
    """Delete a checkpoint."""
    try:
        checkpoint_dir = os.path.join(CHECKPOINTS_DIR, checkpoint_id)
        if os.path.exists(checkpoint_dir):
            shutil.rmtree(checkpoint_dir)
            return json.dumps({"success": True, "deleted": checkpoint_id})
        else:
            return json.dumps({"success": False, "error": "Checkpoint not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def checkpoint_cleanup(keep_last: int = 5) -> str:
    """Cleanup old checkpoints."""
    try:
        checkpoints = []
        for d in os.listdir(CHECKPOINTS_DIR):
            checkpoint_dir = os.path.join(CHECKPOINTS_DIR, d)
            metadata_file = os.path.join(checkpoint_dir, "metadata.json")
            
            if os.path.exists(metadata_file):
                with open(metadata_file, "r") as f:
                    metadata = json.load(f)
                    metadata["dir"] = d
                    checkpoints.append(metadata)
        
        # Sort by creation time
        checkpoints.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        
        # Delete old checkpoints
        deleted = 0
        for checkpoint in checkpoints[keep_last:]:
            checkpoint_dir = os.path.join(CHECKPOINTS_DIR, checkpoint["dir"])
            shutil.rmtree(checkpoint_dir)
            deleted += 1
        
        return json.dumps({
            "success": True,
            "deleted": deleted,
            "kept": min(keep_last, len(checkpoints)),
            "message": f"Cleaned up {deleted} checkpoints"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_checkpoint_tools(register_tool):
    """Register checkpoint tools."""
    register_tool(
        name="checkpoint_create",
        description="Create a filesystem checkpoint",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Checkpoint name"},
                "path": {"type": "string", "description": "Path to checkpoint", "default": "."},
                "description": {"type": "string", "description": "Description", "default": ""}
            },
            "required": ["name"]
        },
        handler=lambda args: checkpoint_create(args.get("name", ""), args.get("path", "."), args.get("description", ""))
    )
    
    register_tool(
        name="checkpoint_list",
        description="List all checkpoints",
        parameters={"type": "object", "properties": {}},
        handler=lambda args: checkpoint_list()
    )
    
    register_tool(
        name="checkpoint_restore",
        description="Restore a checkpoint",
        parameters={
            "type": "object",
            "properties": {
                "checkpoint_id": {"type": "string", "description": "Checkpoint ID"},
                "target_path": {"type": "string", "description": "Target path", "default": ""}
            },
            "required": ["checkpoint_id"]
        },
        handler=lambda args: checkpoint_restore(args.get("checkpoint_id", ""), args.get("target_path", ""))
    )
    
    register_tool(
        name="checkpoint_diff",
        description="Compare checkpoint with current state",
        parameters={
            "type": "object",
            "properties": {
                "checkpoint_id": {"type": "string", "description": "Checkpoint ID"},
                "current_path": {"type": "string", "description": "Current path", "default": "."}
            },
            "required": ["checkpoint_id"]
        },
        handler=lambda args: checkpoint_diff(args.get("checkpoint_id", ""), args.get("current_path", "."))
    )
    
    register_tool(
        name="checkpoint_delete",
        description="Delete a checkpoint",
        parameters={
            "type": "object",
            "properties": {
                "checkpoint_id": {"type": "string", "description": "Checkpoint ID"}
            },
            "required": ["checkpoint_id"]
        },
        handler=lambda args: checkpoint_delete(args.get("checkpoint_id", ""))
    )
    
    register_tool(
        name="checkpoint_cleanup",
        description="Cleanup old checkpoints",
        parameters={
            "type": "object",
            "properties": {
                "keep_last": {"type": "integer", "description": "Number of checkpoints to keep", "default": 5}
            }
        },
        handler=lambda args: checkpoint_cleanup(args.get("keep_last", 5))
    )
