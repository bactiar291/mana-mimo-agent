"""
sandbox.py — Code Execution Sandbox
Sandboxed Python and Bash execution.
"""
import json
import os
import subprocess
import tempfile
from typing import Any, Dict, List, Optional
from datetime import datetime

def sandbox_execute(code: str, language: str = "python", timeout: int = 30) -> str:
    """Execute code in sandbox."""
    try:
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix=f'.{language}', delete=False) as f:
            f.write(code)
            temp_file = f.name
        
        # Execute
        if language == "python":
            cmd = ["python3", temp_file]
        elif language == "bash":
            cmd = ["bash", temp_file]
        else:
            return json.dumps({"success": False, "error": f"Unsupported language: {language}"})
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        
        # Cleanup
        os.unlink(temp_file)
        
        return json.dumps({
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "return_code": result.returncode,
            "language": language
        })
    except subprocess.TimeoutExpired:
        return json.dumps({"success": False, "error": "Execution timed out"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def sandbox_install(package: str, language: str = "python") -> str:
    """Install package in sandbox."""
    try:
        if language == "python":
            cmd = ["pip", "install", package]
        elif language == "bash":
            cmd = ["apt-get", "install", "-y", package]
        else:
            return json.dumps({"success": False, "error": f"Unsupported language: {language}"})
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        return json.dumps({
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "package": package,
            "language": language
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def sandbox_test(code: str, test_code: str = "", language: str = "python") -> str:
    """Run and test code."""
    try:
        # Execute main code
        main_result = sandbox_execute(code, language)
        main_data = json.loads(main_result)
        
        if not main_data.get("success"):
            return main_result
        
        # Execute test code if provided
        if test_code:
            test_result = sandbox_execute(test_code, language)
            test_data = json.loads(test_result)
            
            return json.dumps({
                "success": True,
                "main_output": main_data.get("stdout"),
                "test_output": test_data.get("stdout"),
                "test_passed": test_data.get("success"),
                "language": language
            })
        else:
            return json.dumps({
                "success": True,
                "output": main_data.get("stdout"),
                "language": language
            })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_sandbox_tools(register_tool):
    """Register sandbox tools."""
    register_tool(
        name="sandbox_execute",
        description="Execute code in sandbox",
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to execute"},
                "language": {"type": "string", "description": "Language: python, bash", "default": "python"},
                "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30}
            },
            "required": ["code"]
        },
        handler=lambda args: sandbox_execute(args.get("code", ""), args.get("language", "python"), args.get("timeout", 30))
    )
    
    register_tool(
        name="sandbox_install",
        description="Install package in sandbox",
        parameters={
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Package name"},
                "language": {"type": "string", "description": "Language: python, bash", "default": "python"}
            },
            "required": ["package"]
        },
        handler=lambda args: sandbox_install(args.get("package", ""), args.get("language", "python"))
    )
    
    register_tool(
        name="sandbox_test",
        description="Run and test code",
        parameters={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Code to execute"},
                "test_code": {"type": "string", "description": "Test code", "default": ""},
                "language": {"type": "string", "description": "Language: python, bash", "default": "python"}
            },
            "required": ["code"]
        },
        handler=lambda args: sandbox_test(args.get("code", ""), args.get("test_code", ""), args.get("language", "python"))
    )
