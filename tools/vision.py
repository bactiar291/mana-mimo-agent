"""
vision.py — Vision/Image Analysis Tools
Analyze images, capture screenshots, extract text via OCR.
"""
import json
import os
import hashlib
import shutil
import subprocess
from typing import Any, Dict
from datetime import datetime


def _image_metadata(image_path: str) -> Dict[str, Any]:
    stat = os.stat(image_path)
    metadata: Dict[str, Any] = {
        "file": image_path,
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }
    try:
        from PIL import Image
        with Image.open(image_path) as image:
            metadata["dimensions"] = image.size
            metadata["format"] = image.format
            metadata["mode"] = image.mode
    except Exception:
        pass
    return metadata


def _metadata_only_question(question: str) -> bool:
    text = (question or "").strip().lower()
    if not text:
        return True
    metadata_terms = (
        "metadata", "info", "file info", "dimensions", "dimension", "ukuran",
        "resolusi", "format", "size", "stat",
    )
    analysis_terms = (
        "describe", "jelaskan", "analisa", "analyze", "apa isi", "what is",
        "read", "ocr", "text", "teks", "caption",
    )
    return any(term in text for term in metadata_terms) and not any(term in text for term in analysis_terms)

def vision_analyze(image_url: str = "", image_path: str = "", question: str = "Describe this image") -> str:
    """Analyze an image from URL or local path."""
    try:
        if not image_url and not image_path:
            return json.dumps({"success": False, "error": "Provide image_url or image_path"})

        if image_url and not image_path:
            return json.dumps({
                "success": False,
                "error": "Image URL analysis is not implemented without a vision model or downloader",
                "reason": "not_implemented",
                "url": image_url,
                "question": question,
            })

        if not os.path.exists(image_path):
            return json.dumps({"success": False, "error": f"Image not found: {image_path}"})

        metadata = _image_metadata(image_path)
        if _metadata_only_question(question):
            return json.dumps({
                "success": True,
                "analysis_type": "metadata",
                **metadata,
            })

        return json.dumps({
            "success": False,
            "error": "Image content analysis requires a configured vision model",
            "reason": "not_implemented",
            "question": question,
            "metadata": metadata,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def vision_screenshot(url: str = "", output_path: str = "/tmp/screenshot.png") -> str:
    """Capture screenshot of a URL."""
    try:
        if not url:
            return json.dumps({"success": False, "error": "URL required"})
        try:
            from lib import browser_engine
        except ImportError:
            import browser_engine

        open_result = json.loads(browser_engine.browser_open(url, wait=3))
        if open_result.get("error"):
            return json.dumps({"success": False, "error": open_result.get("error"), "url": url})

        screenshot_result = json.loads(browser_engine.browser_screenshot(output_path))
        path = screenshot_result.get("screenshot") or output_path
        if screenshot_result.get("error"):
            return json.dumps({"success": False, "error": screenshot_result.get("error"), "url": url})
        if not os.path.isfile(path):
            return json.dumps({"success": False, "error": f"Screenshot file not created: {path}", "url": url})

        return json.dumps({
            "success": True,
            "url": url,
            "output": path,
            "size": os.path.getsize(path),
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def vision_ocr(image_path: str = "") -> str:
    """Extract text from image via OCR."""
    try:
        if not image_path or not os.path.exists(image_path):
            return json.dumps({"success": False, "error": "Image not found"})

        metadata = _image_metadata(image_path)
        tesseract = shutil.which("tesseract")
        if not tesseract:
            return json.dumps({
                "success": False,
                "error": "OCR engine not available. Install tesseract to enable vision_ocr.",
                "reason": "not_implemented",
                "metadata": metadata,
            })

        result = subprocess.run(
            [tesseract, image_path, "stdout"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return json.dumps({
                "success": False,
                "error": result.stderr.strip() or "Tesseract OCR failed",
                "metadata": metadata,
            })

        return json.dumps({
            "success": True,
            "file": image_path,
            "text": result.stdout,
            "metadata": metadata,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def vision_compare(image1: str, image2: str) -> str:
    """Compare two images."""
    try:
        if not os.path.exists(image1) or not os.path.exists(image2):
            return json.dumps({"success": False, "error": "One or both images not found"})
        
        stat1 = os.stat(image1)
        stat2 = os.stat(image2)
        
        with open(image1, "rb") as file1:
            hash1 = hashlib.sha256(file1.read()).hexdigest()
        with open(image2, "rb") as file2:
            hash2 = hashlib.sha256(file2.read()).hexdigest()
        result = {
            "success": True,
            "image1": {"path": image1, "size": stat1.st_size},
            "image2": {"path": image2, "size": stat2.st_size},
            "same_size": stat1.st_size == stat2.st_size,
            "same_sha256": hash1 == hash2,
            "sha256_1": hash1,
            "sha256_2": hash2,
        }
        try:
            from PIL import Image
            with Image.open(image1) as img1, Image.open(image2) as img2:
                result["image1"]["dimensions"] = img1.size
                result["image2"]["dimensions"] = img2.size
                result["same_dimensions"] = img1.size == img2.size
        except Exception:
            pass
        return json.dumps(result)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_vision_tools(register_tool):
    """Register vision tools."""
    register_tool(
        name="vision_analyze",
        description="Analyze an image from URL or local path",
        parameters={
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "Image URL", "default": ""},
                "image_path": {"type": "string", "description": "Local image path", "default": ""},
                "question": {"type": "string", "description": "Question about the image", "default": "Describe this image"}
            }
        },
        handler=lambda args: vision_analyze(args.get("image_url", ""), args.get("image_path", ""), args.get("question", "Describe this image"))
    )
    
    register_tool(
        name="vision_screenshot",
        description="Capture screenshot of a URL",
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to screenshot"},
                "output_path": {"type": "string", "description": "Output file path", "default": "/tmp/screenshot.png"}
            },
            "required": ["url"]
        },
        handler=lambda args: vision_screenshot(args.get("url", ""), args.get("output_path", "/tmp/screenshot.png"))
    )
    
    register_tool(
        name="vision_ocr",
        description="Extract text from image via OCR",
        parameters={
            "type": "object",
            "properties": {
                "image_path": {"type": "string", "description": "Image file path"}
            },
            "required": ["image_path"]
        },
        handler=lambda args: vision_ocr(args.get("image_path", ""))
    )
    
    register_tool(
        name="vision_compare",
        description="Compare two images",
        parameters={
            "type": "object",
            "properties": {
                "image1": {"type": "string", "description": "First image path"},
                "image2": {"type": "string", "description": "Second image path"}
            },
            "required": ["image1", "image2"]
        },
        handler=lambda args: vision_compare(args.get("image1", ""), args.get("image2", ""))
    )
