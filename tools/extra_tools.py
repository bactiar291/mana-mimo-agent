"""
extra_tools.py — Additional tools to match Hermes capabilities
Skills, Memory, Todo, Vision, Browser extras
"""
import json
import os
import re
import time
import subprocess
from typing import Any, Dict, List, Optional
from datetime import datetime


def _voice_enabled() -> bool:
    value = os.environ.get("MIMO_VOICE_ENABLED", "1").strip().lower()
    return value not in {"0", "false", "no", "off", "disabled"}

# ─── Skills System ──────────────────────────────────────────────────────────

SKILLS_DIR = os.path.expanduser("~/.agent/skills")

def _ensure_skills_dir():
    os.makedirs(SKILLS_DIR, exist_ok=True)

def skill_view(name: str) -> str:
    """View a skill's content."""
    _ensure_skills_dir()
    skill_path = os.path.join(SKILLS_DIR, f"{name}.md")
    if not os.path.exists(skill_path):
        return json.dumps({"success": False, "error": f"Skill '{name}' not found", "reason": "not_found"})
    with open(skill_path, 'r') as f:
        content = f.read()
    return json.dumps({"success": True, "name": name, "content": content[:5000]})

def skill_manage(action: str, name: str = None, content: str = None) -> str:
    """Manage skills: create, update, delete, list."""
    _ensure_skills_dir()
    
    if action == "list":
        skills = []
        for f in os.listdir(SKILLS_DIR):
            if f.endswith('.md'):
                skills.append(f[:-3])
        return json.dumps({"skills": skills, "count": len(skills)})
    
    if not name:
        return json.dumps({"error": "name required for this action"})
    
    skill_path = os.path.join(SKILLS_DIR, f"{name}.md")
    
    if action == "create":
        if os.path.exists(skill_path):
            return json.dumps({"error": f"Skill '{name}' already exists"})
        with open(skill_path, 'w') as f:
            f.write(content or f"# {name}\n\nSkill content here.")
        return json.dumps({"created": name})
    
    elif action == "update":
        with open(skill_path, 'w') as f:
            f.write(content or "")
        return json.dumps({"updated": name})
    
    elif action == "delete":
        if os.path.exists(skill_path):
            os.remove(skill_path)
            return json.dumps({"deleted": name})
        return json.dumps({"error": f"Skill '{name}' not found"})
    
    return json.dumps({"error": f"Unknown action: {action}"})

def skills_list() -> str:
    """List all available skills."""
    return skill_manage("list")


# ─── Memory Tool (wrapper for Memory class) ─────────────────────────────────

MEMORY_FILE = os.path.expanduser("~/.agent/memory.json")

def _load_memory() -> dict:
    os.makedirs(os.path.dirname(MEMORY_FILE), exist_ok=True)
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return {"facts": [], "preferences": {}, "notes": [], "updated": ""}

def _save_memory(data: dict):
    data["updated"] = datetime.now().isoformat()
    with open(MEMORY_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def memory_tool(action: str, key: str = None, value: str = None) -> str:
    """Persistent memory: add_fact, set_pref, add_note, get/list, clear."""
    data = _load_memory()
    
    if action in ("get", "list"):
        return json.dumps(data)
    
    elif action == "add_fact":
        if value and value not in data["facts"]:
            data["facts"].append(value)
            _save_memory(data)
        return json.dumps({"facts": data["facts"]})
    
    elif action == "set_pref":
        if key and value:
            data["preferences"][key] = value
            _save_memory(data)
        return json.dumps({"preferences": data["preferences"]})
    
    elif action == "add_note":
        if value:
            data["notes"].append({"text": value, "time": datetime.now().isoformat()})
            _save_memory(data)
        return json.dumps({"notes_count": len(data["notes"])})
    
    elif action == "clear":
        data = {"facts": [], "preferences": {}, "notes": [], "updated": ""}
        _save_memory(data)
        return json.dumps({"status": "cleared"})
    
    return json.dumps({"success": False, "error": f"Unknown action: {action}", "valid_actions": ["get", "list", "add_fact", "set_pref", "add_note", "clear"]})


# ─── Todo System ─────────────────────────────────────────────────────────────

TODO_FILE = os.path.expanduser("~/.agent/todo.json")

def _load_todo() -> list:
    os.makedirs(os.path.dirname(TODO_FILE), exist_ok=True)
    if os.path.exists(TODO_FILE):
        try:
            with open(TODO_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return []

def _save_todo(items: list):
    with open(TODO_FILE, 'w') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)

def todo_tool(action: str, item_id: str = None, content: str = None, status: str = None) -> str:
    """Todo list: add, update, list, clear."""
    items = _load_todo()
    
    if action == "list":
        return json.dumps({"items": items, "count": len(items)})
    
    elif action == "add":
        new_id = str(len(items) + 1)
        items.append({"id": new_id, "content": content, "status": "pending", "created": datetime.now().isoformat()})
        _save_todo(items)
        return json.dumps({"added": new_id, "content": content})
    
    elif action == "update":
        for item in items:
            if item["id"] == item_id:
                if content:
                    item["content"] = content
                if status:
                    item["status"] = status
                item["updated"] = datetime.now().isoformat()
                _save_todo(items)
                return json.dumps({"updated": item_id})
        return json.dumps({"error": f"Item {item_id} not found"})
    
    elif action == "clear":
        _save_todo([])
        return json.dumps({"status": "cleared"})
    
    return json.dumps({"error": f"Unknown action: {action}"})


# ─── Vision Tools ────────────────────────────────────────────────────────────

def vision_analyze(image_path: str, question: str = None) -> str:
    """Analyze an image using vision model or describe it."""
    if not os.path.exists(image_path):
        return json.dumps({"error": f"Image not found: {image_path}"})
    
    # Get image info
    import mimetypes
    mime = mimetypes.guess_type(image_path)[0]
    size = os.path.getsize(image_path)
    
    result = {
        "path": image_path,
        "mime": mime,
        "size_bytes": size,
        "size_mb": round(size / 1024 / 1024, 2)
    }
    
    # Try to use describe via terminal if available
    try:
        # Check if we can use file command
        import subprocess
        r = subprocess.run(["file", image_path], capture_output=True, text=True, timeout=5)
        result["file_info"] = r.stdout.strip()
    except:
        pass
    
    if question:
        result["question"] = question
        result["note"] = "Vision analysis requires external model. Image info provided instead."
    
    return json.dumps(result)

def video_analyze(video_path: str, question: str = None) -> str:
    """Analyze a video file."""
    if not os.path.exists(video_path):
        return json.dumps({"error": f"Video not found: {video_path}"})
    
    import mimetypes
    mime = mimetypes.guess_type(video_path)[0]
    size = os.path.getsize(video_path)
    
    result = {
        "path": video_path,
        "mime": mime,
        "size_bytes": size,
        "size_mb": round(size / 1024 / 1024, 2)
    }
    
    # Try ffprobe for video info
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", video_path],
            capture_output=True, text=True, timeout=10
        )
        if r.returncode == 0:
            result["video_info"] = json.loads(r.stdout)
    except:
        pass
    
    return json.dumps(result)


# ─── Text-to-Speech ──────────────────────────────────────────────────────────

def text_to_speech(text: str, output_path: str = None) -> str:
    """Convert text to speech using edge-tts."""
    if not _voice_enabled():
        return json.dumps({"success": False, "error": "Voice tools disabled by MIMO_VOICE_ENABLED=0"})
    if not text:
        return json.dumps({"success": False, "error": "Text required"})
    if not output_path:
        output_path = os.path.expanduser(f"~/agent_tts_{int(time.time())}.mp3")
    
    try:
        import edge_tts
        import asyncio
        
        async def generate():
            communicate = edge_tts.Communicate(text, "id-ID-ArdiNeural")
            await communicate.save(output_path)
        
        asyncio.run(generate())
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            size = os.path.getsize(output_path)
            return json.dumps({"success": True, "output": output_path, "size_bytes": size, "autoplay": False, "status": "ok"})
        else:
            return json.dumps({"success": False, "error": "TTS output file was not created"})
    except ImportError:
        return json.dumps({"success": False, "error": "edge-tts not installed. Run: pip install edge-tts"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


# ─── Browser Extras ─────────────────────────────────────────────────────────

def browser_press(key: str) -> str:
    """Press a keyboard key in the browser."""
    try:
        from lib import browser_engine
        if browser_engine.get_engine() == "playwright":
            page = browser_engine._get_playwright_browser()
            page.keyboard.press(key)
        else:
            tab = browser_engine._get_drission_browser()
            from DrissionPage.common import Keys
            key_map = {
                "Enter": Keys.ENTER, "Tab": Keys.TAB, "Escape": Keys.ESCAPE,
                "ArrowDown": Keys.ARROW_DOWN, "ArrowUp": Keys.ARROW_UP,
                "ArrowLeft": Keys.ARROW_LEFT, "ArrowRight": Keys.ARROW_RIGHT,
            }
            mapped = key_map.get(key, key)
            tab.actions.key_down(mapped).key_up(mapped).perform()
        return json.dumps({"pressed": key, "status": "ok"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def browser_scroll(direction: str = "down", amount: int = 3) -> str:
    """Scroll the browser page."""
    try:
        from lib import browser_engine
        if browser_engine.get_engine() == "playwright":
            page = browser_engine._get_playwright_browser()
            delta = 300 * amount if direction == "down" else -300 * amount
            page.mouse.wheel(0, delta)
        else:
            tab = browser_engine._get_drission_browser()
            delta = 300 * amount if direction == "down" else -300 * amount
            tab.scroll(delta)
        time.sleep(0.5)
        return json.dumps({"scrolled": direction, "amount": amount, "status": "ok"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def browser_snapshot() -> str:
    """Get a text snapshot of the current page (accessibility tree)."""
    try:
        from lib import browser_engine
        if browser_engine.get_engine() == "playwright":
            page = browser_engine._get_playwright_browser()
            # Get page content as text
            content = page.evaluate("""
                () => {
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        null,
                        false
                    );
                    let text = '';
                    let node;
                    while(node = walker.nextNode()) {
                        const t = node.textContent.trim();
                        if(t) text += t + '\\n';
                    }
                    return text.substring(0, 10000);
                }
            """)
        else:
            tab = browser_engine._get_drission_browser()
            content = tab.html[:5000]
            # Clean HTML
            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
            content = re.sub(r'<[^>]+>', ' ', content)
            content = re.sub(r'\s+', ' ', content).strip()
        
        return json.dumps({"snapshot": content[:5000], "length": len(content)})
    except Exception as e:
        return json.dumps({"error": str(e)})

def browser_console(expression: str) -> str:
    """Execute JavaScript in browser console (alias for browser_evaluate)."""
    try:
        from lib import browser_engine
        return browser_engine.browser_evaluate(expression)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─── Register All Extra Tools ───────────────────────────────────────────────

def register_extra_tools(register_tool_func):
    """Register all extra tools with the main tool registry."""
    count = 0
    
    # Skills
    register_tool_func(
        name="skill_view",
        description="View a skill's content by name.",
        parameters={"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        handler=skill_view
    )
    count += 1
    
    register_tool_func(
        name="skill_manage",
        description="Manage skills: create, update, delete, list.",
        parameters={"type": "object", "properties": {
            "action": {"type": "string", "enum": ["create", "update", "delete", "list"]},
            "name": {"type": "string"},
            "content": {"type": "string"}
        }, "required": ["action"]},
        handler=skill_manage
    )
    count += 1
    
    register_tool_func(
        name="skills_list",
        description="List all available skills.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=skills_list
    )
    count += 1
    
    # Memory
    register_tool_func(
        name="memory",
        description="Persistent memory: add_fact, set_pref, add_note, get/list, clear.",
        parameters={"type": "object", "properties": {
            "action": {"type": "string", "enum": ["get", "list", "add_fact", "set_pref", "add_note", "clear"]},
            "key": {"type": "string"},
            "value": {"type": "string"}
        }, "required": ["action"]},
        handler=memory_tool
    )
    count += 1
    
    # Todo
    register_tool_func(
        name="todo",
        description="Todo list: add, update, list, clear tasks.",
        parameters={"type": "object", "properties": {
            "action": {"type": "string", "enum": ["add", "update", "list", "clear"]},
            "item_id": {"type": "string"},
            "content": {"type": "string"},
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "cancelled"]}
        }, "required": ["action"]},
        handler=todo_tool
    )
    count += 1
    
    # Vision
    register_tool_func(
        name="vision_analyze",
        description="Analyze an image file (get info, dimensions, etc).",
        parameters={"type": "object", "properties": {
            "image_path": {"type": "string"},
            "question": {"type": "string"}
        }, "required": ["image_path"]},
        handler=vision_analyze
    )
    count += 1
    
    register_tool_func(
        name="video_analyze",
        description="Analyze a video file (get info, duration, etc).",
        parameters={"type": "object", "properties": {
            "video_path": {"type": "string"},
            "question": {"type": "string"}
        }, "required": ["video_path"]},
        handler=video_analyze
    )
    count += 1
    
    # TTS
    if _voice_enabled():
        register_tool_func(
            name="text_to_speech",
            description="Convert text to speech audio file.",
            parameters={"type": "object", "properties": {
                "text": {"type": "string"},
                "output_path": {"type": "string"}
            }, "required": ["text"]},
            handler=text_to_speech
        )
        count += 1
    
    # Browser extras
    register_tool_func(
        name="browser_press",
        description="Press a keyboard key in the browser (Enter, Tab, Escape, Arrow keys).",
        parameters={"type": "object", "properties": {
            "key": {"type": "string"}
        }, "required": ["key"]},
        handler=browser_press
    )
    count += 1
    
    register_tool_func(
        name="browser_scroll",
        description="Scroll the browser page up or down.",
        parameters={"type": "object", "properties": {
            "direction": {"type": "string", "enum": ["up", "down"]},
            "amount": {"type": "integer"}
        }, "required": ["direction"]},
        handler=browser_scroll
    )
    count += 1
    
    register_tool_func(
        name="browser_snapshot",
        description="Get a text snapshot of the current page content.",
        parameters={"type": "object", "properties": {}, "required": []},
        handler=browser_snapshot
    )
    count += 1
    
    register_tool_func(
        name="browser_console",
        description="Execute JavaScript in browser console.",
        parameters={"type": "object", "properties": {
            "expression": {"type": "string"}
        }, "required": ["expression"]},
        handler=browser_console
    )
    count += 1
    
    return count
