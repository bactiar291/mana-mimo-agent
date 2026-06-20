"""
upgrade.py — Self-learning & error recovery system for Agent
Makes the agent upgrade itself based on usage patterns
"""
import json
import os
import time
from datetime import datetime
from typing import Dict, List, Any

# ─── Learning Database ──────────────────────────────────────────────────────

LEARN_DB = os.path.expanduser("~/.agent/learn.json")

def _load_learn() -> dict:
    os.makedirs(os.path.dirname(LEARN_DB), exist_ok=True)
    if os.path.exists(LEARN_DB):
        try:
            with open(LEARN_DB, 'r') as f:
                return json.load(f)
        except:
            pass
    return {
        "patterns": {},       # Successful patterns
        "errors": {},         # Error patterns and fixes
        "tool_usage": {},     # Tool usage stats
        "success_rate": {},   # Task success rates
        "upgrades": [],       # Upgrade log
        "created": datetime.now().isoformat()
    }

def _save_learn(data: dict):
    data["updated"] = datetime.now().isoformat()
    with open(LEARN_DB, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ─── Pattern Learning ───────────────────────────────────────────────────────

def learn_pattern(task_type: str, steps: List[str], success: bool):
    """Learn from successful/failed task patterns."""
    data = _load_learn()
    
    if task_type not in data["patterns"]:
        data["patterns"][task_type] = {"success": [], "failure": [], "count": 0}
    
    entry = {
        "steps": steps,
        "timestamp": datetime.now().isoformat(),
        "success": success
    }
    
    if success:
        data["patterns"][task_type]["success"].append(entry)
        data["patterns"][task_type]["success"] = data["patterns"][task_type]["success"][-10:]  # Keep last 10
    else:
        data["patterns"][task_type]["failure"].append(entry)
        data["patterns"][task_type]["failure"] = data["patterns"][task_type]["failure"][-10:]
    
    data["patterns"][task_type]["count"] += 1
    _save_learn(data)

def get_best_pattern(task_type: str) -> Dict[str, Any]:
    """Get the best known pattern for a task type."""
    data = _load_learn()
    
    if task_type not in data["patterns"]:
        return {"found": False, "message": f"No patterns learned for '{task_type}' yet"}
    
    pattern = data["patterns"][task_type]
    success_count = len(pattern["success"])
    failure_count = len(pattern["failure"])
    total = pattern["count"]
    
    if success_count == 0:
        return {"found": False, "message": f"No successful patterns for '{task_type}' yet"}
    
    # Get most recent success
    latest = pattern["success"][-1]
    
    return {
        "found": True,
        "task_type": task_type,
        "success_rate": success_count / total if total > 0 else 0,
        "recommended_steps": latest["steps"],
        "total_attempts": total,
        "success_count": success_count,
        "failure_count": failure_count
    }


# ─── Error Learning ─────────────────────────────────────────────────────────

def learn_error(error_type: str, error_msg: str, fix_applied: str = None):
    """Learn from errors and their fixes."""
    data = _load_learn()
    
    if error_type not in data["errors"]:
        data["errors"][error_type] = {"occurrences": 0, "fixes": [], "last_seen": None}
    
    data["errors"][error_type]["occurrences"] += 1
    data["errors"][error_type]["last_seen"] = datetime.now().isoformat()
    
    if fix_applied:
        data["errors"][error_type]["fixes"].append({
            "fix": fix_applied,
            "timestamp": datetime.now().isoformat()
        })
        data["errors"][error_type]["fixes"] = data["errors"][error_type]["fixes"][-5:]  # Keep last 5
    
    _save_learn(data)

def get_error_fix(error_type: str) -> Dict[str, Any]:
    """Get known fix for an error type."""
    data = _load_learn()
    
    if error_type not in data["errors"]:
        return {"found": False}
    
    error = data["errors"][error_type]
    if not error["fixes"]:
        return {"found": False, "occurrences": error["occurrences"]}
    
    return {
        "found": True,
        "occurrences": error["occurrences"],
        "last_fix": error["fixes"][-1]["fix"],
        "all_fixes": [f["fix"] for f in error["fixes"]]
    }


# ─── Tool Usage Tracking ───────────────────────────────────────────────────

def track_tool_usage(tool_name: str, success: bool, duration_ms: int):
    """Track tool usage statistics."""
    data = _load_learn()
    
    if tool_name not in data["tool_usage"]:
        data["tool_usage"][tool_name] = {
            "total_calls": 0,
            "successes": 0,
            "failures": 0,
            "avg_duration_ms": 0,
            "last_used": None
        }
    
    stats = data["tool_usage"][tool_name]
    stats["total_calls"] += 1
    if success:
        stats["successes"] += 1
    else:
        stats["failures"] += 1
    
    # Running average duration
    stats["avg_duration_ms"] = (
        (stats["avg_duration_ms"] * (stats["total_calls"] - 1) + duration_ms) / stats["total_calls"]
    )
    stats["last_used"] = datetime.now().isoformat()
    
    _save_learn(data)

def get_tool_stats(tool_name: str = None) -> Dict[str, Any]:
    """Get tool usage statistics."""
    data = _load_learn()
    
    if tool_name:
        if tool_name in data["tool_usage"]:
            return {"tool": tool_name, **data["tool_usage"][tool_name]}
        return {"tool": tool_name, "error": "No stats found"}
    
    # Return all stats
    return {
        "tools": data["tool_usage"],
        "total_tools_used": len(data["tool_usage"]),
        "most_used": max(data["tool_usage"].items(), key=lambda x: x[1]["total_calls"])[0] if data["tool_usage"] else None
    }


# ─── Self-Upgrade System ───────────────────────────────────────────────────

def log_upgrade(description: str, details: str = None):
    """Log an upgrade made to the agent."""
    data = _load_learn()
    
    data["upgrades"].append({
        "description": description,
        "details": details,
        "timestamp": datetime.now().isoformat()
    })
    data["upgrades"] = data["upgrades"][-50:]  # Keep last 50
    
    _save_learn(data)

def get_upgrade_history() -> List[Dict]:
    """Get upgrade history."""
    data = _load_learn()
    return data.get("upgrades", [])


# ─── Smart Retry Logic ─────────────────────────────────────────────────────

def should_retry(error_type: str, attempt: int, max_attempts: int = 3) -> Dict[str, Any]:
    """Determine if we should retry based on learned patterns."""
    fix_info = get_error_fix(error_type)
    
    if attempt >= max_attempts:
        return {
            "retry": False,
            "reason": f"Max attempts ({max_attempts}) reached",
            "suggestion": fix_info.get("last_fix", "No known fix")
        }
    
    if fix_info["found"]:
        return {
            "retry": True,
            "attempt": attempt + 1,
            "suggested_fix": fix_info["last_fix"],
            "confidence": "high" if fix_info["occurrences"] > 3 else "medium"
        }
    
    return {
        "retry": True,
        "attempt": attempt + 1,
        "suggested_fix": None,
        "confidence": "low"
    }


# ─── Learning Summary ──────────────────────────────────────────────────────

def get_learning_summary() -> str:
    """Get a summary of what the agent has learned."""
    data = _load_learn()
    
    patterns = data.get("patterns", {})
    errors = data.get("errors", {})
    tools = data.get("tool_usage", {})
    upgrades = data.get("upgrades", [])
    
    summary = []
    summary.append("=== Agent Learning Summary ===\n")
    
    # Patterns learned
    summary.append(f"Patterns Learned: {len(patterns)} task types")
    for task, info in patterns.items():
        success_rate = len(info["success"]) / info["count"] * 100 if info["count"] > 0 else 0
        summary.append(f"  - {task}: {info['count']} attempts, {success_rate:.0f}% success")
    
    # Errors encountered
    summary.append(f"\nErrors Encountered: {len(errors)} types")
    for err, info in errors.items():
        summary.append(f"  - {err}: {info['occurrences']} times, {len(info['fixes'])} fixes known")
    
    # Tool usage
    summary.append(f"\nTools Used: {len(tools)}")
    if tools:
        most_used = max(tools.items(), key=lambda x: x[1]["total_calls"])
        summary.append(f"  - Most used: {most_used[0]} ({most_used[1]['total_calls']} calls)")
    
    # Upgrades
    summary.append(f"\nUpgrades Made: {len(upgrades)}")
    if upgrades:
        summary.append(f"  - Latest: {upgrades[-1]['description']}")
    
    return "\n".join(summary)


# ─── Register Tools ─────────────────────────────────────────────────────────

def register_upgrade_tools(register_tool_func):
    """Register upgrade/learning tools."""
    
    register_tool_func(
        name="learn_pattern",
        description="Learn from a task pattern (success or failure).",
        parameters={"type": "object", "properties": {
            "task_type": {"type": "string"},
            "steps": {"type": "array", "items": {"type": "string"}},
            "success": {"type": "boolean"}
        }, "required": ["task_type", "steps", "success"]},
        handler=lambda task_type, steps, success: json.dumps(learn_pattern(task_type, steps, success) or {"status": "learned"})
    )
    
    register_tool_func(
        name="get_best_pattern",
        description="Get the best known pattern for a task type.",
        parameters={"type": "object", "properties": {
            "task_type": {"type": "string"}
        }, "required": ["task_type"]},
        handler=lambda task_type: json.dumps(get_best_pattern(task_type))
    )
    
    register_tool_func(
        name="learn_error",
        description="Learn from an error and its fix.",
        parameters={"type": "object", "properties": {
            "error_type": {"type": "string"},
            "error_msg": {"type": "string"},
            "fix_applied": {"type": "string"}
        }, "required": ["error_type", "error_msg"]},
        handler=lambda error_type, error_msg, fix_applied=None: json.dumps(learn_error(error_type, error_msg, fix_applied) or {"status": "learned"})
    )
    
    register_tool_func(
        name="get_error_fix",
        description="Get known fix for an error type.",
        parameters={"type": "object", "properties": {
            "error_type": {"type": "string"}
        }, "required": ["error_type"]},
        handler=lambda error_type: json.dumps(get_error_fix(error_type))
    )
    
    register_tool_func(
        name="track_tool_usage",
        description="Track tool usage statistics.",
        parameters={"type": "object", "properties": {
            "tool_name": {"type": "string"},
            "success": {"type": "boolean"},
            "duration_ms": {"type": "integer"}
        }, "required": ["tool_name", "success", "duration_ms"]},
        handler=lambda tool_name, success, duration_ms: json.dumps(track_tool_usage(tool_name, success, duration_ms) or {"status": "tracked"})
    )
    
    register_tool_func(
        name="get_tool_stats",
        description="Get tool usage statistics.",
        parameters={"type": "object", "properties": {
            "tool_name": {"type": "string"}
        }, "required": []},
        handler=lambda tool_name=None: json.dumps(get_tool_stats(tool_name))
    )
    
    register_tool_func(
        name="log_upgrade",
        description="Log an upgrade made to the agent.",
        parameters={"type": "object", "properties": {
            "description": {"type": "string"},
            "details": {"type": "string"}
        }, "required": ["description"]},
        handler=lambda description, details=None: json.dumps(log_upgrade(description, details) or {"status": "logged"})
    )
    
    register_tool_func(
        name="get_upgrade_history",
        description="Get upgrade history.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda: json.dumps(get_upgrade_history())
    )
    
    register_tool_func(
        name="get_learning_summary",
        description="Get a summary of what the agent has learned.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=lambda: json.dumps({"summary": get_learning_summary()})
    )
    
    return 9  # Number of tools registered
