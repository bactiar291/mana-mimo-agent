"""
thinking.py — Chain-of-Thought & Error Recovery
Error analysis, recovery planning, reasoning chains.
"""
import json
import os
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

# ─── Thinking Storage ──────────────────────────────────────────────────────
THINKING_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "thinking")
os.makedirs(THINKING_DIR, exist_ok=True)

def thinking_analyze(error: str, context: str = "") -> str:
    """Analyze an error and suggest recovery."""
    try:
        analysis = {
            "error": error,
            "context": context,
            "timestamp": datetime.now().isoformat(),
            "category": "unknown",
            "suggestions": []
        }
        
        # Categorize error
        error_lower = error.lower()
        if "connection" in error_lower or "timeout" in error_lower:
            analysis["category"] = "connection"
            analysis["suggestions"] = [
                "Check network connectivity",
                "Verify the URL is accessible",
                "Try with a different timeout",
                "Use browser_open for JS-heavy sites"
            ]
        elif "permission" in error_lower or "access" in error_lower:
            analysis["category"] = "permission"
            analysis["suggestions"] = [
                "Check file permissions",
                "Run with appropriate user privileges",
                "Verify path exists and is accessible"
            ]
        elif "not found" in error_lower or "404" in error_lower:
            analysis["category"] = "not_found"
            analysis["suggestions"] = [
                "Verify the resource exists",
                "Check URL/path spelling",
                "Use search_files to locate the resource"
            ]
        elif "syntax" in error_lower or "parse" in error_lower:
            analysis["category"] = "syntax"
            analysis["suggestions"] = [
                "Check syntax of the code/config",
                "Validate JSON/YAML format",
                "Look for missing brackets or quotes"
            ]
        else:
            analysis["suggestions"] = [
                "Review the error message carefully",
                "Check logs for more details",
                "Try a different approach"
            ]
        
        # Save analysis
        analysis_file = os.path.join(THINKING_DIR, f"analysis_{int(time.time())}.json")
        with open(analysis_file, "w") as f:
            json.dump(analysis, f, indent=2)
        
        return json.dumps({"success": True, "analysis": analysis})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def thinking_plan(goal: str, constraints: str = "[]") -> str:
    """Create a reasoning plan."""
    try:
        constraints_list = json.loads(constraints) if isinstance(constraints, str) else constraints
        
        plan = {
            "goal": goal,
            "constraints": constraints_list,
            "steps": [],
            "timestamp": datetime.now().isoformat()
        }
        
        # Generate basic plan steps
        plan["steps"] = [
            {"step": 1, "action": "Analyze the goal and constraints", "status": "pending"},
            {"step": 2, "action": "Gather required information", "status": "pending"},
            {"step": 3, "action": "Execute the plan", "status": "pending"},
            {"step": 4, "action": "Verify results", "status": "pending"}
        ]
        
        # Save plan
        plan_file = os.path.join(THINKING_DIR, f"plan_{int(time.time())}.json")
        with open(plan_file, "w") as f:
            json.dump(plan, f, indent=2)
        
        return json.dumps({"success": True, "plan": plan})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def thinking_chain(thoughts: str) -> str:
    """Record a chain of thoughts."""
    try:
        chain = {
            "thoughts": thoughts,
            "timestamp": datetime.now().isoformat()
        }
        
        chain_file = os.path.join(THINKING_DIR, f"chain_{int(time.time())}.json")
        with open(chain_file, "w") as f:
            json.dump(chain, f, indent=2)
        
        return json.dumps({"success": True, "message": "Thought chain recorded"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def thinking_list(limit: int = 10) -> str:
    """List recent thinking sessions."""
    try:
        files = sorted(os.listdir(THINKING_DIR), reverse=True)[:limit]
        sessions = []
        
        for f in files:
            if f.endswith(".json"):
                with open(os.path.join(THINKING_DIR, f), "r") as file:
                    data = json.load(file)
                    sessions.append({"file": f, "data": data})
        
        return json.dumps({"success": True, "sessions": sessions, "count": len(sessions)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_thinking_tools(register_tool):
    """Register thinking tools."""
    register_tool(
        name="thinking_analyze",
        description="Analyze an error and suggest recovery",
        parameters={
            "type": "object",
            "properties": {
                "error": {"type": "string", "description": "Error message"},
                "context": {"type": "string", "description": "Additional context", "default": ""}
            },
            "required": ["error"]
        },
        handler=lambda args: thinking_analyze(args.get("error", ""), args.get("context", ""))
    )
    
    register_tool(
        name="thinking_plan",
        description="Create a reasoning plan",
        parameters={
            "type": "object",
            "properties": {
                "goal": {"type": "string", "description": "Goal to achieve"},
                "constraints": {"type": "string", "description": "JSON array of constraints", "default": "[]"}
            },
            "required": ["goal"]
        },
        handler=lambda args: thinking_plan(args.get("goal", ""), args.get("constraints", "[]"))
    )
    
    register_tool(
        name="thinking_chain",
        description="Record a chain of thoughts",
        parameters={
            "type": "object",
            "properties": {
                "thoughts": {"type": "string", "description": "Thoughts to record"}
            },
            "required": ["thoughts"]
        },
        handler=lambda args: thinking_chain(args.get("thoughts", ""))
    )
    
    register_tool(
        name="thinking_list",
        description="List recent thinking sessions",
        parameters={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max results", "default": 10}
            }
        },
        handler=lambda args: thinking_list(args.get("limit", 10))
    )
