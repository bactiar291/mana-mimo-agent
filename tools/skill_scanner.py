"""
skill_scanner.py — Skill Security Scanner (OpenClaw-inspired)
Scan skills for hidden instructions and security issues.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

DANGEROUS_PATTERNS = [
    r"ignore\s+previous\s+instructions",
    r"system\s*:\s*you\s+are",
    r"assistant\s*:\s*",
    r"<\|im_start\|>",
    r"<\|im_end\|>",
    r"\[INST\]",
    r"\[/INST\]",
    r"Human\s*:",
    r"Assistant\s*:",
    r"rm\s+-rf\s+/",
    r"sudo\s+rm",
    r"curl.*\|\s*sh",
    r"wget.*\|\s*bash",
    r"eval\s*\(",
    r"exec\s*\(",
    r"__import__",
    r"subprocess\.call",
    r"os\.system",
]

def skill_scan(skill_path: str = "", skill_content: str = "") -> str:
    """Scan a skill for security issues."""
    try:
        if skill_path and os.path.exists(skill_path):
            with open(skill_path, "r") as f:
                content = f.read()
        elif skill_content:
            content = skill_content
        else:
            return json.dumps({"success": False, "error": "Provide skill_path or skill_content"})
        
        issues = []
        score = 100
        
        for pattern in DANGEROUS_PATTERNS:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                issues.append({
                    "pattern": pattern,
                    "matches": len(matches),
                    "severity": "high" if "rm" in pattern or "eval" in pattern else "medium"
                })
                score -= 10 if "rm" in pattern or "eval" in pattern else 5
        
        # Check for encoded content
        if "base64" in content.lower():
            issues.append({
                "pattern": "base64 encoding detected",
                "matches": 1,
                "severity": "low"
            })
            score -= 5
        
        # Check for external URLs
        urls = re.findall(r'https?://[^\s<>"]+', content)
        if urls:
            issues.append({
                "pattern": "external URLs found",
                "matches": len(urls),
                "severity": "info",
                "urls": urls[:5]
            })
        
        return json.dumps({
            "success": True,
            "score": max(0, score),
            "issues": issues,
            "issue_count": len(issues),
            "safe": score >= 80,
            "recommendation": "Safe to use" if score >= 80 else "Review issues before using"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def skill_validate(skill_path: str) -> str:
    """Validate skill structure."""
    try:
        if not os.path.exists(skill_path):
            return json.dumps({"success": False, "error": "Skill file not found"})
        
        with open(skill_path, "r") as f:
            content = f.read()
        
        checks = {
            "has_frontmatter": content.startswith("---"),
            "has_name": "name:" in content[:500],
            "has_description": "description:" in content[:500],
            "has_content": len(content) > 100,
            "file_size": len(content)
        }
        
        return json.dumps({
            "success": True,
            "checks": checks,
            "valid": all(checks.values()),
            "message": "Skill is valid" if all(checks.values()) else "Skill has issues"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def skill_export(skill_path: str, output_path: str = "") -> str:
    """Export skill to JSON."""
    try:
        if not os.path.exists(skill_path):
            return json.dumps({"success": False, "error": "Skill file not found"})
        
        with open(skill_path, "r") as f:
            content = f.read()
        
        if not output_path:
            output_path = skill_path.replace(".md", ".json")
        
        export = {
            "path": skill_path,
            "content": content,
            "exported_at": datetime.now().isoformat(),
            "size": len(content)
        }
        
        with open(output_path, "w") as f:
            json.dump(export, f, indent=2)
        
        return json.dumps({"success": True, "exported": output_path})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def skill_import(json_path: str, output_dir: str = "") -> str:
    """Import skill from JSON."""
    try:
        if not os.path.exists(json_path):
            return json.dumps({"success": False, "error": "JSON file not found"})
        
        with open(json_path, "r") as f:
            data = json.load(f)
        
        if not output_dir:
            output_dir = os.path.dirname(json_path)
        
        output_path = os.path.join(output_dir, os.path.basename(data.get("path", "imported_skill.md")))
        
        with open(output_path, "w") as f:
            f.write(data.get("content", ""))
        
        return json.dumps({"success": True, "imported": output_path})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_skill_scanner_tools(register_tool):
    """Register skill scanner tools."""
    register_tool(
        name="skill_scan",
        description="Scan a skill for security issues",
        parameters={
            "type": "object",
            "properties": {
                "skill_path": {"type": "string", "description": "Path to skill file", "default": ""},
                "skill_content": {"type": "string", "description": "Skill content to scan", "default": ""}
            }
        },
        handler=lambda args: skill_scan(args.get("skill_path", ""), args.get("skill_content", ""))
    )
    
    register_tool(
        name="skill_validate",
        description="Validate skill structure",
        parameters={
            "type": "object",
            "properties": {
                "skill_path": {"type": "string", "description": "Path to skill file"}
            },
            "required": ["skill_path"]
        },
        handler=lambda args: skill_validate(args.get("skill_path", ""))
    )
    
    register_tool(
        name="skill_export",
        description="Export skill to JSON",
        parameters={
            "type": "object",
            "properties": {
                "skill_path": {"type": "string", "description": "Path to skill file"},
                "output_path": {"type": "string", "description": "Output JSON path", "default": ""}
            },
            "required": ["skill_path"]
        },
        handler=lambda args: skill_export(args.get("skill_path", ""), args.get("output_path", ""))
    )
    
    register_tool(
        name="skill_import",
        description="Import skill from JSON",
        parameters={
            "type": "object",
            "properties": {
                "json_path": {"type": "string", "description": "Path to JSON file"},
                "output_dir": {"type": "string", "description": "Output directory", "default": ""}
            },
            "required": ["json_path"]
        },
        handler=lambda args: skill_import(args.get("json_path", ""), args.get("output_dir", ""))
    )
