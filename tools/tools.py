#!/usr/bin/env python3
"""
tools.py — Tool registry and implementations for MiMo Agent.
Provides a broad agentic toolkit for web, files, code, git, system, data, and process work.
"""
import csv
import difflib
import fnmatch
import glob
import hashlib
import inspect
import json
import mimetypes
import os
import platform
import re
import shutil
import signal
import sqlite3
import subprocess
import tarfile
import time
import urllib.parse
import zipfile
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

# Import browser engine
browser_engine = None
try:
    from lib import browser_engine
    HAS_BROWSER_ENGINE = True
except ImportError:
    try:
        import browser_engine
        HAS_BROWSER_ENGINE = True
    except ImportError:
        HAS_BROWSER_ENGINE = False

# Import search engine
try:
    from lib import search_engine as _search_engine
    HAS_SEARCH_ENGINE = True
except ImportError:
    try:
        import search_engine as _search_engine
        HAS_SEARCH_ENGINE = True
    except ImportError:
        HAS_SEARCH_ENGINE = False

# Import extra tools (skills, memory, todo, vision, tts, browser extras)
try:
    from tools.extra_tools import register_extra_tools
    HAS_EXTRA_TOOLS = True
except ImportError:
    try:
        from extra_tools import register_extra_tools
        HAS_EXTRA_TOOLS = True
    except ImportError:
        HAS_EXTRA_TOOLS = False

# Import upgrade/learning system
try:
    from lib.upgrade import register_upgrade_tools
    HAS_UPGRADE_TOOLS = True
except ImportError:
    HAS_UPGRADE_TOOLS = False

# Import security approval system
try:
    from tools.security import request_command_approval, request_path_approval, check_command_safety, check_path_safety
    HAS_SECURITY = True
except ImportError:
    try:
        from security import request_command_approval, request_path_approval, check_command_safety, check_path_safety
        HAS_SECURITY = True
    except ImportError:
        HAS_SECURITY = False


# ─── Tool Registry ───────────────────────────────────────────────────────────

TOOLS: Dict[str, Dict[str, Any]] = {}


def register_tool(
    name: str,
    description: str,
    parameters: Dict[str, Any],
    handler: Callable[..., str],
    requires_env: Optional[List[str]] = None,
):
    """Register a tool."""
    TOOLS[name] = {
        "name": name,
        "description": description,
        "parameters": parameters,
        "handler": handler,
        "requires_env": requires_env or [],
    }


def get_tools_schema() -> List[Dict[str, Any]]:
    """Get OpenAI-compatible tool schemas."""
    schemas = []
    for name, tool in TOOLS.items():
        # Check requirements
        if tool["requires_env"]:
            missing = [e for e in tool["requires_env"] if not os.environ.get(e)]
            if missing:
                continue
        schemas.append({
            "type": "function",
            "function": {
                "name": name,
                "description": tool["description"],
                "parameters": tool["parameters"],
            }
        })
    return schemas


def call_tool(name: str, args: Dict[str, Any]) -> str:
    """Execute a tool by name."""
    if name not in TOOLS:
        return json.dumps({"error": f"Tool '{name}' not found"})
    try:
        handler = TOOLS[name]["handler"]
        call_args = args or {}
        try:
            signature = inspect.signature(handler)
            params = list(signature.parameters.values())
            has_var_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in params)
            args_style_handler = (
                len(params) == 1
                and params[0].name == "args"
                and params[0].kind in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
                and not has_var_kwargs
            )
        except (TypeError, ValueError):
            args_style_handler = False

        if args_style_handler:
            result = handler(call_args)
        else:
            result = handler(**call_args)
        return result if isinstance(result, str) else json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _error(message: str) -> str:
    return _json({"error": message})


def _expand(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path or "."))


def _truncate(text: str, limit: int = 10000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... (truncated)"


def _run(command: List[str], cwd: Optional[str] = None, timeout: int = 30, limit: int = 12000) -> Dict[str, Any]:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=_expand(cwd) if cwd else None,
    )
    output = result.stdout
    if result.stderr:
        output += "\n" + result.stderr if output else result.stderr
    return {
        "command": command,
        "exit_code": result.returncode,
        "output": _truncate(output, limit),
    }


def _coerce_json(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        return json.loads(value)
    return value


# ─── Web Search ──────────────────────────────────────────────────────────────

def _web_search(query: str, limit: int = 5) -> str:
    """Search the web using DuckDuckGo (free) with SearXNG fallback."""
    try:
        if HAS_SEARCH_ENGINE:
            result = _search_engine.web_search(query, limit)
            return json.dumps(result)
        else:
            # Fallback to direct DuckDuckGo
            import requests
            url = "https://html.duckduckgo.com/html/"
            resp = requests.post(url, data={"q": query}, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            results = []
            import re
            links = re.findall(r'<a rel="nofollow" class="result__a" href="([^"]+)">([^<]+)</a>', resp.text)
            snippets = re.findall(r'<a class="result__snippet"[^>]*>([^<]+)</a>', resp.text)
            for i, (url, title) in enumerate(links[:limit]):
                snippet = snippets[i] if i < len(snippets) else ""
                results.append({
                    "title": title.strip(),
                    "url": url.strip(),
                    "description": snippet.strip(),
                })
            return json.dumps({"results": results, "engine": "duckduckgo"})
    except Exception as e:
        return json.dumps({"error": str(e)})


register_tool(
    name="web_search",
    description="Search the web for information. Returns search results with titles, URLs, and descriptions.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "description": "Max results (default 5)", "default": 5},
        },
        "required": ["query"],
    },
    handler=_web_search,
)


def _search_engine_set(engine: str, api_key: str = None, instance: str = None) -> str:
    """Switch search engine."""
    try:
        if HAS_SEARCH_ENGINE:
            result = _search_engine.set_search_engine(engine, api_key, instance)
            return json.dumps({"engine": result, "status": "switched"})
        return json.dumps({"error": "search_engine module not available"})
    except Exception as e:
        return json.dumps({"error": str(e)})

def _search_engine_status() -> str:
    """Get search engine status."""
    try:
        if HAS_SEARCH_ENGINE:
            status = _search_engine.get_search_status()
            return json.dumps(status)
        return json.dumps({"engine": "duckduckgo (basic)", "status": "search_engine module not available"})
    except Exception as e:
        return json.dumps({"error": str(e)})


register_tool(
    name="search_engine_set",
    description="Switch search engine. Options: duckduckgo (free, default), searxng (free, self-hosted), brave (needs API key).",
    parameters={
        "type": "object",
        "properties": {
            "engine": {"type": "string", "description": "Engine: duckduckgo, searxng, or brave"},
            "api_key": {"type": "string", "description": "Brave API key (only for brave engine)"},
            "instance": {"type": "string", "description": "SearXNG instance URL (only for searxng)"},
        },
        "required": ["engine"],
    },
    handler=_search_engine_set,
)

register_tool(
    name="search_engine_status",
    description="Get current search engine status and available engines.",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_search_engine_status,
)


# ─── Web Extract ─────────────────────────────────────────────────────────────

def _web_extract(url: str, max_chars: int = 8000) -> str:
    """Extract content from a URL with anti-bot bypass."""
    import json as _json
    try:
        import requests
        
        # Better headers to bypass basic bot detection
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }
        
        session = requests.Session()
        resp = session.get(url, headers=headers, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        
        text = resp.text
        
        # Try to extract JSON-LD or meta data first (for structured sites)
        json_ld = re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', text, re.DOTALL)
        meta_data = {}
        for match in json_ld:
            try:
                data = _json.loads(match)
                if isinstance(data, dict):
                    meta_data.update(data)
            except Exception:
                pass
        
        # Remove scripts, styles, and HTML tags
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<nav[^>]*>.*?</nav>', '', text, flags=re.DOTALL)
        text = re.sub(r'<footer[^>]*>.*?</footer>', '', text, flags=re.DOTALL)
        text = re.sub(r'<header[^>]*>.*?</header>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # If we have structured data, prepend it
        result = text
        if meta_data:
            structured = _json.dumps(meta_data, indent=2)[:1000]
            result = f"[Structured Data]\n{structured}\n\n[Page Content]\n{text}"
        
        # Limit length
        if len(result) > max_chars:
            result = result[:max_chars] + "..."
        
        return _json.dumps({"url": url, "content": result, "status": resp.status_code})
    except Exception as e:
        # For 403/401, try alternative approach with curl
        if "403" in str(e) or "401" in str(e) or "Forbidden" in str(e):
            try:
                import subprocess
                result = subprocess.run(
                    ["curl", "-s", "-L", "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", 
                     "-H", "Accept: text/html", url],
                    capture_output=True, text=True, timeout=15
                )
                if result.returncode == 0 and result.stdout:
                    text = result.stdout
                    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                    text = re.sub(r'<[^>]+>', ' ', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    if len(text) > max_chars:
                        text = text[:max_chars] + "..."
                    return _json.dumps({"url": url, "content": text, "method": "curl_fallback"})
            except Exception:
                pass
        return _json.dumps({"error": str(e)})


register_tool(
    name="web_extract",
    description="Extract text content from a URL. Returns cleaned page text.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to extract content from"},
            "max_chars": {"type": "integer", "description": "Max characters to return (default 8000)", "default": 8000},
        },
        "required": ["url"],
    },
    handler=_web_extract,
)


# ─── Read File ───────────────────────────────────────────────────────────────

def _read_file(path: str, offset: int = 1, limit: int = 500) -> str:
    """Read a file with line numbers."""
    try:
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return json.dumps({"error": f"File not found: {path}"})
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        start = max(0, offset - 1)
        end = min(total, start + limit)
        content = ""
        for i in range(start, end):
            content += f"{i+1}|{lines[i]}"
        return json.dumps({"content": content, "total_lines": total, "path": path})
    except Exception as e:
        return json.dumps({"error": str(e)})


register_tool(
    name="read_file",
    description="Read a text file with line numbers. Use offset and limit for large files.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to read"},
            "offset": {"type": "integer", "description": "Start line (1-indexed, default 1)", "default": 1},
            "limit": {"type": "integer", "description": "Max lines to read (default 500)", "default": 500},
        },
        "required": ["path"],
    },
    handler=_read_file,
)


# ─── Write File ──────────────────────────────────────────────────────────────

def _write_file(path: str, content: str) -> str:
    """Write content to a file (overwrites)."""
    try:
        path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return json.dumps({"success": True, "path": path, "bytes": len(content.encode())})
    except Exception as e:
        return json.dumps({"error": str(e)})


register_tool(
    name="write_file",
    description="Write content to a file. Creates parent directories. OVERWRITES existing content.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    },
    handler=_write_file,
)


# ─── Patch File ──────────────────────────────────────────────────────────────

def _patch_file(path: str, old_string: str, new_string: str) -> str:
    """Find and replace in a file."""
    try:
        path = os.path.expanduser(path)
        if not os.path.exists(path):
            return json.dumps({"error": f"File not found: {path}"})
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if old_string not in content:
            return json.dumps({"error": "old_string not found in file"})
        new_content = content.replace(old_string, new_string, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return json.dumps({"success": True, "path": path})
    except Exception as e:
        return json.dumps({"error": str(e)})


register_tool(
    name="patch_file",
    description="Find and replace a string in a file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "old_string": {"type": "string", "description": "String to find"},
            "new_string": {"type": "string", "description": "Replacement string"},
        },
        "required": ["path", "old_string", "new_string"],
    },
    handler=_patch_file,
)


# ─── Search Files ────────────────────────────────────────────────────────────

def _search_files(pattern: str, path: str = ".", target: str = "content", limit: int = 20) -> str:
    """Search file contents or find files by name."""
    try:
        path = os.path.expanduser(path)
        results = []
        if target == "files":
            # Find files by name pattern. Accept shell globs (*.py) and regex.
            glob_mode = any(ch in pattern for ch in "*?[]")
            for root, dirs, files in os.walk(path):
                for f in files:
                    matched = fnmatch.fnmatch(f.lower(), pattern.lower()) if glob_mode else re.search(pattern, f, re.IGNORECASE)
                    if matched:
                        results.append(os.path.join(root, f))
                        if len(results) >= limit:
                            break
                if len(results) >= limit:
                    break
        else:
            # Search file contents
            for root, dirs, files in os.walk(path):
                # Skip hidden dirs
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for f in files:
                    if not f.endswith(('.py', '.txt', '.md', '.json', '.yaml', '.yml', '.js', '.ts')):
                        continue
                    fpath = os.path.join(root, f)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                            for i, line in enumerate(fh, 1):
                                if re.search(pattern, line, re.IGNORECASE):
                                    results.append({"file": fpath, "line": i, "content": line.strip()})
                                    if len(results) >= limit:
                                        break
                    except Exception:
                        continue
                if len(results) >= limit:
                    break
        return json.dumps({"results": results, "count": len(results)})
    except Exception as e:
        return json.dumps({"error": str(e)})


register_tool(
    name="search_files",
    description="Search file contents (grep) or find files by name pattern (glob).",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search"},
            "path": {"type": "string", "description": "Directory to search in (default: current dir)", "default": "."},
            "target": {"type": "string", "enum": ["content", "files"], "description": "Search mode", "default": "content"},
            "limit": {"type": "integer", "description": "Max results", "default": 20},
        },
        "required": ["pattern"],
    },
    handler=_search_files,
)


# ─── Terminal ────────────────────────────────────────────────────────────────

def _terminal(command: str, timeout: int = 30, workdir: str = None) -> str:
    """Execute a shell command with security approval."""
    try:
        # Security check
        if HAS_SECURITY:
            check = check_command_safety(command)
            if not check.get("safe", True):
                # Request approval
                if not request_command_approval(command):
                    return json.dumps({"error": "Command denied by user", "command": command})
        
        cwd = workdir or os.getcwd()
        result = subprocess.run(
            ["bash", "-lc", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd or os.getcwd(),
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr if output else result.stderr
        # Limit output
        if len(output) > 10000:
            output = output[:10000] + "\n... (truncated)"
        return json.dumps({
            "output": output,
            "exit_code": result.returncode,
            "command": command,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Command timed out after {timeout}s"})
    except Exception as e:
        return json.dumps({"error": str(e)})


register_tool(
    name="terminal",
    description="Execute a shell command and return output. Use for builds, installs, git, network, etc.",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "timeout": {"type": "integer", "description": "Max seconds (default 30)", "default": 30},
            "workdir": {"type": "string", "description": "Working directory (optional)"},
        },
        "required": ["command"],
    },
    handler=_terminal,
)


# ─── List Directory ──────────────────────────────────────────────────────────

def _list_directory(path: str = ".", show_hidden: bool = False) -> str:
    """List files and directories."""
    try:
        path = os.path.expanduser(path)
        if not os.path.isdir(path):
            return json.dumps({"error": f"Not a directory: {path}"})
        entries = []
        for entry in sorted(os.listdir(path)):
            if not show_hidden and entry.startswith('.'):
                continue
            full = os.path.join(path, entry)
            entries.append({
                "name": entry,
                "type": "dir" if os.path.isdir(full) else "file",
                "size": os.path.getsize(full) if os.path.isfile(full) else None,
            })
        return json.dumps({"path": path, "entries": entries})
    except Exception as e:
        return json.dumps({"error": str(e)})


register_tool(
    name="list_directory",
    description="List files and directories in a path.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path (default: current dir)", "default": "."},
            "show_hidden": {"type": "boolean", "description": "Show hidden files", "default": False},
        },
        "required": [],
    },
    handler=_list_directory,
)


# ─── Python Execute ─────────────────────────────────────────────────────────

def _execute_python(code: str, timeout: int = 30) -> str:
    """Execute Python code and return output."""
    try:
        result = subprocess.run(
            ["python3", "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr if output else result.stderr
        if len(output) > 10000:
            output = output[:10000] + "\n... (truncated)"
        return json.dumps({"output": output, "exit_code": result.returncode})
    except subprocess.TimeoutExpired:
        return json.dumps({"error": f"Code timed out after {timeout}s"})
    except Exception as e:
        return json.dumps({"error": str(e)})


register_tool(
    name="execute_python",
    description="Execute Python code and return output. Use for data processing, calculations, etc.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute"},
            "timeout": {"type": "integer", "description": "Max seconds (default 30)", "default": 30},
        },
        "required": ["code"],
    },
    handler=_execute_python,
)


# ─── Expanded Workspace Tools ────────────────────────────────────────────────

def _file_info(path: str, hash_file: bool = False) -> str:
    """Return file or directory metadata."""
    try:
        full_path = _expand(path)
        if not os.path.exists(full_path):
            return _error(f"Path not found: {full_path}")
        stat_result = os.stat(full_path)
        data = {
            "path": full_path,
            "exists": True,
            "type": "directory" if os.path.isdir(full_path) else "file",
            "size": stat_result.st_size,
            "modified": datetime.fromtimestamp(stat_result.st_mtime).isoformat(),
            "mode": oct(stat_result.st_mode),
            "mime": mimetypes.guess_type(full_path)[0],
        }
        if hash_file and os.path.isfile(full_path):
            digest = hashlib.sha256()
            with open(full_path, "rb") as file_handle:
                for block in iter(lambda: file_handle.read(1024 * 1024), b""):
                    digest.update(block)
            data["sha256"] = digest.hexdigest()
        return _json(data)
    except Exception as error:
        return _error(str(error))


register_tool(
    name="file_info",
    description="Get metadata for a file or directory, optionally including sha256 for files.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File or directory path"},
            "hash_file": {"type": "boolean", "description": "Calculate sha256 for files", "default": False},
        },
        "required": ["path"],
    },
    handler=_file_info,
)


def _append_file(path: str, content: str, newline: bool = False) -> str:
    """Append text to a file."""
    try:
        full_path = _expand(path)
        os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
        text = content + ("\n" if newline and not content.endswith("\n") else "")
        with open(full_path, "a", encoding="utf-8") as file_handle:
            file_handle.write(text)
        return _json({"success": True, "path": full_path, "bytes": len(text.encode("utf-8"))})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="append_file",
    description="Append text to a file. Creates the file and parent directories if needed.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Text to append"},
            "newline": {"type": "boolean", "description": "Append a trailing newline", "default": False},
        },
        "required": ["path", "content"],
    },
    handler=_append_file,
)


def _create_directory(path: str) -> str:
    """Create a directory tree."""
    try:
        full_path = _expand(path)
        os.makedirs(full_path, exist_ok=True)
        return _json({"success": True, "path": full_path})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="create_directory",
    description="Create a directory and missing parents.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Directory path"}},
        "required": ["path"],
    },
    handler=_create_directory,
)


def _copy_path(source: str, destination: str, overwrite: bool = False) -> str:
    """Copy a file or directory."""
    try:
        source_path = _expand(source)
        destination_path = _expand(destination)
        if not os.path.exists(source_path):
            return _error(f"Source not found: {source_path}")
        if os.path.exists(destination_path) and not overwrite:
            return _error(f"Destination exists: {destination_path}")
        os.makedirs(os.path.dirname(destination_path) or ".", exist_ok=True)
        if os.path.isdir(source_path):
            if os.path.exists(destination_path):
                shutil.rmtree(destination_path)
            shutil.copytree(source_path, destination_path)
        else:
            shutil.copy2(source_path, destination_path)
        return _json({"success": True, "source": source_path, "destination": destination_path})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="copy_path",
    description="Copy a file or directory to a destination.",
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Source path"},
            "destination": {"type": "string", "description": "Destination path"},
            "overwrite": {"type": "boolean", "description": "Overwrite destination", "default": False},
        },
        "required": ["source", "destination"],
    },
    handler=_copy_path,
)


def _move_path(source: str, destination: str, overwrite: bool = False) -> str:
    """Move a file or directory."""
    try:
        source_path = _expand(source)
        destination_path = _expand(destination)
        if not os.path.exists(source_path):
            return _error(f"Source not found: {source_path}")
        if os.path.exists(destination_path):
            if not overwrite:
                return _error(f"Destination exists: {destination_path}")
            if os.path.isdir(destination_path):
                shutil.rmtree(destination_path)
            else:
                os.remove(destination_path)
        os.makedirs(os.path.dirname(destination_path) or ".", exist_ok=True)
        shutil.move(source_path, destination_path)
        return _json({"success": True, "source": source_path, "destination": destination_path})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="move_path",
    description="Move or rename a file or directory.",
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Source path"},
            "destination": {"type": "string", "description": "Destination path"},
            "overwrite": {"type": "boolean", "description": "Overwrite destination", "default": False},
        },
        "required": ["source", "destination"],
    },
    handler=_move_path,
)


def _move_to_trash(path: str) -> str:
    """Move a path into ~/.mimo_trash instead of deleting it."""
    try:
        full_path = _expand(path)
        if not os.path.exists(full_path):
            return _error(f"Path not found: {full_path}")
        trash_root = _expand("~/.mimo_trash")
        os.makedirs(trash_root, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = os.path.basename(full_path.rstrip(os.sep)) or "root"
        trash_path = os.path.join(trash_root, f"{stamp}_{time.time_ns()}_{name}")
        shutil.move(full_path, trash_path)
        return _json({"success": True, "path": full_path, "trash_path": trash_path})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="move_to_trash",
    description="Safely remove a file or directory by moving it to ~/.mimo_trash.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Path to move to trash"}},
        "required": ["path"],
    },
    handler=_move_to_trash,
)


def _find_files(pattern: str, path: str = ".", mode: str = "glob", limit: int = 100, show_hidden: bool = False) -> str:
    """Find files by glob, fnmatch, or regex name pattern."""
    try:
        base_path = _expand(path)
        results = []
        if mode == "glob":
            search_pattern = pattern if os.path.isabs(pattern) else os.path.join(base_path, pattern)
            matches = glob.glob(search_pattern, recursive=True)
            for match_path in matches:
                basename = os.path.basename(match_path)
                if not show_hidden and basename.startswith("."):
                    continue
                results.append(match_path)
                if len(results) >= limit:
                    break
        else:
            compiled = re.compile(pattern, re.IGNORECASE) if mode == "regex" else None
            for root, dirs, files in os.walk(base_path):
                if not show_hidden:
                    dirs[:] = [directory for directory in dirs if not directory.startswith(".")]
                    files = [filename for filename in files if not filename.startswith(".")]
                for filename in files:
                    matched = compiled.search(filename) if compiled else fnmatch.fnmatch(filename, pattern)
                    if matched:
                        results.append(os.path.join(root, filename))
                        if len(results) >= limit:
                            return _json({"results": results, "count": len(results)})
        return _json({"results": results, "count": len(results)})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="find_files",
    description="Find files by glob, fnmatch, or regex filename pattern.",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Glob, fnmatch, or regex pattern"},
            "path": {"type": "string", "description": "Base directory", "default": "."},
            "mode": {"type": "string", "enum": ["glob", "fnmatch", "regex"], "description": "Search mode", "default": "glob"},
            "limit": {"type": "integer", "description": "Max results", "default": 100},
            "show_hidden": {"type": "boolean", "description": "Include hidden files/directories", "default": False},
        },
        "required": ["pattern"],
    },
    handler=_find_files,
)


def _list_tree(path: str = ".", max_depth: int = 3, show_hidden: bool = False, limit: int = 250) -> str:
    """Return a compact directory tree."""
    try:
        base_path = _expand(path)
        if not os.path.isdir(base_path):
            return _error(f"Not a directory: {base_path}")
        lines = [base_path + os.sep]
        count = 0

        def walk(current_path: str, prefix: str, depth: int):
            nonlocal count
            if depth > max_depth or count >= limit:
                return
            entries = sorted(os.listdir(current_path))
            if not show_hidden:
                entries = [entry for entry in entries if not entry.startswith(".")]
            for index, entry in enumerate(entries):
                if count >= limit:
                    return
                full_path = os.path.join(current_path, entry)
                connector = "└── " if index == len(entries) - 1 else "├── "
                suffix = "/" if os.path.isdir(full_path) else ""
                lines.append(f"{prefix}{connector}{entry}{suffix}")
                count += 1
                if os.path.isdir(full_path):
                    extension = "    " if index == len(entries) - 1 else "│   "
                    walk(full_path, prefix + extension, depth + 1)

        walk(base_path, "", 1)
        if count >= limit:
            lines.append("... (truncated)")
        return _json({"path": base_path, "tree": "\n".join(lines), "count": count})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="list_tree",
    description="Return a compact directory tree with configurable depth.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path", "default": "."},
            "max_depth": {"type": "integer", "description": "Maximum tree depth", "default": 3},
            "show_hidden": {"type": "boolean", "description": "Include hidden files", "default": False},
            "limit": {"type": "integer", "description": "Max entries", "default": 250},
        },
        "required": [],
    },
    handler=_list_tree,
)


def _replace_in_file(path: str, pattern: str, replacement: str, regex: bool = False, max_replacements: int = 0) -> str:
    """Replace text in a file using plain text or regex."""
    try:
        full_path = _expand(path)
        if not os.path.isfile(full_path):
            return _error(f"File not found: {full_path}")
        with open(full_path, "r", encoding="utf-8", errors="replace") as file_handle:
            content = file_handle.read()
        if regex:
            new_content, replacements = re.subn(pattern, replacement, content, count=max_replacements)
        else:
            replacements = content.count(pattern) if max_replacements == 0 else min(content.count(pattern), max_replacements)
            new_content = content.replace(pattern, replacement, max_replacements if max_replacements else -1)
        if replacements == 0:
            return _error("pattern not found")
        with open(full_path, "w", encoding="utf-8") as file_handle:
            file_handle.write(new_content)
        return _json({"success": True, "path": full_path, "replacements": replacements})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="replace_in_file",
    description="Replace plain text or regex matches in a file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "pattern": {"type": "string", "description": "Text or regex pattern"},
            "replacement": {"type": "string", "description": "Replacement text"},
            "regex": {"type": "boolean", "description": "Treat pattern as regex", "default": False},
            "max_replacements": {"type": "integer", "description": "0 means replace all", "default": 0},
        },
        "required": ["path", "pattern", "replacement"],
    },
    handler=_replace_in_file,
)


def _text_diff(old_path: str, new_path: Optional[str] = None, new_content: Optional[str] = None, context: int = 3) -> str:
    """Generate a unified diff between files or file and provided content."""
    try:
        old_full_path = _expand(old_path)
        if not os.path.isfile(old_full_path):
            return _error(f"File not found: {old_full_path}")
        with open(old_full_path, "r", encoding="utf-8", errors="replace") as file_handle:
            old_lines = file_handle.readlines()
        if new_content is not None:
            new_lines = new_content.splitlines(True)
            label = "<new_content>"
        elif new_path:
            new_full_path = _expand(new_path)
            with open(new_full_path, "r", encoding="utf-8", errors="replace") as file_handle:
                new_lines = file_handle.readlines()
            label = new_full_path
        else:
            return _error("Provide new_path or new_content")
        diff = "".join(difflib.unified_diff(old_lines, new_lines, fromfile=old_full_path, tofile=label, n=context))
        return _json({"diff": _truncate(diff, 20000)})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="text_diff",
    description="Create a unified diff between two files or a file and proposed content.",
    parameters={
        "type": "object",
        "properties": {
            "old_path": {"type": "string", "description": "Original file path"},
            "new_path": {"type": "string", "description": "New file path"},
            "new_content": {"type": "string", "description": "New content to compare"},
            "context": {"type": "integer", "description": "Diff context lines", "default": 3},
        },
        "required": ["old_path"],
    },
    handler=_text_diff,
)


def _code_outline(path: str, limit: int = 200) -> str:
    """Extract lightweight function/class/signature outline."""
    try:
        full_path = _expand(path)
        if not os.path.isfile(full_path):
            return _error(f"File not found: {full_path}")
        patterns = [
            re.compile(r"^\s*(class|def)\s+([A-Za-z_][\w]*)\s*(\(.*)?"),
            re.compile(r"^\s*(async\s+def)\s+([A-Za-z_][\w]*)\s*(\(.*)?"),
            re.compile(r"^\s*(export\s+)?(async\s+)?function\s+([A-Za-z_][\w]*)\s*\("),
            re.compile(r"^\s*(const|let|var)\s+([A-Za-z_][\w]*)\s*=\s*(async\s*)?\([^)]*\)\s*=>"),
            re.compile(r"^\s*(func)\s+([A-Za-z_][\w]*)\s*\("),
            re.compile(r"^\s*(pub\s+)?(fn|struct|enum|impl|trait)\s+([A-Za-z_][\w]*)"),
        ]
        outline = []
        with open(full_path, "r", encoding="utf-8", errors="replace") as file_handle:
            for line_number, line in enumerate(file_handle, 1):
                stripped = line.rstrip()
                for pattern in patterns:
                    if pattern.search(stripped):
                        outline.append({"line": line_number, "signature": stripped[:300]})
                        break
                if len(outline) >= limit:
                    break
        return _json({"path": full_path, "outline": outline, "count": len(outline)})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="code_outline",
    description="Extract a compact function/class/signature outline from source files.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Source file path"},
            "limit": {"type": "integer", "description": "Max signatures", "default": 200},
        },
        "required": ["path"],
    },
    handler=_code_outline,
)


def _project_map(path: str = ".", max_depth: int = 3) -> str:
    """Summarize project structure and common metadata files."""
    try:
        base_path = _expand(path)
        metadata_names = [
            "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml",
            "go.mod", "pom.xml", "build.gradle", "README.md", "Makefile",
            "docker-compose.yml", "Dockerfile", ".env.example",
        ]
        metadata = {}
        for name in metadata_names:
            candidate = os.path.join(base_path, name)
            if os.path.exists(candidate):
                metadata[name] = {"path": candidate, "size": os.path.getsize(candidate)}
        tree_result = json.loads(_list_tree(base_path, max_depth=max_depth, show_hidden=False, limit=300))
        return _json({"path": base_path, "metadata": metadata, "tree": tree_result.get("tree", "")})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="project_map",
    description="Summarize a project tree and important metadata files.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Project directory", "default": "."},
            "max_depth": {"type": "integer", "description": "Tree depth", "default": 3},
        },
        "required": [],
    },
    handler=_project_map,
)


# ─── JSON, CSV, SQLite ───────────────────────────────────────────────────────

def _read_json(path: str) -> str:
    """Read and parse JSON."""
    try:
        full_path = _expand(path)
        with open(full_path, "r", encoding="utf-8") as file_handle:
            data = json.load(file_handle)
        return _json({"path": full_path, "data": data})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="read_json",
    description="Read and parse a JSON file.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "JSON file path"}},
        "required": ["path"],
    },
    handler=_read_json,
)


def _write_json(path: str, data: Any, indent: int = 2) -> str:
    """Write JSON data to a file."""
    try:
        full_path = _expand(path)
        os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
        parsed = _coerce_json(data, {})
        with open(full_path, "w", encoding="utf-8") as file_handle:
            json.dump(parsed, file_handle, ensure_ascii=False, indent=indent)
            file_handle.write("\n")
        return _json({"success": True, "path": full_path})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="write_json",
    description="Write JSON data to a file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Output JSON file path"},
            "data": {"description": "JSON object/array or JSON string"},
            "indent": {"type": "integer", "description": "Indent spaces", "default": 2},
        },
        "required": ["path", "data"],
    },
    handler=_write_json,
)


def _json_query(path: str, key_path: str = "") -> str:
    """Read JSON and return a nested value using dot/index path."""
    try:
        full_path = _expand(path)
        with open(full_path, "r", encoding="utf-8") as file_handle:
            value = json.load(file_handle)
        if key_path:
            for part in key_path.split("."):
                if isinstance(value, list):
                    value = value[int(part)]
                else:
                    value = value[part]
        return _json({"path": full_path, "key_path": key_path, "value": value})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="json_query",
    description="Read JSON and return a nested value using dot paths and list indexes.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "JSON file path"},
            "key_path": {"type": "string", "description": "Dot path, e.g. users.0.name", "default": ""},
        },
        "required": ["path"],
    },
    handler=_json_query,
)


def _csv_preview(path: str, limit: int = 20, delimiter: str = ",") -> str:
    """Preview CSV rows."""
    try:
        full_path = _expand(path)
        rows = []
        with open(full_path, "r", encoding="utf-8", errors="replace", newline="") as file_handle:
            reader = csv.DictReader(file_handle, delimiter=delimiter)
            for row in reader:
                rows.append(row)
                if len(rows) >= limit:
                    break
            return _json({"path": full_path, "columns": reader.fieldnames or [], "rows": rows, "count": len(rows)})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="csv_preview",
    description="Preview CSV columns and first rows.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "CSV file path"},
            "limit": {"type": "integer", "description": "Max rows", "default": 20},
            "delimiter": {"type": "string", "description": "Delimiter", "default": ","},
        },
        "required": ["path"],
    },
    handler=_csv_preview,
)


def _sqlite_query(db_path: str, query: str, params: Any = None, limit: int = 100, allow_write: bool = False) -> str:
    """Run a SQLite query."""
    try:
        normalized = query.strip().lower()
        readonly_prefixes = ("select", "pragma", "explain", "with")
        if not allow_write and not normalized.startswith(readonly_prefixes):
            return _error("Refusing write query unless allow_write=true")
        parsed_params = _coerce_json(params, [])
        connection = sqlite3.connect(_expand(db_path))
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(query, parsed_params)
        if cursor.description:
            rows = [dict(row) for row in cursor.fetchmany(limit)]
            columns = [column[0] for column in cursor.description]
            result = {"columns": columns, "rows": rows, "count": len(rows)}
        else:
            connection.commit()
            result = {"rows_affected": cursor.rowcount}
        connection.close()
        return _json(result)
    except Exception as error:
        return _error(str(error))


register_tool(
    name="sqlite_query",
    description="Run a SQLite query. Read-only by default; set allow_write=true for writes.",
    parameters={
        "type": "object",
        "properties": {
            "db_path": {"type": "string", "description": "SQLite database path"},
            "query": {"type": "string", "description": "SQL query"},
            "params": {"description": "JSON list or object of query parameters"},
            "limit": {"type": "integer", "description": "Max rows to return", "default": 100},
            "allow_write": {"type": "boolean", "description": "Allow INSERT/UPDATE/DELETE/DDL", "default": False},
        },
        "required": ["db_path", "query"],
    },
    handler=_sqlite_query,
)


# ─── HTTP, Download, Archives ────────────────────────────────────────────────

def _http_request(method: str, url: str, headers: Any = None, body: Any = None, timeout: int = 20) -> str:
    """Make an HTTP request."""
    try:
        import requests
        parsed_headers = _coerce_json(headers, {})
        data = None
        json_body = None
        if isinstance(body, (dict, list)):
            json_body = body
        elif isinstance(body, str) and body.strip().startswith(("{", "[")):
            json_body = json.loads(body)
        elif body is not None:
            data = str(body)
        response = requests.request(
            method.upper(),
            url,
            headers=parsed_headers,
            data=data,
            json=json_body,
            timeout=timeout,
        )
        content_type = response.headers.get("content-type", "")
        text = response.text if "text" in content_type or "json" in content_type or not content_type else response.text
        return _json({
            "status": response.status_code,
            "url": response.url,
            "headers": dict(response.headers),
            "body": _truncate(text, 12000),
        })
    except Exception as error:
        return _error(str(error))


register_tool(
    name="http_request",
    description="Make an HTTP request with method, headers, and optional body.",
    parameters={
        "type": "object",
        "properties": {
            "method": {"type": "string", "description": "GET, POST, PUT, PATCH, DELETE"},
            "url": {"type": "string", "description": "Request URL"},
            "headers": {"description": "Header object or JSON string"},
            "body": {"description": "String or JSON body"},
            "timeout": {"type": "integer", "description": "Timeout seconds", "default": 20},
        },
        "required": ["method", "url"],
    },
    handler=_http_request,
)


def _download_file(url: str, path: str, overwrite: bool = False, timeout: int = 60) -> str:
    """Download a URL to a file."""
    try:
        import requests
        full_path = _expand(path)
        if os.path.exists(full_path) and not overwrite:
            return _error(f"Destination exists: {full_path}")
        os.makedirs(os.path.dirname(full_path) or ".", exist_ok=True)
        with requests.get(url, stream=True, timeout=timeout) as response:
            response.raise_for_status()
            bytes_written = 0
            with open(full_path, "wb") as file_handle:
                for chunk in response.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        file_handle.write(chunk)
                        bytes_written += len(chunk)
        return _json({"success": True, "url": url, "path": full_path, "bytes": bytes_written})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="download_file",
    description="Download a URL to a local file.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to download"},
            "path": {"type": "string", "description": "Destination file path"},
            "overwrite": {"type": "boolean", "description": "Overwrite existing file", "default": False},
            "timeout": {"type": "integer", "description": "Timeout seconds", "default": 60},
        },
        "required": ["url", "path"],
    },
    handler=_download_file,
)


def _create_archive(source: str, destination: str, overwrite: bool = False) -> str:
    """Create a zip or tar.gz archive."""
    try:
        source_path = _expand(source)
        destination_path = _expand(destination)
        if not os.path.exists(source_path):
            return _error(f"Source not found: {source_path}")
        if os.path.exists(destination_path) and not overwrite:
            return _error(f"Destination exists: {destination_path}")
        os.makedirs(os.path.dirname(destination_path) or ".", exist_ok=True)
        if destination_path.endswith(".tar.gz") or destination_path.endswith(".tgz"):
            with tarfile.open(destination_path, "w:gz") as archive:
                archive.add(source_path, arcname=os.path.basename(source_path))
        else:
            with zipfile.ZipFile(destination_path, "w", zipfile.ZIP_DEFLATED) as archive:
                if os.path.isdir(source_path):
                    for root, _, files in os.walk(source_path):
                        for filename in files:
                            file_path = os.path.join(root, filename)
                            archive.write(file_path, os.path.relpath(file_path, os.path.dirname(source_path)))
                else:
                    archive.write(source_path, os.path.basename(source_path))
        return _json({"success": True, "source": source_path, "destination": destination_path})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="create_archive",
    description="Create a .zip, .tar.gz, or .tgz archive from a file/directory.",
    parameters={
        "type": "object",
        "properties": {
            "source": {"type": "string", "description": "Source file or directory"},
            "destination": {"type": "string", "description": "Archive path"},
            "overwrite": {"type": "boolean", "description": "Overwrite existing archive", "default": False},
        },
        "required": ["source", "destination"],
    },
    handler=_create_archive,
)


def _extract_archive(path: str, destination: str, overwrite: bool = False) -> str:
    """Extract zip or tar archives."""
    try:
        archive_path = _expand(path)
        destination_path = _expand(destination)
        if not os.path.isfile(archive_path):
            return _error(f"Archive not found: {archive_path}")
        if os.path.exists(destination_path) and os.listdir(destination_path) and not overwrite:
            return _error(f"Destination is not empty: {destination_path}")
        os.makedirs(destination_path, exist_ok=True)
        if zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path) as archive:
                archive.extractall(destination_path)
        elif tarfile.is_tarfile(archive_path):
            with tarfile.open(archive_path) as archive:
                archive.extractall(destination_path)
        else:
            return _error("Unsupported archive format")
        return _json({"success": True, "archive": archive_path, "destination": destination_path})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="extract_archive",
    description="Extract a .zip, .tar, .tar.gz, or .tgz archive.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Archive path"},
            "destination": {"type": "string", "description": "Destination directory"},
            "overwrite": {"type": "boolean", "description": "Allow extracting into non-empty destination", "default": False},
        },
        "required": ["path", "destination"],
    },
    handler=_extract_archive,
)


# ─── Git Tools ───────────────────────────────────────────────────────────────

def _git_status(path: str = ".") -> str:
    try:
        return _json(_run(["git", "-C", _expand(path), "status", "--short", "--branch"], timeout=20))
    except Exception as error:
        return _error(str(error))


register_tool(
    name="git_status",
    description="Show compact git branch and working tree status.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Repo path", "default": "."}},
        "required": [],
    },
    handler=_git_status,
)


def _git_diff(path: str = ".", staged: bool = False, file: Optional[str] = None, limit: int = 20000) -> str:
    try:
        command = ["git", "-C", _expand(path), "diff"]
        if staged:
            command.append("--staged")
        if file:
            command.extend(["--", file])
        return _json(_run(command, timeout=30, limit=limit))
    except Exception as error:
        return _error(str(error))


register_tool(
    name="git_diff",
    description="Show git diff, optionally staged or scoped to a file.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repo path", "default": "."},
            "staged": {"type": "boolean", "description": "Show staged diff", "default": False},
            "file": {"type": "string", "description": "Optional file path"},
            "limit": {"type": "integer", "description": "Max output chars", "default": 20000},
        },
        "required": [],
    },
    handler=_git_diff,
)


def _git_log(path: str = ".", limit: int = 10) -> str:
    try:
        command = ["git", "-C", _expand(path), "log", f"-{limit}", "--oneline", "--decorate"]
        return _json(_run(command, timeout=20))
    except Exception as error:
        return _error(str(error))


register_tool(
    name="git_log",
    description="Show recent git commits in one-line format.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repo path", "default": "."},
            "limit": {"type": "integer", "description": "Number of commits", "default": 10},
        },
        "required": [],
    },
    handler=_git_log,
)


def _git_show(path: str = ".", ref: str = "HEAD", limit: int = 20000) -> str:
    try:
        return _json(_run(["git", "-C", _expand(path), "show", "--stat", "--patch", ref], timeout=30, limit=limit))
    except Exception as error:
        return _error(str(error))


register_tool(
    name="git_show",
    description="Show a git commit/ref with stat and patch.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Repo path", "default": "."},
            "ref": {"type": "string", "description": "Commit/ref", "default": "HEAD"},
            "limit": {"type": "integer", "description": "Max output chars", "default": 20000},
        },
        "required": [],
    },
    handler=_git_show,
)


# ─── System and Process Tools ────────────────────────────────────────────────

def _current_time() -> str:
    """Return current local and UTC time."""
    try:
        local_time = datetime.now().astimezone()
        utc_time = datetime.now(timezone.utc)
        return _json({"local": local_time.isoformat(), "utc": utc_time.isoformat(), "timezone": str(local_time.tzinfo)})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="current_time",
    description="Return current local and UTC time.",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_current_time,
)


def _system_info() -> str:
    """Return OS, Python, CPU, and platform info."""
    try:
        return _json({
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "processor": platform.processor(),
            "cwd": os.getcwd(),
            "home": os.path.expanduser("~"),
        })
    except Exception as error:
        return _error(str(error))


register_tool(
    name="system_info",
    description="Return OS, Python, CPU, cwd, and platform information.",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=_system_info,
)


def _disk_usage(path: str = ".") -> str:
    """Return disk usage for a path."""
    try:
        usage = shutil.disk_usage(_expand(path))
        return _json({"path": _expand(path), "total": usage.total, "used": usage.used, "free": usage.free})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="disk_usage",
    description="Return disk usage for a path.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Path", "default": "."}},
        "required": [],
    },
    handler=_disk_usage,
)


def _process_list(filter: str = "", limit: int = 50) -> str:
    """List running processes."""
    try:
        command = ["ps", "-eo", "pid,ppid,stat,pcpu,pmem,comm,args", "--sort=-pcpu"]
        result = _run(command, timeout=10, limit=30000)
        lines = result["output"].splitlines()
        if filter:
            header = lines[:1]
            body = [line for line in lines[1:] if filter.lower() in line.lower()]
            lines = header + body
        return _json({"processes": "\n".join(lines[: limit + 1]), "exit_code": result["exit_code"]})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="process_list",
    description="List running processes, optionally filtered.",
    parameters={
        "type": "object",
        "properties": {
            "filter": {"type": "string", "description": "Substring filter", "default": ""},
            "limit": {"type": "integer", "description": "Max process rows", "default": 50},
        },
        "required": [],
    },
    handler=_process_list,
)


def _process_kill(pid: int, signal_name: str = "TERM") -> str:
    """Send a signal to a process."""
    try:
        signal_value = getattr(signal, f"SIG{signal_name.upper()}", signal.SIGTERM)
        os.kill(int(pid), signal_value)
        return _json({"success": True, "pid": pid, "signal": signal_name.upper()})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="process_kill",
    description="Send a signal to a process by PID. Use TERM by default, KILL only when necessary.",
    parameters={
        "type": "object",
        "properties": {
            "pid": {"type": "integer", "description": "Process ID"},
            "signal_name": {"type": "string", "description": "TERM, INT, HUP, KILL", "default": "TERM"},
        },
        "required": ["pid"],
    },
    handler=_process_kill,
)


# ─── Agent Scratchpad ────────────────────────────────────────────────────────

def _task_board(action: str, item: str = "", status: str = "todo", path: str = "~/.mimo_tasks.json") -> str:
    """Simple persistent task board for agent planning."""
    try:
        board_path = _expand(path)
        if os.path.exists(board_path):
            with open(board_path, "r", encoding="utf-8") as file_handle:
                tasks = json.load(file_handle)
        else:
            tasks = []
        if action == "add":
            tasks.append({"id": len(tasks) + 1, "item": item, "status": status, "updated": datetime.now().isoformat()})
        elif action == "update":
            matched = False
            for task in tasks:
                if str(task.get("id")) == str(item) or task.get("item") == item:
                    task["status"] = status
                    task["updated"] = datetime.now().isoformat()
                    matched = True
            if not matched:
                return _error("Task not found")
        elif action == "clear":
            tasks = []
        elif action != "list":
            return _error("action must be add, update, list, or clear")
        os.makedirs(os.path.dirname(board_path) or ".", exist_ok=True)
        with open(board_path, "w", encoding="utf-8") as file_handle:
            json.dump(tasks, file_handle, ensure_ascii=False, indent=2)
        return _json({"path": board_path, "tasks": tasks})
    except Exception as error:
        return _error(str(error))


register_tool(
    name="task_board",
    description="Persistent task board for add/update/list/clear of agent work items.",
    parameters={
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["add", "update", "list", "clear"], "description": "Task action"},
            "item": {"type": "string", "description": "Task text or id for update", "default": ""},
            "status": {"type": "string", "description": "todo, doing, done, blocked", "default": "todo"},
            "path": {"type": "string", "description": "Task board JSON path", "default": "~/.mimo_tasks.json"},
        },
        "required": ["action"],
    },
    handler=_task_board,
)


if __name__ == "__main__":
    print("Available tools:")
    for schema in get_tools_schema():
        fn = schema["function"]
        print(f"  {fn['name']}: {fn['description'][:60]}...")


# ─── Browser Tools (DrissionPage — Anti-Detect Chromium) ─────────────────────

# Global browser instance (reusable)
_browser = None
_browser_tab = None


# Browser visibility mode (toggle with /browser command)
BROWSER_VISIBLE = False

def _get_browser():
    """Get or create browser instance."""
    global _browser, _browser_tab
    if _browser is None:
        from DrissionPage import ChromiumPage, ChromiumOptions
        co = ChromiumOptions()
        # Use Playwright's Chromium (already installed)
        import os
        pw_chromium = os.path.expanduser('~/.cache/ms-playwright/chromium-1208/chrome-linux64/chrome')
        if os.path.exists(pw_chromium):
            co.set_browser_path(pw_chromium)
        # Toggle headless based on BROWSER_VISIBLE
        if not BROWSER_VISIBLE:
            co.headless()
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-gpu')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_argument('--disable-infobars')
        co.set_argument('--window-size=1280,800')
        co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
        co.set_pref('credentials_enable_service', False)
        co.set_pref('profile.password_manager_enabled', False)
        _browser = ChromiumPage(co)
        _browser_tab = _browser
    return _browser_tab


def set_browser_visible(visible: bool):
    """Toggle browser visibility. Closes current browser to apply."""
    global BROWSER_VISIBLE, _browser, _browser_tab
    BROWSER_VISIBLE = visible
    # Close existing browser to force new instance with new settings
    if _browser:
        try:
            _browser.quit()
        except:
            pass
        _browser = None
        _browser_tab = None
    return BROWSER_VISIBLE


def _browser_open(url: str, wait: int = 3) -> str:
    """Open a URL in headless Chromium. Returns page title and text."""
    import time
    import re as _re

    # Cap wait time to reasonable limits
    if wait > 15:
        wait = 15
    if wait < 1:
        wait = 1

    for attempt in range(3):
        try:
            tab = _get_browser()
            tab.get(url)
            time.sleep(wait)

            # Check if page loaded properly
            try:
                title = tab.title
                html_content = tab.html
            except Exception:
                # Connection lost — recreate browser
                if _browser:
                    try:
                        _browser.quit()
                    except:
                        pass
                _browser = None
                _browser_tab = None
                if attempt < 2:
                    time.sleep(1)
                    continue
                return json.dumps({"error": "Browser connection lost after 3 attempts", "url": url})

            if not html_content or len(html_content) < 100:
                if attempt < 2:
                    time.sleep(2)
                    continue
                return json.dumps({"error": "Page returned empty content", "url": url})

            text = html_content[:20000] if len(html_content) > 20000 else html_content
            # Strip HTML to text
            clean = _re.sub(r'<script[^>]*>.*?</script>', '', text, flags=_re.DOTALL)
            clean = _re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=_re.DOTALL)
            clean = _re.sub(r'<[^>]+>', ' ', clean)
            clean = _re.sub(r'\s+', ' ', clean).strip()
            if len(clean) > 10000:
                clean = clean[:10000] + "\n... (truncated)"
            return json.dumps({"url": url, "title": title or "", "content": clean, "status": "ok"})
        except Exception as e:
            error_msg = str(e)
            # If connection error, recreate browser
            if "连接已断开" in error_msg or "connection" in error_msg.lower():
                try:
                    _browser.quit()
                except:
                    pass
                _browser = None
                _browser_tab = None
                if attempt < 2:
                    time.sleep(1)
                    continue
            return json.dumps({"error": error_msg, "url": url, "attempt": attempt + 1})

    return json.dumps({"error": "All attempts failed", "url": url})


def _browser_get_text(selector: str = "body") -> str:
    """Get text content from current page, optionally filtered by CSS selector."""
    try:
        tab = _get_browser()
        if selector == "body":
            text = tab.html
            import re
            clean = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            clean = re.sub(r'<style[^>]*>.*?</style>', '', clean, flags=re.DOTALL)
            clean = re.sub(r'<[^>]+>', ' ', clean)
            clean = re.sub(r'\s+', ' ', clean).strip()
        else:
            elem = tab.ele(selector)
            clean = elem.text if elem else "Element not found"
        if len(clean) > 10000:
            clean = clean[:10000] + "\n... (truncated)"
        return json.dumps({"text": clean, "selector": selector})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _browser_get_links() -> str:
    """Get all links from current page."""
    try:
        tab = _get_browser()
        links = []
        for elem in tab.eles('tag:a'):
            href = elem.attr('href')
            text = elem.text.strip()
            if href and href.startswith('http'):
                links.append({"url": href, "text": text[:100]})
        return json.dumps({"links": links[:50], "total": len(links)})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _browser_click(selector: str) -> str:
    """Click an element on the page."""
    try:
        tab = _get_browser()
        elem = tab.ele(selector)
        if elem:
            elem.click()
            import time
            time.sleep(1)
            return json.dumps({"clicked": selector, "status": "ok"})
        return json.dumps({"error": f"Element not found: {selector}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _browser_type(selector: str, text: str, press_enter: bool = False) -> str:
    """Type text into an input field."""
    try:
        tab = _get_browser()
        elem = tab.ele(selector)
        if elem:
            elem.clear()
            elem.input(text)
            if press_enter:
                from DrissionPage.common import Keys
                elem.input(Keys.ENTER)
            import time
            time.sleep(0.5)
            return json.dumps({"typed": text, "selector": selector, "status": "ok"})
        return json.dumps({"error": f"Element not found: {selector}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _browser_evaluate(js_code: str) -> str:
    """Execute JavaScript in the browser and return result."""
    try:
        tab = _get_browser()
        result = tab.run_js(js_code)
        return json.dumps({"result": str(result)[:5000]})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _browser_wait_for(selector: str, timeout: int = 10) -> str:
    """Wait for an element to appear on the page."""
    try:
        tab = _get_browser()
        elem = tab.ele(selector, timeout=timeout)
        if elem:
            return json.dumps({"found": selector, "text": elem.text[:200]})
        return json.dumps({"error": f"Timeout waiting for: {selector}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _browser_close() -> str:
    """Close the browser."""
    try:
        if not HAS_BROWSER_ENGINE or browser_engine is None:
            return json.dumps({"error": "Browser engine is not available"})
        return json.dumps(browser_engine.close_browser())
    except Exception as e:
        return json.dumps({"error": str(e)})


def _browser_status() -> str:
    """Get browser status."""
    try:
        if not HAS_BROWSER_ENGINE or browser_engine is None:
            return json.dumps({"error": "Browser engine is not available"})
        status = browser_engine.get_browser_status()
        return json.dumps(status)
    except Exception as e:
        return json.dumps({"error": str(e)})


def _browser_set_engine(engine: str) -> str:
    """Switch browser engine (drission/playwright)."""
    try:
        if not HAS_BROWSER_ENGINE or browser_engine is None:
            return json.dumps({"error": "Browser engine is not available"})
        result = browser_engine.set_engine(engine)
        return json.dumps({"engine": result, "status": "switched"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# Register browser tools (using hybrid engine)
register_tool(
    name="browser_open",
    description="Open URL in headless Chromium. Auto-fallback between DrissionPage (fast) and Playwright (stable for SPA).",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to open"},
            "wait": {"type": "integer", "description": "Seconds to wait for JS (default 3)", "default": 3},
            "engine": {"type": "string", "description": "Force engine: drission or playwright (auto if omitted)"},
        },
        "required": ["url"],
    },
    handler=lambda url, wait=3, engine=None: browser_engine.browser_open(url, wait, engine),
)

register_tool(
    name="browser_get_text",
    description="Get text content from current browser page. Use CSS selector to target specific element.",
    parameters={
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector (default: body)", "default": "body"},
        },
        "required": [],
    },
    handler=lambda selector="body": browser_engine.browser_get_text(selector),
)

register_tool(
    name="browser_get_links",
    description="Get all links from current browser page.",
    parameters={
        "type": "object",
        "properties": {},
        "required": [],
    },
    handler=lambda: browser_engine.browser_get_links(),
)

register_tool(
    name="browser_click",
    description="Click an element on the current browser page.",
    parameters={
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector of element to click"},
        },
        "required": ["selector"],
    },
    handler=lambda selector: browser_engine.browser_click(selector),
)

register_tool(
    name="browser_type",
    description="Type text into an input field on the current browser page.",
    parameters={
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector of input field"},
            "text": {"type": "string", "description": "Text to type"},
            "press_enter": {"type": "boolean", "description": "Press Enter after typing", "default": False},
        },
        "required": ["selector", "text"],
    },
    handler=lambda selector, text, press_enter=False: browser_engine.browser_type(selector, text, press_enter),
)

register_tool(
    name="browser_evaluate",
    description="Execute JavaScript in the browser and return the result.",
    parameters={
        "type": "object",
        "properties": {
            "js_code": {"type": "string", "description": "JavaScript code to execute"},
        },
        "required": ["js_code"],
    },
    handler=lambda js_code: browser_engine.browser_evaluate(js_code),
)

register_tool(
    name="browser_wait_for",
    description="Wait for an element to appear on the page.",
    parameters={
        "type": "object",
        "properties": {
            "selector": {"type": "string", "description": "CSS selector to wait for"},
            "timeout": {"type": "integer", "description": "Max seconds to wait (default 10)", "default": 10},
        },
        "required": ["selector"],
    },
    handler=lambda selector, timeout=10: browser_engine.browser_wait_for(selector, timeout),
)

register_tool(
    name="browser_screenshot",
    description="Take a screenshot of the current page.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to save screenshot", "default": "/tmp/mimo_screenshot.png"},
        },
        "required": [],
    },
    handler=lambda path="/tmp/mimo_screenshot.png": browser_engine.browser_screenshot(path),
)

register_tool(
    name="browser_close",
    description="Close browser and free memory.",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=lambda: _browser_close(),
)

register_tool(
    name="browser_status",
    description="Get current browser status (engine, alive, age).",
    parameters={"type": "object", "properties": {}, "required": []},
    handler=lambda: _browser_status(),
)

register_tool(
    name="browser_set_engine",
    description="Switch browser engine. Options: drission (fast), playwright (stable for SPA).",
    parameters={
        "type": "object",
        "properties": {
            "engine": {"type": "string", "description": "Engine name: drission or playwright"},
        },
        "required": ["engine"],
    },
    handler=lambda engine: _browser_set_engine(engine),
)


# ─── Register Extra Tools (Skills, Memory, Todo, Vision, TTS, Browser) ──────

if HAS_EXTRA_TOOLS:
    _extra_count = register_extra_tools(register_tool)
    # print(f"Registered {_extra_count} extra tools")

if HAS_UPGRADE_TOOLS:
    _upgrade_count = register_upgrade_tools(register_tool)
    # print(f"Registered {_upgrade_count} upgrade tools")

# ─── Import New Modules (OpenClaw/Hermes/DeerFlow features) ──────────────

# Supervisor/Planner (DeerFlow)
try:
    from tools.supervisor import register_supervisor_tools
    HAS_SUPERVISOR = True
except ImportError:
    HAS_SUPERVISOR = False

# Session Search (Hermes)
try:
    from tools.session_search import register_session_search_tools
    HAS_SESSION_SEARCH = True
except ImportError:
    HAS_SESSION_SEARCH = False

# Vision/Image Analysis
try:
    from tools.vision import register_vision_tools
    HAS_VISION = True
except ImportError:
    HAS_VISION = False

# Voice/TTS
try:
    from tools.voice import register_voice_tools
    HAS_VOICE = True
except ImportError:
    HAS_VOICE = False

# Webhooks
try:
    from tools.webhooks import register_webhook_tools
    HAS_WEBHOOKS = True
except ImportError:
    HAS_WEBHOOKS = False

# Enhanced Memory
try:
    from tools.enhanced_memory import register_enhanced_memory_tools
    HAS_ENHANCED_MEMORY = True
except ImportError:
    HAS_ENHANCED_MEMORY = False

# Thinking
try:
    from tools.thinking import register_thinking_tools
    HAS_THINKING = True
except ImportError:
    HAS_THINKING = False

# Notification
try:
    from tools.notification import register_notification_tools
    HAS_NOTIFICATION = True
except ImportError:
    HAS_NOTIFICATION = False

# Session Manager
try:
    from tools.session_manager import register_session_manager_tools
    HAS_SESSION_MANAGER = True
except ImportError:
    HAS_SESSION_MANAGER = False

# Cron Manager
try:
    from tools.cron_manager import register_cron_manager_tools
    HAS_CRON_MANAGER = True
except ImportError:
    HAS_CRON_MANAGER = False

# Delegation
try:
    from tools.delegation import register_delegation_tools
    HAS_DELEGATION = True
except ImportError:
    HAS_DELEGATION = False

# Skill Scanner (OpenClaw)
try:
    from tools.skill_scanner import register_skill_scanner_tools
    HAS_SKILL_SCANNER = True
except ImportError:
    HAS_SKILL_SCANNER = False

# Channel Router (OpenClaw)
try:
    from tools.channel_router import register_channel_router_tools
    HAS_CHANNEL_ROUTER = True
except ImportError:
    HAS_CHANNEL_ROUTER = False

# Auto Improve (OpenClaw)
try:
    from tools.auto_improve import register_auto_improve_tools
    HAS_AUTO_IMPROVE = True
except ImportError:
    HAS_AUTO_IMPROVE = False

# Event System (OpenClaw)
try:
    from tools.event_system import register_event_system_tools
    HAS_EVENT_SYSTEM = True
except ImportError:
    HAS_EVENT_SYSTEM = False

# Plugin System (OpenClaw)
try:
    from tools.plugin_system import register_plugin_system_tools
    HAS_PLUGIN_SYSTEM = True
except ImportError:
    HAS_PLUGIN_SYSTEM = False

# Context Compressor (Hermes)
try:
    from tools.context_compressor import register_context_compressor_tools
    HAS_CONTEXT_COMPRESSOR = True
except ImportError:
    HAS_CONTEXT_COMPRESSOR = False

# Credential Pool (Hermes)
try:
    from tools.credential_pool import register_credential_pool_tools
    HAS_CREDENTIAL_POOL = True
except ImportError:
    HAS_CREDENTIAL_POOL = False

# Skill Manager (Hermes)
try:
    from tools.skill_manager import register_skill_manager_tools
    HAS_SKILL_MANAGER = True
except ImportError:
    HAS_SKILL_MANAGER = False

# Kanban (Hermes)
try:
    from tools.kanban import register_kanban_tools
    HAS_KANBAN = True
except ImportError:
    HAS_KANBAN = False

# MCP Client (Hermes)
try:
    from tools.mcp_client import register_mcp_client_tools
    HAS_MCP_CLIENT = True
except ImportError:
    HAS_MCP_CLIENT = False

# Sandbox
try:
    from tools.sandbox import register_sandbox_tools
    HAS_SANDBOX = True
except ImportError:
    HAS_SANDBOX = False

# Checkpoints (Hermes)
try:
    from tools.checkpoints import register_checkpoint_tools
    HAS_CHECKPOINTS = True
except ImportError:
    HAS_CHECKPOINTS = False

# Workspaces (OpenClaw)
try:
    from tools.workspaces import register_workspace_tools
    HAS_WORKSPACES = True
except ImportError:
    HAS_WORKSPACES = False

# Register all new tools
if HAS_SUPERVISOR:
    try:
        register_supervisor_tools(register_tool)
    except Exception:
        pass

if HAS_SESSION_SEARCH:
    try:
        register_session_search_tools(register_tool)
    except Exception:
        pass

if HAS_VISION:
    try:
        register_vision_tools(register_tool)
    except Exception:
        pass

if HAS_VOICE:
    try:
        register_voice_tools(register_tool)
    except Exception:
        pass

if HAS_WEBHOOKS:
    try:
        register_webhook_tools(register_tool)
    except Exception:
        pass

if HAS_ENHANCED_MEMORY:
    try:
        register_enhanced_memory_tools(register_tool)
    except Exception:
        pass

if HAS_THINKING:
    try:
        register_thinking_tools(register_tool)
    except Exception:
        pass

if HAS_NOTIFICATION:
    try:
        register_notification_tools(register_tool)
    except Exception:
        pass

if HAS_SESSION_MANAGER:
    try:
        register_session_manager_tools(register_tool)
    except Exception:
        pass

if HAS_CRON_MANAGER:
    try:
        register_cron_manager_tools(register_tool)
    except Exception:
        pass

if HAS_DELEGATION:
    try:
        register_delegation_tools(register_tool)
    except Exception:
        pass

if HAS_SKILL_SCANNER:
    try:
        register_skill_scanner_tools(register_tool)
    except Exception:
        pass

if HAS_CHANNEL_ROUTER:
    try:
        register_channel_router_tools(register_tool)
    except Exception:
        pass

if HAS_AUTO_IMPROVE:
    try:
        register_auto_improve_tools(register_tool)
    except Exception:
        pass

if HAS_EVENT_SYSTEM:
    try:
        register_event_system_tools(register_tool)
    except Exception:
        pass

if HAS_PLUGIN_SYSTEM:
    try:
        register_plugin_system_tools(register_tool)
    except Exception:
        pass

if HAS_CONTEXT_COMPRESSOR:
    try:
        register_context_compressor_tools(register_tool)
    except Exception:
        pass

if HAS_CREDENTIAL_POOL:
    try:
        register_credential_pool_tools(register_tool)
    except Exception:
        pass

if HAS_SKILL_MANAGER:
    try:
        register_skill_manager_tools(register_tool)
    except Exception:
        pass

if HAS_KANBAN:
    try:
        register_kanban_tools(register_tool)
    except Exception:
        pass

if HAS_MCP_CLIENT:
    try:
        register_mcp_client_tools(register_tool)
    except Exception:
        pass

if HAS_SANDBOX:
    try:
        register_sandbox_tools(register_tool)
    except Exception:
        pass

if HAS_CHECKPOINTS:
    try:
        register_checkpoint_tools(register_tool)
    except Exception:
        pass

if HAS_WORKSPACES:
    try:
        register_workspace_tools(register_tool)
    except Exception:
        pass

# ─── Import Security System ──────────────────────────────────────────────

try:
    from tools.security import register_security_tools
    HAS_SECURITY_TOOLS = True
except ImportError:
    HAS_SECURITY_TOOLS = False

if HAS_SECURITY_TOOLS:
    try:
        register_security_tools(register_tool)
    except Exception:
        pass

# ─── Import Nodriver Engine ──────────────────────────────────────────────

try:
    from tools.nodriver_engine import register_nodriver_tools
    HAS_NODEIVER = True
except ImportError:
    HAS_NODEIVER = False

if HAS_NODEIVER:
    try:
        register_nodriver_tools(register_tool)
    except Exception:
        pass
