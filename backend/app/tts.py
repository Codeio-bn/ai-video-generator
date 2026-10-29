"""Narration voiceover via OpenAI text-to-speech.

A thin wrapper over OpenAI's /audio/speech endpoint (plain ``requests``). Chosen
over local Kokoro because it needs no binary wheels — it works on Python 3.15,
where torch/onnx have none — and it reuses the OpenAI key already configured for
the script writer.
"""

from __future__ import annotations

from pathlib import Path

import requests

from .config import get_secret

_URL = "https://api.openai.com/v1/audio/speech"
DEFAULT_MODEL = "gpt-4o-mini-tts"
DEFAULT_VOICE = "onyx"          # deep, steady — suits SCP narration
_TIMEOUT = 90

# OpenAI TTS voices (as of the current API).
VOICES = ["alloy", "ash", "ballad", "coral", "echo", "fable",
          "nova", "onyx", "sage", "shimmer"]


class TTSError(RuntimeError):
    """User-facing failure while synthesizing narration."""


def model_name() -> str:
    return get_secret("OPENAI_TTS_MODEL") or DEFAULT_MODEL


def available() -> tuple[bool, str]:
    if not get_secret("OPENAI_API_KEY"):
        return False, "No OpenAI API key saved — narration needs one."
    return True, f"Ready (voice {get_secret('OPENAI_TTS_VOICE') or DEFAULT_VOICE})."


def synthesize(text: str, dest: Path, *, voice: str = "") -> Path:
    """Render `text` to an mp3 at `dest`. Raises TTSError on failure."""
    key = get_secret("OPENAI_API_KEY")
    if not key:
        raise TTSError("No OpenAI API key saved. Add one under Settings.")
    if not (text or "").strip():
        raise TTSError("No narration text to speak.")

    body = {
        "model": model_name(),
        "voice": voice or get_secret("OPENAI_TTS_VOICE") or DEFAULT_VOICE,
        "input": text.strip(),
        "response_format": "mp3",
    }
    try:
        resp = requests.post(_URL, headers={"Authorization": f"Bearer {key}"},
                             json=body, timeout=_TIMEOUT)
    except requests.RequestException as exc:
        raise TTSError(f"Could not reach OpenAI TTS: {exc}") from exc
    if resp.status_code != 200:
        try:
            msg = (resp.json().get("error") or {}).get("message") or resp.text
        except ValueError:
            msg = resp.text or resp.reason
        raise TTSError(f"OpenAI TTS returned HTTP {resp.status_code}: {msg}")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest
