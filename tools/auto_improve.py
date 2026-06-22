"""
auto_improve.py — Self-Learning Auto-Improvement System (OpenClaw-inspired)
Learn from errors, recognize patterns, and auto-correct similar issues.
"""
import json
import os
import re
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

# ─── Learning Storage ──────────────────────────────────────────────────────
LEARNING_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "learning")
os.makedirs(LEARNING_DIR, exist_ok=True)

class ErrorPattern:
    def __init__(self, pattern_id: str, error_type: str, description: str, solution: str = ""):
        self.pattern_id = pattern_id
        self.error_type = error_type
        self.description = description
        self.solution = solution
        self.seen_count = 0
        self.resolved_count = 0
        self.last_seen = None
    
    def to_dict(self):
        return {
            "pattern_id": self.pattern_id,
            "error_type": self.error_type,
            "description": self.description,
            "solution": self.solution,
            "seen_count": self.seen_count,
            "resolved_count": self.resolved_count,
            "success_rate": self.resolved_count / max(1, self.seen_count),
            "last_seen": self.last_seen
        }

def auto_improve_learn(error: str, solution: str = "", context: str = "") -> str:
    """Learn from an error and solution."""
    try:
        # Generate pattern ID
        pattern_id = f"pattern_{int(time.time())}"
        
        # Categorize error
        error_lower = error.lower()
        if "connection" in error_lower or "timeout" in error_lower:
            error_type = "connection"
        elif "permission" in error_lower:
            error_type = "permission"
        elif "not found" in error_lower:
            error_type = "not_found"
        elif "syntax" in error_lower:
            error_type = "syntax"
        else:
            error_type = "unknown"
        
        # Create pattern
        pattern = ErrorPattern(pattern_id, error_type, error, solution)
        pattern.seen_count = 1
        pattern.resolved_count = 1 if solution else 0
        pattern.last_seen = datetime.now().isoformat()
        
        # Save pattern
        pattern_file = os.path.join(LEARNING_DIR, f"{pattern_id}.json")
        with open(pattern_file, "w") as f:
            json.dump(pattern.to_dict(), f, indent=2)
        
        return json.dumps({
            "success": True,
            "pattern_id": pattern_id,
            "error_type": error_type,
            "message": "Error pattern learned"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def auto_improve_status() -> str:
    """Get learning status."""
    try:
        patterns = []
        for f in os.listdir(LEARNING_DIR):
            if f.endswith(".json"):
                with open(os.path.join(LEARNING_DIR, f), "r") as file:
                    patterns.append(json.load(file))
        
        # Calculate stats
        total_patterns = len(patterns)
        total_seen = sum(p.get("seen_count", 0) for p in patterns)
        total_resolved = sum(p.get("resolved_count", 0) for p in patterns)
        
        return json.dumps({
            "success": True,
            "total_patterns": total_patterns,
            "total_seen": total_seen,
            "total_resolved": total_resolved,
            "success_rate": total_resolved / max(1, total_seen),
            "patterns": patterns[:10]  # Return top 10
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def auto_improve_report(error: str) -> str:
    """Get improvement suggestions for an error."""
    try:
        # Search for similar patterns
        similar = []
        for f in os.listdir(LEARNING_DIR):
            if f.endswith(".json"):
                with open(os.path.join(LEARNING_DIR, f), "r") as file:
                    pattern = json.load(file)
                    
                    # Simple similarity check
                    if pattern.get("error_type", "") in error.lower() or \
                       any(word in error.lower() for word in pattern.get("description", "").lower().split()):
                        similar.append(pattern)
        
        if similar:
            # Return best matching solution
            best = max(similar, key=lambda x: x.get("success_rate", 0))
            return json.dumps({
                "success": True,
                "found": True,
                "suggestion": best.get("solution", ""),
                "confidence": best.get("success_rate", 0),
                "pattern_id": best.get("pattern_id", "")
            })
        else:
            return json.dumps({
                "success": True,
                "found": False,
                "message": "No similar patterns found"
            })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def learning_add(category: str, key: str, value: str) -> str:
    """Add a learning entry."""
    try:
        learning_file = os.path.join(LEARNING_DIR, "learnings.json")
        
        if os.path.exists(learning_file):
            with open(learning_file, "r") as f:
                learnings = json.load(f)
        else:
            learnings = {}
        
        if category not in learnings:
            learnings[category] = {}
        
        learnings[category][key] = {
            "value": value,
            "added_at": datetime.now().isoformat()
        }
        
        with open(learning_file, "w") as f:
            json.dump(learnings, f, indent=2)
        
        return json.dumps({"success": True, "category": category, "key": key})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_auto_improve_tools(register_tool):
    """Register auto-improve tools."""
    register_tool(
        name="auto_improve_learn",
        description="Learn from an error and solution",
        parameters={
            "type": "object",
            "properties": {
                "error": {"type": "string", "description": "Error message"},
                "solution": {"type": "string", "description": "Solution", "default": ""},
                "context": {"type": "string", "description": "Additional context", "default": ""}
            },
            "required": ["error"]
        },
        handler=lambda args: auto_improve_learn(args.get("error", ""), args.get("solution", ""), args.get("context", ""))
    )
    
    register_tool(
        name="auto_improve_status",
        description="Get learning status",
        parameters={"type": "object", "properties": {}},
        handler=lambda args: auto_improve_status()
    )
    
    register_tool(
        name="auto_improve_report",
        description="Get improvement suggestions for an error",
        parameters={
            "type": "object",
            "properties": {
                "error": {"type": "string", "description": "Error to analyze"}
            },
            "required": ["error"]
        },
        handler=lambda args: auto_improve_report(args.get("error", ""))
    )
    
    register_tool(
        name="learning_add",
        description="Add a learning entry",
        parameters={
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Category"},
                "key": {"type": "string", "description": "Key"},
                "value": {"type": "string", "description": "Value"}
            },
            "required": ["category", "key", "value"]
        },
        handler=lambda args: learning_add(args.get("category", ""), args.get("key", ""), args.get("value", ""))
    )
