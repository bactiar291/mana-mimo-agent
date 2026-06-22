"""
credential_pool.py — Credential Pool (Hermes-inspired)
Manage multiple API keys with rotation and failover.
"""
import json
import os
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

# ─── Credential Storage ──────────────────────────────────────────────────
CREDENTIALS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "credentials")
os.makedirs(CREDENTIALS_DIR, exist_ok=True)

class Credential:
    def __init__(self, name: str, provider: str, key: str, secret: str = ""):
        self.credential_id = f"{provider}_{name}"
        self.name = name
        self.provider = provider
        self.key = key
        self.secret = secret
        self.enabled = True
        self.usage_count = 0
        self.last_used = None
        self.created_at = datetime.now().isoformat()
    
    def to_dict(self):
        return {
            "credential_id": self.credential_id,
            "name": self.name,
            "provider": self.provider,
            "key": self.key[:8] + "..." if len(self.key) > 8 else self.key,
            "enabled": self.enabled,
            "usage_count": self.usage_count,
            "last_used": self.last_used,
            "created_at": self.created_at
        }

def credential_add(name: str, provider: str, key: str, secret: str = "") -> str:
    """Add a credential to the pool."""
    try:
        credential = Credential(name, provider, key, secret)
        
        credential_file = os.path.join(CREDENTIALS_DIR, f"{credential.credential_id}.json")
        with open(credential_file, "w") as f:
            json.dump({
                "credential_id": credential.credential_id,
                "name": name,
                "provider": provider,
                "key": key,
                "secret": secret,
                "enabled": True,
                "usage_count": 0,
                "last_used": None,
                "created_at": credential.created_at
            }, f, indent=2)
        
        return json.dumps({
            "success": True,
            "credential_id": credential.credential_id,
            "name": name,
            "provider": provider,
            "message": "Credential added"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def credential_list(provider: str = "") -> str:
    """List all credentials."""
    try:
        credentials = []
        for f in os.listdir(CREDENTIALS_DIR):
            if f.endswith(".json"):
                with open(os.path.join(CREDENTIALS_DIR, f), "r") as file:
                    cred = json.load(file)
                    if not provider or cred.get("provider") == provider:
                        credentials.append({
                            "credential_id": cred.get("credential_id"),
                            "name": cred.get("name"),
                            "provider": cred.get("provider"),
                            "key": cred.get("key", "")[:8] + "...",
                            "enabled": cred.get("enabled"),
                            "usage_count": cred.get("usage_count"),
                            "last_used": cred.get("last_used")
                        })
        
        return json.dumps({"success": True, "credentials": credentials, "count": len(credentials)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def credential_remove(credential_id: str) -> str:
    """Remove a credential."""
    try:
        credential_file = os.path.join(CREDENTIALS_DIR, f"{credential_id}.json")
        if os.path.exists(credential_file):
            os.remove(credential_file)
            return json.dumps({"success": True, "removed": credential_id})
        else:
            return json.dumps({"success": False, "error": "Credential not found"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def credential_rotate(provider: str) -> str:
    """Rotate to next credential for a provider."""
    try:
        credentials = []
        for f in os.listdir(CREDENTIALS_DIR):
            if f.endswith(".json"):
                with open(os.path.join(CREDENTIALS_DIR, f), "r") as file:
                    cred = json.load(file)
                    if cred.get("provider") == provider and cred.get("enabled"):
                        credentials.append(cred)
        
        if not credentials:
            return json.dumps({"success": False, "error": "No enabled credentials for provider"})
        
        # Find least used credential
        least_used = min(credentials, key=lambda x: x.get("usage_count", 0))
        
        # Update usage
        least_used["usage_count"] = least_used.get("usage_count", 0) + 1
        least_used["last_used"] = datetime.now().isoformat()
        
        credential_file = os.path.join(CREDENTIALS_DIR, f"{least_used['credential_id']}.json")
        with open(credential_file, "w") as f:
            json.dump(least_used, f, indent=2)
        
        return json.dumps({
            "success": True,
            "credential_id": least_used["credential_id"],
            "provider": provider,
            "usage_count": least_used["usage_count"],
            "message": "Rotated to credential"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def credential_test(credential_id: str) -> str:
    """Test a credential."""
    try:
        credential_file = os.path.join(CREDENTIALS_DIR, f"{credential_id}.json")
        if not os.path.exists(credential_file):
            return json.dumps({"success": False, "error": "Credential not found"})
        
        with open(credential_file, "r") as f:
            cred = json.load(f)
        
        # Basic validation
        if not cred.get("key"):
            return json.dumps({"success": False, "error": "No key found"})
        
        return json.dumps({
            "success": True,
            "credential_id": credential_id,
            "provider": cred.get("provider"),
            "key_length": len(cred.get("key", "")),
            "message": "Credential appears valid"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def credential_export(output_path: str = "") -> str:
    """Export credentials (without secrets)."""
    try:
        if not output_path:
            output_path = os.path.join(CREDENTIALS_DIR, "export.json")
        
        credentials = []
        for f in os.listdir(CREDENTIALS_DIR):
            if f.endswith(".json"):
                with open(os.path.join(CREDENTIALS_DIR, f), "r") as file:
                    cred = json.load(file)
                    credentials.append({
                        "credential_id": cred.get("credential_id"),
                        "name": cred.get("name"),
                        "provider": cred.get("provider"),
                        "enabled": cred.get("enabled"),
                        "usage_count": cred.get("usage_count")
                    })
        
        with open(output_path, "w") as f:
            json.dump(credentials, f, indent=2)
        
        return json.dumps({"success": True, "exported": output_path, "count": len(credentials)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_credential_pool_tools(register_tool):
    """Register credential pool tools."""
    register_tool(
        name="credential_add",
        description="Add a credential to the pool",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Credential name"},
                "provider": {"type": "string", "description": "Provider name"},
                "key": {"type": "string", "description": "API key"},
                "secret": {"type": "string", "description": "API secret", "default": ""}
            },
            "required": ["name", "provider", "key"]
        },
        handler=lambda args: credential_add(args.get("name", ""), args.get("provider", ""), args.get("key", ""), args.get("secret", ""))
    )
    
    register_tool(
        name="credential_list",
        description="List all credentials",
        parameters={
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "Filter by provider", "default": ""}
            }
        },
        handler=lambda args: credential_list(args.get("provider", ""))
    )
    
    register_tool(
        name="credential_remove",
        description="Remove a credential",
        parameters={
            "type": "object",
            "properties": {
                "credential_id": {"type": "string", "description": "Credential ID"}
            },
            "required": ["credential_id"]
        },
        handler=lambda args: credential_remove(args.get("credential_id", ""))
    )
    
    register_tool(
        name="credential_rotate",
        description="Rotate to next credential for a provider",
        parameters={
            "type": "object",
            "properties": {
                "provider": {"type": "string", "description": "Provider name"}
            },
            "required": ["provider"]
        },
        handler=lambda args: credential_rotate(args.get("provider", ""))
    )
    
    register_tool(
        name="credential_test",
        description="Test a credential",
        parameters={
            "type": "object",
            "properties": {
                "credential_id": {"type": "string", "description": "Credential ID"}
            },
            "required": ["credential_id"]
        },
        handler=lambda args: credential_test(args.get("credential_id", ""))
    )
    
    register_tool(
        name="credential_export",
        description="Export credentials (without secrets)",
        parameters={
            "type": "object",
            "properties": {
                "output_path": {"type": "string", "description": "Output file path", "default": ""}
            }
        },
        handler=lambda args: credential_export(args.get("output_path", ""))
    )
