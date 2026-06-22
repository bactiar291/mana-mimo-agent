"""
supervisor.py — Supervisor/Planner System (DeerFlow-inspired)
Break complex tasks into sub-tasks with role assignment.
"""
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime

# ─── Plan Storage ──────────────────────────────────────────────────────────
PLANS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "plans")
os.makedirs(PLANS_DIR, exist_ok=True)

class Plan:
    def __init__(self, goal: str, steps: List[Dict] = None):
        self.plan_id = str(uuid.uuid4())[:8]
        self.goal = goal
        self.steps = steps or []
        self.status = "pending"
        self.created_at = datetime.now().isoformat()
        self.updated_at = self.created_at
    
    def to_dict(self):
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": self.steps,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

def supervisor_plan(goal: str, steps: str = "[]") -> str:
    """Create a plan for a complex goal."""
    try:
        steps_list = json.loads(steps) if isinstance(steps, str) else steps
        plan = Plan(goal, steps_list)
        
        # Save plan
        plan_path = os.path.join(PLANS_DIR, f"{plan.plan_id}.json")
        with open(plan_path, "w") as f:
            json.dump(plan.to_dict(), f, indent=2)
        
        return json.dumps({
            "success": True,
            "plan_id": plan.plan_id,
            "goal": goal,
            "steps_count": len(steps_list),
            "message": f"Plan created with {len(steps_list)} steps"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def supervisor_execute(plan_id: str, step_index: int = 0, status: str = "completed") -> str:
    """Update plan step status."""
    try:
        plan_path = os.path.join(PLANS_DIR, f"{plan_id}.json")
        if not os.path.exists(plan_path):
            return json.dumps({"success": False, "error": "Plan not found"})
        
        with open(plan_path, "r") as f:
            plan_data = json.load(f)
        
        if step_index < len(plan_data["steps"]):
            plan_data["steps"][step_index]["status"] = status
            plan_data["updated_at"] = datetime.now().isoformat()
            
            with open(plan_path, "w") as f:
                json.dump(plan_data, f, indent=2)
            
            return json.dumps({
                "success": True,
                "plan_id": plan_id,
                "step_index": step_index,
                "status": status
            })
        else:
            return json.dumps({"success": False, "error": "Step index out of range"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def supervisor_status(plan_id: str = "") -> str:
    """Get plan status or list all plans."""
    try:
        if plan_id:
            plan_path = os.path.join(PLANS_DIR, f"{plan_id}.json")
            if not os.path.exists(plan_path):
                return json.dumps({"success": False, "error": "Plan not found"})
            
            with open(plan_path, "r") as f:
                return json.dumps({"success": True, "plan": json.load(f)})
        else:
            plans = []
            for f in os.listdir(PLANS_DIR):
                if f.endswith(".json"):
                    with open(os.path.join(PLANS_DIR, f), "r") as file:
                        plans.append(json.load(file))
            return json.dumps({"success": True, "plans": plans, "count": len(plans)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def supervisor_adapt(plan_id: str, feedback: str) -> str:
    """Adapt plan based on feedback."""
    try:
        plan_path = os.path.join(PLANS_DIR, f"{plan_id}.json")
        if not os.path.exists(plan_path):
            return json.dumps({"success": False, "error": "Plan not found"})
        
        with open(plan_path, "r") as f:
            plan_data = json.load(f)
        
        plan_data["feedback"] = feedback
        plan_data["status"] = "adapting"
        plan_data["updated_at"] = datetime.now().isoformat()
        
        with open(plan_path, "w") as f:
            json.dump(plan_data, f, indent=2)
        
        return json.dumps({
            "success": True,
            "plan_id": plan_id,
            "message": "Plan marked for adaptation",
            "feedback": feedback
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_supervisor_tools(register_tool):
    """Register supervisor tools."""
    register_tool(
        name="supervisor_plan",
        description="Create a plan for a complex goal with sub-tasks",
        parameters={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "The main goal to achieve"},
                "steps": {"type": "string", "description": "JSON array of steps", "default": "[]"}
            },
            "required": ["goal"]
        },
        handler=lambda args: supervisor_plan(args.get("goal", ""), args.get("steps", "[]"))
    )
    
    register_tool(
        name="supervisor_execute",
        description="Update plan step status",
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "Plan ID"},
                "step_index": {"type": "integer", "description": "Step index", "default": 0},
                "status": {"type": "string", "description": "New status", "default": "completed"}
            },
            "required": ["plan_id"]
        },
        handler=lambda args: supervisor_execute(args.get("plan_id", ""), args.get("step_index", 0), args.get("status", "completed"))
    )
    
    register_tool(
        name="supervisor_status",
        description="Get plan status or list all plans",
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "Plan ID (empty to list all)", "default": ""}
            }
        },
        handler=lambda args: supervisor_status(args.get("plan_id", ""))
    )
    
    register_tool(
        name="supervisor_adapt",
        description="Adapt plan based on feedback",
        parameters={
            "type": "object",
            "properties": {
                "plan_id": {"type": "string", "description": "Plan ID"},
                "feedback": {"type": "string", "description": "Feedback for adaptation"}
            },
            "required": ["plan_id", "feedback"]
        },
        handler=lambda args: supervisor_adapt(args.get("plan_id", ""), args.get("feedback", ""))
    )
