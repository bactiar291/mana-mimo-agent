"""
skill_manager.py — Skill System (Hermes-inspired)
Load, manage, and execute skills.
"""
import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional
from datetime import datetime

# ─── Skill Storage ──────────────────────────────────────────────────────
SKILLS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "skills")
os.makedirs(SKILLS_DIR, exist_ok=True)


def _safe_skill_name(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", (name or "").strip())
    clean = clean.strip("._-")
    if not clean:
        raise ValueError("Skill name required")
    return clean[:80]

def skill_view(name: str) -> str:
    """View skill content."""
    try:
        name = _safe_skill_name(name)
        skill_file = os.path.join(SKILLS_DIR, f"{name}.md")
        if not os.path.exists(skill_file):
            return json.dumps({"success": False, "error": f"Skill '{name}' not found", "reason": "not_found"})
        
        with open(skill_file, "r") as f:
            content = f.read()
        
        return json.dumps({
            "success": True,
            "name": name,
            "content": content,
            "size": len(content)
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def skill_manage(action: str = "list", name: str = "", content: str = "") -> str:
    """Manage skills."""
    try:
        if action == "list":
            skills = []
            for f in os.listdir(SKILLS_DIR):
                if f.endswith(".md"):
                    skill_path = os.path.join(SKILLS_DIR, f)
                    with open(skill_path, "r") as file:
                        skill_content = file.read()
                    
                    # Extract name from frontmatter
                    name_match = re.search(r'name:\s*(.+)', skill_content)
                    desc_match = re.search(r'description:\s*(.+)', skill_content)
                    
                    skills.append({
                        "name": f.replace(".md", ""),
                        "display_name": name_match.group(1).strip() if name_match else f.replace(".md", ""),
                        "description": desc_match.group(1).strip() if desc_match else "",
                        "size": len(skill_content)
                    })
            
            return json.dumps({"success": True, "skills": skills, "count": len(skills)})
        
        elif action == "create":
            if not name or not content:
                return json.dumps({"success": False, "error": "Name and content required"})
            name = _safe_skill_name(name)
            skill_file = os.path.join(SKILLS_DIR, f"{name}.md")
            with open(skill_file, "w") as f:
                f.write(content)
            
            return json.dumps({"success": True, "name": name, "message": "Skill created"})
        
        elif action == "delete":
            name = _safe_skill_name(name)
            skill_file = os.path.join(SKILLS_DIR, f"{name}.md")
            if os.path.exists(skill_file):
                os.remove(skill_file)
                return json.dumps({"success": True, "name": name, "message": "Skill deleted"})
            else:
                return json.dumps({"success": False, "error": "Skill not found"})
        
        else:
            return json.dumps({"success": False, "error": "Invalid action"})
    
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def skill_install(url: str, name: str = "") -> str:
    """Install skill from URL."""
    try:
        if not url:
            return json.dumps({"success": False, "error": "URL required"})

        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https", "file"}:
            return json.dumps({"success": False, "error": "Only http, https, and file URLs are supported"})

        if not name:
            basename = os.path.basename(parsed.path).rsplit(".", 1)[0]
            name = basename or "downloaded_skill"
        name = _safe_skill_name(name)

        with urllib.request.urlopen(url, timeout=20) as response:
            content_bytes = response.read(1_000_001)
        if len(content_bytes) > 1_000_000:
            return json.dumps({"success": False, "error": "Skill file too large; max 1MB"})
        content = content_bytes.decode("utf-8")
        if not content.strip():
            return json.dumps({"success": False, "error": "Downloaded skill is empty"})

        skill_file = os.path.join(SKILLS_DIR, f"{name}.md")
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(content)

        return json.dumps({
            "success": True,
            "url": url,
            "name": name,
            "path": skill_file,
            "size": len(content),
            "message": "Skill installed"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def skill_auto_load(query: str = "") -> str:
    """Find relevant skills for a task."""
    try:
        skills = []
        for f in os.listdir(SKILLS_DIR):
            if f.endswith(".md"):
                skill_path = os.path.join(SKILLS_DIR, f)
                with open(skill_path, "r") as file:
                    content = file.read()
                
                # Simple relevance check
                if query and any(word in content.lower() for word in query.lower().split()):
                    skills.append({
                        "name": f.replace(".md", ""),
                        "relevance": "high"
                    })
                else:
                    skills.append({
                        "name": f.replace(".md", ""),
                        "relevance": "low"
                    })
        
        # Sort by relevance
        skills.sort(key=lambda x: 0 if x["relevance"] == "high" else 1)
        
        return json.dumps({"success": True, "skills": skills[:10], "count": len(skills)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_skill_manager_tools(register_tool):
    """Register skill manager tools."""
    register_tool(
        name="skill_view",
        description="View skill content",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name"}
            },
            "required": ["name"]
        },
        handler=lambda args: skill_view(args.get("name", ""))
    )
    
    register_tool(
        name="skill_manage",
        description="Manage skills (list, create, delete)",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: list, create, delete", "default": "list"},
                "name": {"type": "string", "description": "Skill name", "default": ""},
                "content": {"type": "string", "description": "Skill content", "default": ""}
            }
        },
        handler=lambda args: skill_manage(args.get("action", "list"), args.get("name", ""), args.get("content", ""))
    )
    
    register_tool(
        name="skill_install",
        description="Install skill from URL",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Skill URL"},
                "name": {"type": "string", "description": "Skill name", "default": ""}
            },
            "required": ["url"]
        },
        handler=lambda args: skill_install(args.get("url", ""), args.get("name", ""))
    )
    
    register_tool(
        name="skill_auto_load",
        description="Find relevant skills for a task",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Task query", "default": ""}
            }
        },
        handler=lambda args: skill_auto_load(args.get("query", ""))
    )
