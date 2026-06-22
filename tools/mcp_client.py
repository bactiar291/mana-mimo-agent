"""
mcp_client.py — Model Context Protocol Client (Hermes-inspired)
Connect to MCP servers and call their tools.
"""
import json
import os
import shlex
import subprocess
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

# ─── MCP Storage ──────────────────────────────────────────────────────
MCP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "mcp")
os.makedirs(MCP_DIR, exist_ok=True)


def _read_mcp_message(stdout) -> Dict[str, Any]:
    """Read one Content-Length framed MCP JSON-RPC message."""
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = stdout.read(1)
        if not chunk:
            raise RuntimeError("MCP server closed stdout before response")
        header += chunk
        if len(header) > 8192:
            raise RuntimeError("MCP response header too large")
    length = 0
    for line in header.decode("utf-8", errors="replace").split("\r\n"):
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
            break
    if length <= 0:
        raise RuntimeError("MCP response missing Content-Length")
    body = stdout.read(length)
    if len(body) != length:
        raise RuntimeError("MCP response body truncated")
    return json.loads(body.decode("utf-8"))


def _write_mcp_message(stdin, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    stdin.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    stdin.flush()


def _open_command_transport(command: str):
    if not command:
        raise RuntimeError("MCP command transport missing command")
    return subprocess.Popen(
        shlex.split(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _mcp_command_request(command: str, method: str, params: Dict[str, Any] = None, timeout: int = 15) -> Dict[str, Any]:
    """Start a command MCP server, initialize, run one request, then terminate."""
    proc = _open_command_transport(command)
    try:
        request_id = 1
        _write_mcp_message(proc.stdin, {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mimo-agent", "version": "1.0"},
            },
        })
        initialized = _read_mcp_message(proc.stdout)
        if initialized.get("error"):
            return initialized

        _write_mcp_message(proc.stdin, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        request_id += 1
        _write_mcp_message(proc.stdin, {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        })
        return _read_mcp_message(proc.stdout)
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        for stream in (proc.stdout, proc.stderr):
            try:
                if stream:
                    stream.close()
            except Exception:
                pass

def mcp_server(action: str = "list", name: str = "", url: str = "", command: str = "") -> str:
    """Manage MCP servers."""
    try:
        if action == "add":
            if not name:
                return json.dumps({"success": False, "error": "Server name required"})
            
            server = {
                "name": name,
                "url": url,
                "command": command,
                "enabled": True,
                "added_at": datetime.now().isoformat()
            }
            
            server_file = os.path.join(MCP_DIR, f"{name}.json")
            with open(server_file, "w") as f:
                json.dump(server, f, indent=2)
            
            return json.dumps({"success": True, "name": name, "message": "MCP server added"})
        
        elif action == "list":
            servers = []
            for f in os.listdir(MCP_DIR):
                if f.endswith(".json"):
                    with open(os.path.join(MCP_DIR, f), "r") as file:
                        servers.append(json.load(file))
            
            return json.dumps({"success": True, "servers": servers, "count": len(servers)})
        
        elif action == "remove":
            server_file = os.path.join(MCP_DIR, f"{name}.json")
            if os.path.exists(server_file):
                os.remove(server_file)
                return json.dumps({"success": True, "name": name, "message": "MCP server removed"})
            else:
                return json.dumps({"success": False, "error": "Server not found"})
        
        else:
            return json.dumps({"success": False, "error": "Invalid action"})
    
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def mcp_tools(server_name: str = "") -> str:
    """List available MCP tools."""
    try:
        if server_name:
            server_file = os.path.join(MCP_DIR, f"{server_name}.json")
            if not os.path.exists(server_file):
                return json.dumps({"success": False, "error": "Server not found"})
            
            with open(server_file, "r") as f:
                server = json.load(f)
            if server.get("command"):
                response = _mcp_command_request(server["command"], "tools/list", {})
                if response.get("error"):
                    return json.dumps({"success": False, "server": server_name, "error": response.get("error")})
                tools = response.get("result", {}).get("tools", [])
                server["tools"] = tools
                with open(server_file, "w") as f:
                    json.dump(server, f, indent=2)
                return json.dumps({
                    "success": True,
                    "server": server_name,
                    "tools": tools,
                    "message": "Tools listed via command transport"
                })

            return json.dumps({
                "success": True,
                "server": server_name,
                "tools": server.get("tools", []),
                "message": "Tools listed"
            })
        else:
            # List all tools from all servers
            all_tools = []
            for f in os.listdir(MCP_DIR):
                if f.endswith(".json"):
                    with open(os.path.join(MCP_DIR, f), "r") as file:
                        server = json.load(file)
                        for tool in server.get("tools", []):
                            tool["server"] = server.get("name")
                            all_tools.append(tool)
            
            return json.dumps({"success": True, "tools": all_tools, "count": len(all_tools)})
    
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def mcp_call(server_name: str, tool_name: str, arguments: str = "{}") -> str:
    """Call an MCP tool."""
    try:
        server_file = os.path.join(MCP_DIR, f"{server_name}.json")
        if not os.path.exists(server_file):
            return json.dumps({"success": False, "error": "Server not found", "reason": "not_found"})

        with open(server_file, "r") as f:
            server = json.load(f)

        parsed_arguments = json.loads(arguments) if isinstance(arguments, str) else arguments

        if server.get("command"):
            response = _mcp_command_request(
                server["command"],
                "tools/call",
                {"name": tool_name, "arguments": parsed_arguments},
            )
            if response.get("error"):
                return json.dumps({"success": False, "server": server_name, "tool": tool_name, "error": response.get("error"), "reason": "transport_error"})
            return json.dumps({
                "success": True,
                "server": server_name,
                "tool": tool_name,
                "arguments": parsed_arguments,
                "result": response.get("result", {}),
            })

        return json.dumps({
            "success": False,
            "server": server_name,
            "tool": tool_name,
            "arguments": parsed_arguments,
            "reason": "not_implemented",
            "error": "MCP JSON-RPC client requires a command transport; URL transport is not implemented yet",
            "configured_transport": "command" if server.get("command") else "url" if server.get("url") else "none",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e), "reason": "transport_error"})

def mcp_list() -> str:
    """List all MCP servers."""
    return mcp_server(action="list")

def mcp_test(server_name: str) -> str:
    """Test MCP server connection."""
    try:
        server_file = os.path.join(MCP_DIR, f"{server_name}.json")
        if not os.path.exists(server_file):
            return json.dumps({"success": False, "error": "Server not found"})
        
        with open(server_file, "r") as f:
            server = json.load(f)

        if server.get("command"):
            response = _mcp_command_request(server["command"], "tools/list", {})
            if response.get("error"):
                return json.dumps({"success": False, "server": server_name, "error": response.get("error")})
            return json.dumps({
                "success": True,
                "server": server_name,
                "transport": "command",
                "tools_count": len(response.get("result", {}).get("tools", [])),
                "message": "MCP command transport responded"
            })

        return json.dumps({
            "success": False,
            "server": server_name,
            "url": server.get("url"),
            "command": server.get("command"),
            "reason": "not_implemented",
            "error": "MCP connection testing requires a JSON-RPC transport implementation",
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def mcp_reload(server_name: str = "") -> str:
    """Reload MCP server(s)."""
    try:
        if server_name:
            return json.dumps({
                "success": False,
                "server": server_name,
                "reason": "not_implemented",
                "error": "MCP server reload is not implemented"
            })
        else:
            return json.dumps({
                "success": False,
                "reason": "not_implemented",
                "error": "MCP server reload is not implemented"
            })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_mcp_client_tools(register_tool):
    """Register MCP client tools."""
    register_tool(
        name="mcp_server",
        description="Manage MCP servers (add, list, remove)",
        parameters={
            "type": "object",
            "properties": {
                "action": {"type": "string", "description": "Action: add, list, remove", "default": "list"},
                "name": {"type": "string", "description": "Server name", "default": ""},
                "url": {"type": "string", "description": "Server URL", "default": ""},
                "command": {"type": "string", "description": "Server command", "default": ""}
            }
        },
        handler=lambda args: mcp_server(args.get("action", "list"), args.get("name", ""), args.get("url", ""), args.get("command", ""))
    )
    
    register_tool(
        name="mcp_tools",
        description="List available MCP tools",
        parameters={
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Server name", "default": ""}
            }
        },
        handler=lambda args: mcp_tools(args.get("server_name", ""))
    )
    
    register_tool(
        name="mcp_call",
        description="Call an MCP tool",
        parameters={
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Server name"},
                "tool_name": {"type": "string", "description": "Tool name"},
                "arguments": {"type": "string", "description": "JSON arguments", "default": "{}"}
            },
            "required": ["server_name", "tool_name"]
        },
        handler=lambda args: mcp_call(args.get("server_name", ""), args.get("tool_name", ""), args.get("arguments", "{}"))
    )
    
    register_tool(
        name="mcp_list",
        description="List all MCP servers",
        parameters={"type": "object", "properties": {}},
        handler=lambda args: mcp_list()
    )
    
    register_tool(
        name="mcp_test",
        description="Test MCP server connection",
        parameters={
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Server name"}
            },
            "required": ["server_name"]
        },
        handler=lambda args: mcp_test(args.get("server_name", ""))
    )
    
    register_tool(
        name="mcp_reload",
        description="Reload MCP server(s)",
        parameters={
            "type": "object",
            "properties": {
                "server_name": {"type": "string", "description": "Server name", "default": ""}
            }
        },
        handler=lambda args: mcp_reload(args.get("server_name", ""))
    )
