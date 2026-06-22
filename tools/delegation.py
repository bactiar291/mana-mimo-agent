"""
delegation.py — Subagent Delegation Tools
Spawn subagents for parallel task execution.
"""
import json
import os
import subprocess
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

# ─── Delegation Storage ──────────────────────────────────────────────────
DELEGATION_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "delegation")
os.makedirs(DELEGATION_DIR, exist_ok=True)

class DelegatedTask:
    def __init__(self, goal: str, context: str = "", toolsets: List[str] = None):
        self.task_id = str(uuid.uuid4())[:8]
        self.goal = goal
        self.context = context
        self.toolsets = toolsets or ["terminal", "file"]
        self.status = "pending"
        self.result = None
        self.created_at = datetime.now().isoformat()
        self.completed_at = None
    
    def to_dict(self):
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "context": self.context,
            "toolsets": self.toolsets,
            "status": self.status,
            "result": self.result,
            "created_at": self.created_at,
            "completed_at": self.completed_at
        }

def delegate_task(goal: str, context: str = "", toolsets: str = '["terminal", "file"]') -> str:
    """Delegate a task to a subagent."""
    try:
        toolsets_list = json.loads(toolsets) if isinstance(toolsets, str) else toolsets
        task = DelegatedTask(goal, context, toolsets_list)
        
        # Save task
        task_file = os.path.join(DELEGATION_DIR, f"{task.task_id}.json")
        with open(task_file, "w") as f:
            json.dump(task.to_dict(), f, indent=2)
        
        # Start execution in background
        def execute_task():
            task.status = "running"
            with open(task_file, "w") as f:
                json.dump(task.to_dict(), f, indent=2)

            try:
                from core.agent import MiMoAgent

                runtime = int(os.environ.get("MIMO_DELEGATE_RUNTIME", "240"))
                request_timeout = int(os.environ.get("MIMO_DELEGATE_REQUEST_TIMEOUT", "75"))
                max_tool_calls = int(os.environ.get("MIMO_DELEGATE_MAX_TOOL_CALLS", "0"))
                agent = MiMoAgent(
                    model=os.environ.get("MIMO_DELEGATE_MODEL", "mimo-v2.5-pro"),
                    web_search=True,
                    show_thinking=True,
                    quiet=True,
                    max_runtime=runtime,
                    request_timeout=request_timeout,
                    max_tool_calls=max_tool_calls,
                )
                prompt = goal
                if context:
                    prompt = f"{goal}\n\nContext:\n{context}"
                task.result = agent.chat(prompt)
                task.status = "completed"
            except Exception as error:
                task.status = "failed"
                task.result = str(error)
            finally:
                task.completed_at = datetime.now().isoformat()
                with open(task_file, "w") as f:
                    json.dump(task.to_dict(), f, indent=2)
        
        if os.environ.get("MIMO_DELEGATE_SYNC") == "1":
            execute_task()
        else:
            thread = threading.Thread(target=execute_task, daemon=True)
            thread.start()
        
        return json.dumps({
            "success": True,
            "task_id": task.task_id,
            "goal": goal,
            "status": "started",
            "message": "Task delegated to background MiMoAgent subagent"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def delegate_batch(tasks: str) -> str:
    """Delegate multiple tasks in parallel."""
    try:
        tasks_list = json.loads(tasks) if isinstance(tasks, str) else tasks
        results = []
        
        for task_def in tasks_list:
            result = delegate_task(
                task_def.get("goal", ""),
                task_def.get("context", ""),
                json.dumps(task_def.get("toolsets", ["terminal", "file"]))
            )
            results.append(json.loads(result))
        
        return json.dumps({
            "success": True,
            "tasks": results,
            "count": len(results),
            "message": f"{len(results)} tasks delegated"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def delegate_status(task_id: str = "") -> str:
    """Get task status or list all tasks."""
    try:
        if task_id:
            task_file = os.path.join(DELEGATION_DIR, f"{task_id}.json")
            if not os.path.exists(task_file):
                return json.dumps({"success": False, "error": "Task not found"})
            
            with open(task_file, "r") as f:
                return json.dumps({"success": True, "task": json.load(f)})
        else:
            tasks = []
            for f in os.listdir(DELEGATION_DIR):
                if f.endswith(".json"):
                    with open(os.path.join(DELEGATION_DIR, f), "r") as file:
                        tasks.append(json.load(file))
            
            return json.dumps({"success": True, "tasks": tasks, "count": len(tasks)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def delegate_cancel(task_id: str) -> str:
    """Cancel a delegated task."""
    try:
        task_file = os.path.join(DELEGATION_DIR, f"{task_id}.json")
        if not os.path.exists(task_file):
            return json.dumps({"success": False, "error": "Task not found"})
        
        with open(task_file, "r") as f:
            task = json.load(f)
        
        task["status"] = "cancelled"
        task["completed_at"] = datetime.now().isoformat()
        
        with open(task_file, "w") as f:
            json.dump(task, f, indent=2)
        
        return json.dumps({"success": True, "task_id": task_id, "status": "cancelled"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_delegation_tools(register_tool):
    """Register delegation tools."""
    register_tool(
        name="delegate_task",
        description="Delegate a task to a subagent",
        parameters={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "Task goal"},
                "context": {"type": "string", "description": "Task context", "default": ""},
                "toolsets": {"type": "string", "description": "JSON array of toolsets", "default": '["terminal", "file"]'}
            },
            "required": ["goal"]
        },
        handler=lambda args: delegate_task(args.get("goal", ""), args.get("context", ""), args.get("toolsets", '["terminal", "file"]'))
    )
    
    register_tool(
        name="delegate_batch",
        description="Delegate multiple tasks in parallel",
        parameters={
            "type": "object",
            "properties": {
                "tasks": {"type": "string", "description": "JSON array of task definitions"}
            },
            "required": ["tasks"]
        },
        handler=lambda args: delegate_batch(args.get("tasks", "[]"))
    )
    
    register_tool(
        name="delegate_status",
        description="Get task status or list all tasks",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID (empty to list all)", "default": ""}
            }
        },
        handler=lambda args: delegate_status(args.get("task_id", ""))
    )
    
    register_tool(
        name="delegate_cancel",
        description="Cancel a delegated task",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID to cancel"}
            },
            "required": ["task_id"]
        },
        handler=lambda args: delegate_cancel(args.get("task_id", ""))
    )
