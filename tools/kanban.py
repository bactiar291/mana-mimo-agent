"""
kanban.py — Kanban Multi-Agent Work Queue (Hermes-inspired)
Manage tasks across multiple agents.
"""
import json
import os
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

# ─── Kanban Storage ──────────────────────────────────────────────────────
KANBAN_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "kanban")
os.makedirs(KANBAN_DIR, exist_ok=True)

class KanbanTask:
    def __init__(self, title: str, description: str = "", status: str = "todo", assignee: str = ""):
        self.task_id = str(uuid.uuid4())[:8]
        self.title = title
        self.description = description
        self.status = status
        self.assignee = assignee
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
    
    def to_dict(self):
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "assignee": self.assignee,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

def kanban_task(action: str = "list", task_id: str = "", title: str = "", description: str = "", status: str = "todo", assignee: str = "") -> str:
    """Manage kanban tasks."""
    try:
        if action == "create":
            task = KanbanTask(title, description, status, assignee)
            task_file = os.path.join(KANBAN_DIR, f"{task.task_id}.json")
            with open(task_file, "w") as f:
                json.dump(task.to_dict(), f, indent=2)
            
            return json.dumps({
                "success": True,
                "task_id": task.task_id,
                "title": title,
                "message": "Task created"
            })
        
        elif action == "list":
            tasks = []
            for f in os.listdir(KANBAN_DIR):
                if f.endswith(".json"):
                    with open(os.path.join(KANBAN_DIR, f), "r") as file:
                        tasks.append(json.load(file))
            
            return json.dumps({"success": True, "tasks": tasks, "count": len(tasks)})
        
        elif action == "get":
            task_file = os.path.join(KANBAN_DIR, f"{task_id}.json")
            if os.path.exists(task_file):
                with open(task_file, "r") as f:
                    return json.dumps({"success": True, "task": json.load(f)})
            else:
                return json.dumps({"success": False, "error": "Task not found"})
        
        elif action == "update":
            task_file = os.path.join(KANBAN_DIR, f"{task_id}.json")
            if not os.path.exists(task_file):
                return json.dumps({"success": False, "error": "Task not found"})
            
            with open(task_file, "r") as f:
                task = json.load(f)
            
            if title:
                task["title"] = title
            if description:
                task["description"] = description
            if status:
                task["status"] = status
            if assignee:
                task["assignee"] = assignee
            
            task["updated_at"] = datetime.now().isoformat()
            
            with open(task_file, "w") as f:
                json.dump(task, f, indent=2)
            
            return json.dumps({"success": True, "task_id": task_id, "message": "Task updated"})
        
        elif action == "delete":
            task_file = os.path.join(KANBAN_DIR, f"{task_id}.json")
            if os.path.exists(task_file):
                os.remove(task_file)
                return json.dumps({"success": True, "task_id": task_id, "message": "Task deleted"})
            else:
                return json.dumps({"success": False, "error": "Task not found"})
        
        else:
            return json.dumps({"success": False, "error": "Invalid action"})
    
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def kanban_move(task_id: str, status: str) -> str:
    """Move task to a new status."""
    return kanban_task(action="update", task_id=task_id, status=status)

def kanban_assign(task_id: str, assignee: str) -> str:
    """Assign task to an agent."""
    return kanban_task(action="update", task_id=task_id, assignee=assignee)

def kanban_list(status: str = "") -> str:
    """List tasks, optionally filtered by status."""
    try:
        tasks = []
        for f in os.listdir(KANBAN_DIR):
            if f.endswith(".json"):
                with open(os.path.join(KANBAN_DIR, f), "r") as file:
                    task = json.load(file)
                    if not status or task.get("status") == status:
                        tasks.append(task)
        
        return json.dumps({"success": True, "tasks": tasks, "count": len(tasks)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def kanban_complete(task_id: str) -> str:
    """Mark task as completed."""
    return kanban_move(task_id, "done")

def kanban_block(task_id: str, reason: str = "") -> str:
    """Mark task as blocked."""
    return kanban_task(action="update", task_id=task_id, status="blocked", description=reason)

def register_kanban_tools(register_tool):
    """Register kanban tools."""
    register_tool(
        name="kanban_task",
        description="Manage kanban tasks (create, list, get, update, delete)",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: create, list, get, update, delete", "default": "list"},
                "task_id": {"type": "string", "description": "Task ID", "default": ""},
                "title": {"type": "string", "description": "Task title", "default": ""},
                "description": {"type": "string", "description": "Task description", "default": ""},
                "status": {"type": "string", "description": "Task status", "default": "todo"},
                "assignee": {"type": "string", "description": "Task assignee", "default": ""}
            }
        },
        handler=lambda args: kanban_task(args.get("action", "list"), args.get("task_id", ""), args.get("title", ""), args.get("description", ""), args.get("status", "todo"), args.get("assignee", ""))
    )
    
    register_tool(
        name="kanban_move",
        description="Move task to a new status",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "status": {"type": "string", "description": "New status"}
            },
            "required": ["task_id", "status"]
        },
        handler=lambda args: kanban_move(args.get("task_id", ""), args.get("status", ""))
    )
    
    register_tool(
        name="kanban_assign",
        description="Assign task to an agent",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "assignee": {"type": "string", "description": "Assignee name"}
            },
            "required": ["task_id", "assignee"]
        },
        handler=lambda args: kanban_assign(args.get("task_id", ""), args.get("assignee", ""))
    )
    
    register_tool(
        name="kanban_list",
        description="List tasks, optionally filtered by status",
        parameters={
            "type": "object",
            "properties": {
                "status": {"type": "string", "description": "Filter by status", "default": ""}
            }
        },
        handler=lambda args: kanban_list(args.get("status", ""))
    )
    
    register_tool(
        name="kanban_complete",
        description="Mark task as completed",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"}
            },
            "required": ["task_id"]
        },
        handler=lambda args: kanban_complete(args.get("task_id", ""))
    )
    
    register_tool(
        name="kanban_block",
        description="Mark task as blocked",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "reason": {"type": "string", "description": "Block reason", "default": ""}
            },
            "required": ["task_id"]
        },
        handler=lambda args: kanban_block(args.get("task_id", ""), args.get("reason", ""))
    )
