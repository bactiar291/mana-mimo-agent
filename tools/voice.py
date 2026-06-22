"""
voice.py — Voice/TTS Tools
Text-to-speech via edge-tts, audio transcription.
"""
import json
import os
import subprocess
import shutil
import tempfile
from typing import Any, Dict
from datetime import datetime


def _voice_enabled() -> bool:
    value = os.environ.get("MIMO_VOICE_ENABLED", "1").strip().lower()
    return value not in {"0", "false", "no", "off", "disabled"}


def _audio_metadata(audio_path: str) -> Dict[str, Any]:
    stat = os.stat(audio_path)
    return {
        "file": audio_path,
        "extension": os.path.splitext(audio_path)[1],
        "size": stat.st_size,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
    }


def voice_tts(text: str, output_path: str = "/tmp/output.mp3", voice: str = "id-ID-ArdiNeural") -> str:
    """Convert text to speech via edge-tts."""
    try:
        if not _voice_enabled():
            return json.dumps({"success": False, "error": "Voice tools disabled by MIMO_VOICE_ENABLED=0"})
        if not text:
            return json.dumps({"success": False, "error": "Text required"})

        edge_tts = shutil.which("edge-tts")
        if not edge_tts:
            return json.dumps({"success": False, "error": "edge-tts not installed. Run: pip install edge-tts"})

        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        cmd = [edge_tts, "--voice", voice, "--text", text, "--write-media", output_path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return json.dumps({
                "success": True,
                "output": output_path,
                "voice": voice,
                "text_length": len(text),
                "autoplay": False,
                "message": f"TTS saved to {output_path}"
            })
        else:
            return json.dumps({"success": False, "error": result.stderr.strip() or "TTS output file was not created"})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def voice_list() -> str:
    """List available TTS voices."""
    try:
        if not _voice_enabled():
            return json.dumps({"success": False, "error": "Voice tools disabled by MIMO_VOICE_ENABLED=0"})
        edge_tts = shutil.which("edge-tts")
        if not edge_tts:
            return json.dumps({"success": False, "error": "edge-tts not installed. Run: pip install edge-tts"})
        result = subprocess.run([edge_tts, "--list-voices"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            voices = []
            for line in result.stdout.split("\n"):
                if "Name:" in line:
                    voices.append(line.strip())
            return json.dumps({"success": True, "voices": voices[:20], "count": len(voices)})
        else:
            return json.dumps({"success": False, "error": result.stderr})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def voice_transcribe(audio_path: str = "") -> str:
    """Transcribe audio file."""
    try:
        if not _voice_enabled():
            return json.dumps({"success": False, "error": "Voice tools disabled by MIMO_VOICE_ENABLED=0"})
        if not audio_path or not os.path.exists(audio_path):
            return json.dumps({"success": False, "error": "Audio file not found"})

        metadata = _audio_metadata(audio_path)
        whisper = shutil.which("whisper")
        if not whisper:
            return json.dumps({
                "success": False,
                "error": "Transcription engine not available. Install openai-whisper CLI to enable voice_transcribe.",
                "reason": "not_implemented",
                "metadata": metadata,
            })

        with tempfile.TemporaryDirectory(prefix="mimo_whisper_") as tmpdir:
            result = subprocess.run(
                [
                    whisper,
                    audio_path,
                    "--model", "base",
                    "--output_format", "txt",
                    "--output_dir", tmpdir,
                ],
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode != 0:
                return json.dumps({
                    "success": False,
                    "error": result.stderr.strip() or "Whisper transcription failed",
                    "metadata": metadata,
                })
            transcript = ""
            for filename in os.listdir(tmpdir):
                if filename.endswith(".txt"):
                    with open(os.path.join(tmpdir, filename), "r", encoding="utf-8", errors="replace") as file_handle:
                        transcript = file_handle.read()
                    break
            if not transcript.strip():
                transcript = result.stdout.strip()

        return json.dumps({
            "success": True,
            "file": audio_path,
            "text": transcript,
            "metadata": metadata,
        })
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def voice_info(audio_path: str = "") -> str:
    """Get audio file info."""
    try:
        if not audio_path or not os.path.exists(audio_path):
            return json.dumps({"success": False, "error": "Audio file not found"})

        return json.dumps({"success": True, **_audio_metadata(audio_path)})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})

def register_voice_tools(register_tool):
    """Register voice tools."""
    if not _voice_enabled():
        return 0
    register_tool(
        name="voice_tts",
        description="Convert text to speech via edge-tts",
        parameters={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to convert"},
                "output_path": {"type": "string", "description": "Output audio path", "default": "/tmp/output.mp3"},
                "voice": {"type": "string", "description": "Voice name", "default": "id-ID-ArdiNeural"}
            },
            "required": ["text"]
        },
        handler=lambda args: voice_tts(args.get("text", ""), args.get("output_path", "/tmp/output.mp3"), args.get("voice", "id-ID-ArdiNeural"))
    )
    
    register_tool(
        name="voice_list",
        description="List available TTS voices",
        parameters={"type": "object", "properties": {}},
        handler=lambda args: voice_list()
    )
    
    register_tool(
        name="voice_transcribe",
        description="Transcribe audio file",
        parameters={
            "type": "object",
            "properties": {
                "audio_path": {"type": "string", "description": "Audio file path"}
            },
            "required": ["audio_path"]
        },
        handler=lambda args: voice_transcribe(args.get("audio_path", ""))
    )
    
    register_tool(
        name="voice_info",
        description="Get audio file info",
        parameters={
            "type": "object",
            "properties": {
                "audio_path": {"type": "string", "description": "Audio file path"}
            },
            "required": ["audio_path"]
        },
        handler=lambda args: voice_info(args.get("audio_path", ""))
    )

    return 4
