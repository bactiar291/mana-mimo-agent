"""
cron_manager.py — Scheduled Tasks Manager
Create, manage, and execute scheduled tasks.
"""
import json
import os
import time
import threading
import uuid
from typing import Any, Callable, Dict, List, Optional
from datetime import datetime

# ─── Cron Storage ──────────────────────────────────────────────────────────
CRON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cron")
os.makedirs(CRON_DIR, exist_ok=True)

class CronJob:
    def __init__(self, name: str, schedule: str, command: str):
        self.job_id = str(uuid.uuid4())[:8]
        self.name = name
        self.schedule = schedule
        self.command = command
        self.enabled = True
        self.last_run = None
        self.next_run = None
        self.created_at = datetime.now().isoformat()
    
    def to_dict(self):
        return {
            "job_id": self.job_id,
            "name": self.name,
            "schedule": self.schedule,
            "command": self.command,
            "enabled": self.enabled,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "created_at": self.created_at
        }

def cron_create(name: str, schedule: str, command: str) -> str:
    """Create a cron job."""
    try:
        job = CronJob(name, schedule, command)
        
        job_file = os.path.join(CRON_DIR, f"{job.job_id}.json")
        with open(job_file, "w") as f:
            json.dump(job.to_dict(), f, indent=2)
        
        return json.dumps({
            "success": True,
            "job_id": job.job_id,
            "name": name,
            "schedule": schedule,
            "message": "Cron job created"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def cron_list() -> str:
    """List all cron jobs."""
    try:
        jobs = []
        for f in os.listdir(CRON_DIR):
            if f.endswith(".json"):
                with open(os.path.join(CRON_DIR, f), "r") as file:
                    jobs.append(json.load(file))
        
        return json.dumps({"success": True, "jobs": jobs, "count": len(jobs)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def cron_update(job_id: str, **kwargs) -> str:
    """Update a cron job."""
    try:
        job_file = os.path.join(CRON_DIR, f"{job_id}.json")
        if not os.path.exists(job_file):
            return json.dumps({"success": False, "error": "Job not found"})
        
        with open(job_file, "r") as f:
            job = json.load(f)
        
        for key, value in kwargs.items():
            if key in job:
                job[key] = value
        
        with open(job_file, "w") as f:
            json.dump(job, f, indent=2)
        
        return json.dumps({"success": True, "job_id": job_id, "updated": list(kwargs.keys())})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def cron_delete(job_id: str) -> str:
    """Delete a cron job."""
    try:
        job_file = os.path.join(CRON_DIR, f"{job_id}.json")
        if os.path.exists(job_file):
            os.remove(job_file)
            return json.dumps({"success": True, "deleted": job_id})
        else:
            return json.dumps({"success": False, "error": "Job not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def cron_pause(job_id: str) -> str:
    """Pause a cron job."""
    return cron_update(job_id, enabled=False)

def cron_resume(job_id: str) -> str:
    """Resume a cron job."""
    return cron_update(job_id, enabled=True)

def cron_run(job_id: str) -> str:
    """Run a cron job immediately."""
    try:
        job_file = os.path.join(CRON_DIR, f"{job_id}.json")
        if not os.path.exists(job_file):
            return json.dumps({"success": False, "error": "Job not found"})
        
        with open(job_file, "r") as f:
            job = json.load(f)
        
        # Update last run
        job["last_run"] = datetime.now().isoformat()
        with open(job_file, "w") as f:
            json.dump(job, f, indent=2)
        
        return json.dumps({
            "success": True,
            "job_id": job_id,
            "command": job["command"],
            "message": "Job executed"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_cron_manager_tools(register_tool):
    """Register cron manager tools."""
    register_tool(
        name="cron_create",
        description="Create a cron job",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Job name"},
                "schedule": {"type": "string", "description": "Cron schedule (e.g., '0 9 * * *')"},
                "command": {"type": "string", "description": "Command to execute"}
            },
            "required": ["name", "schedule", "command"]
        },
        handler=lambda args: cron_create(args.get("name", ""), args.get("schedule", ""), args.get("command", ""))
    )
    
    register_tool(
        name="cron_list",
        description="List all cron jobs",
        parameters={"type": "object", "properties": {}},
        handler=lambda args: cron_list()
    )
    
    register_tool(
        name="cron_update",
        description="Update a cron job",
        parameters={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID"},
                "name": {"type": "string", "description": "New name"},
                "schedule": {"type": "string", "description": "New schedule"},
                "command": {"type": "string", "description": "New command"}
            },
            "required": ["job_id"]
        },
        handler=lambda args: cron_update(args.get("job_id", ""), **{k: v for k, v in args.items() if k != "job_id"})
    )
    
    register_tool(
        name="cron_delete",
        description="Delete a cron job",
        parameters={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID"}
            },
            "required": ["job_id"]
        },
        handler=lambda args: cron_delete(args.get("job_id", ""))
    )
    
    register_tool(
        name="cron_pause",
        description="Pause a cron job",
        parameters={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID"}
            },
            "required": ["job_id"]
        },
        handler=lambda args: cron_pause(args.get("job_id", ""))
    )
    
    register_tool(
        name="cron_resume",
        description="Resume a cron job",
        parameters={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID"}
            },
            "required": ["job_id"]
        },
        handler=lambda args: cron_resume(args.get("job_id", ""))
    )
    
    register_tool(
        name="cron_run",
        description="Run a cron job immediately",
        parameters={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job ID"}
            },
            "required": ["job_id"]
        },
        handler=lambda args: cron_run(args.get("job_id", ""))
    )
