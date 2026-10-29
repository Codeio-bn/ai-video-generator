"""File serving, system status, and settings."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .. import captions as captions_mod
from .. import llm
from .. import tts
from ..config import (
    PROJECTS_DIR, ffmpeg_path, ffprobe_path, get_secret, save_secret,
)

router = APIRouter(prefix="/api", tags=["system"])

# Files may also be served out of the vendored tools dir? No — only project assets.
_ALLOWED_ROOTS = [PROJECTS_DIR.resolve()]


@router.get("/file")
def serve_file(path: str = Query(...)):
    """Serve a project asset by absolute path, sandboxed to projects/."""
    p = Path(path).resolve()
    if not any(_is_within(p, root) for root in _ALLOWED_ROOTS):
        raise HTTPException(403, "Path outside the projects directory")
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(str(p))


def _is_within(p: Path, root: Path) -> bool:
    try:
        p.relative_to(root)
        return True
    except ValueError:
        return False


@router.get("/system")
def system_status():
    whisper_ok, whisper_why = captions_mod.whisper_available()
    kokoro_ok, kokoro_why = tts.kokoro_available()
    return {
        "ffmpeg": ffmpeg_path(),
        "ffprobe": ffprobe_path(),
        "ffmpeg_ok": bool(ffmpeg_path() and ffprobe_path()),
        "whisper_ok": whisper_ok,
        "whisper_detail": whisper_why,
        "gemini_key_set": bool(get_secret("GEMINI_API_KEY")),
        "groq_key_set": bool(get_secret("GROQ_API_KEY")),
        "openai_key_set": bool(get_secret("OPENAI_API_KEY")),
        "llm_provider": llm.provider_name(),
        "llm_model": llm.model_name(),
        "llm_key_set": bool(
            get_secret({
                "groq": "GROQ_API_KEY",
                "openai": "OPENAI_API_KEY",
            }.get(llm.provider_name(), "GEMINI_API_KEY"))
        ),
        "gemini_model": llm.model_name(),  # kept for back-compat
        "kokoro_ok": kokoro_ok,
        "kokoro_detail": kokoro_why,
        "tts_voices": tts.VOICES,
    }


class SecretBody(BaseModel):
    key: str
    value: str


@router.post("/settings/secret")
def set_secret(body: SecretBody):
    save_secret(body.key, body.value)
    return {"ok": True}


@router.post("/settings/test-gemini")
def test_gemini():
    return llm.check_connection()
