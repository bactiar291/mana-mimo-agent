"""
context_compressor.py — Context Compression (Hermes-inspired)
Manage context window and compress conversations.
"""
import json
import os
import re
from typing import Any, Dict, List, Optional
from datetime import datetime

def context_compress(text: str, ratio: float = 0.5, method: str = "smart") -> str:
    """Compress text to reduce token count."""
    try:
        if not text:
            return json.dumps({"success": False, "error": "No text provided"})
        
        original_length = len(text)
        
        if method == "smart":
            # Smart compression: keep important parts
            lines = text.split("\n")
            important_lines = []
            
            for line in lines:
                # Keep lines with important keywords
                if any(keyword in line.lower() for keyword in ["error", "success", "failed", "result", "output", "status"]):
                    important_lines.append(line)
                # Keep short lines (likely important)
                elif len(line.strip()) < 50:
                    important_lines.append(line)
            
            compressed = "\n".join(important_lines)
        
        elif method == "truncate":
            # Simple truncation
            target_length = int(original_length * ratio)
            compressed = text[:target_length] + "\n... [truncated]"
        
        elif method == "summarize":
            # Extract key points
            sentences = re.split(r'[.!?]+', text)
            key_sentences = [s.strip() for s in sentences if len(s.strip()) > 20][:5]
            compressed = ". ".join(key_sentences) + "."
        
        else:
            compressed = text
        
        compressed_length = len(compressed)
        compression_ratio = compressed_length / original_length if original_length > 0 else 1.0
        
        return json.dumps({
            "success": True,
            "original_length": original_length,
            "compressed_length": compressed_length,
            "compression_ratio": compression_ratio,
            "method": method,
            "compressed_text": compressed
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def context_expand(text: str, context: str = "") -> str:
    """Expand text with additional context."""
    try:
        if context:
            expanded = f"{text}\n\nContext:\n{context}"
        else:
            expanded = text
        
        return json.dumps({
            "success": True,
            "original_length": len(text),
            "expanded_length": len(expanded),
            "expanded_text": expanded
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def context_summarize(text: str, max_length: int = 200) -> str:
    """Summarize text to a maximum length."""
    try:
        if len(text) <= max_length:
            return json.dumps({
                "success": True,
                "original_length": len(text),
                "summary": text,
                "truncated": False
            })
        
        # Extract first N characters and add ellipsis
        summary = text[:max_length] + "..."
        
        return json.dumps({
            "success": True,
            "original_length": len(text),
            "summary_length": len(summary),
            "summary": summary,
            "truncated": True
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def context_prune(messages: str, keep_last: int = 10) -> str:
    """Prune messages to keep only recent ones."""
    try:
        messages_list = json.loads(messages) if isinstance(messages, str) else messages
        
        if len(messages_list) <= keep_last:
            return json.dumps({
                "success": True,
                "original_count": len(messages_list),
                "pruned_count": len(messages_list),
                "messages": messages_list
            })
        
        pruned = messages_list[-keep_last:]
        
        return json.dumps({
            "success": True,
            "original_count": len(messages_list),
            "pruned_count": len(pruned),
            "messages": pruned
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def token_count(text: str) -> str:
    """Estimate token count."""
    try:
        # Rough estimation: 1 token ≈ 4 characters
        estimated_tokens = len(text) // 4
        
        return json.dumps({
            "success": True,
            "text_length": len(text),
            "estimated_tokens": estimated_tokens,
            "method": "character_ratio"
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def context_optimize(messages: str, max_tokens: int = 4000) -> str:
    """Optimize messages to fit within token limit."""
    try:
        messages_list = json.loads(messages) if isinstance(messages, str) else messages
        
        # Estimate tokens per message
        total_tokens = 0
        optimized = []
        
        for msg in messages_list:
            msg_tokens = len(json.dumps(msg)) // 4
            if total_tokens + msg_tokens <= max_tokens:
                optimized.append(msg)
                total_tokens += msg_tokens
            else:
                break
        
        return json.dumps({
            "success": True,
            "original_count": len(messages_list),
            "optimized_count": len(optimized),
            "estimated_tokens": total_tokens,
            "messages": optimized
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_context_compressor_tools(register_tool):
    """Register context compressor tools."""
    register_tool(
        name="context_compress",
        description="Compress text to reduce token count",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to compress"},
                "ratio": {"type": "number", "description": "Compression ratio", "default": 0.5},
                "method": {"type": "string", "description": "Method: smart, truncate, summarize", "default": "smart"}
            },
            "required": ["text"]
        },
        handler=lambda args: context_compress(args.get("text", ""), args.get("ratio", 0.5), args.get("method", "smart"))
    )
    
    register_tool(
        name="context_expand",
        description="Expand text with additional context",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to expand"},
                "context": {"type": "string", "description": "Additional context", "default": ""}
            },
            "required": ["text"]
        },
        handler=lambda args: context_expand(args.get("text", ""), args.get("context", ""))
    )
    
    register_tool(
        name="context_summarize",
        description="Summarize text to a maximum length",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to summarize"},
                "max_length": {"type": "integer", "description": "Max summary length", "default": 200}
            },
            "required": ["text"]
        },
        handler=lambda args: context_summarize(args.get("text", ""), args.get("max_length", 200))
    )
    
    register_tool(
        name="context_prune",
        description="Prune messages to keep only recent ones",
        parameters={
            "type": "object",
            "properties": {
                "messages": {"type": "string", "description": "JSON array of messages"},
                "keep_last": {"type": "integer", "description": "Number of messages to keep", "default": 10}
            },
            "required": ["messages"]
        },
        handler=lambda args: context_prune(args.get("messages", "[]"), args.get("keep_last", 10))
    )
    
    register_tool(
        name="token_count",
        description="Estimate token count",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to count tokens"}
            },
            "required": ["text"]
        },
        handler=lambda args: token_count(args.get("text", ""))
    )
    
    register_tool(
        name="context_optimize",
        description="Optimize messages to fit within token limit",
        parameters={
            "type": "object",
            "properties": {
                "messages": {"type": "string", "description": "JSON array of messages"},
                "max_tokens": {"type": "integer", "description": "Max token limit", "default": 4000}
            },
            "required": ["messages"]
        },
        handler=lambda args: context_optimize(args.get("messages", "[]"), args.get("max_tokens", 4000))
    )
