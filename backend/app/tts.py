"""Text-to-speech provider seam (Milestone 3: narration audio).

Like the LLM seam, the app talks only to this module, never to a vendor SDK, so
the local-Kokoro path here can later be swapped for a cloud voice without
touching the routers.

Kokoro runs locally through ONNX/torch, whose wheels do not exist for every
brand-new Python yet (same story as the caption engine). So every entry point
degrades gracefully: if Kokoro can't load, narration can still be uploaded by
hand (Milestone 1) and caption word-timings can still be *estimated* from an
audio file's duration — which lets burned-in captions work even when neither
Kokoro nor faster-whisper is installed.
"""

from __future__ import annotations

import re
import wave
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .config import ffprobe_path

SAMPLE_RATE = 24000  # Kokoro's native output rate

# Known Kokoro voices, grouped for the UI. The first letter encodes the language
# pack: a=American English, b=British English.
VOICES = [
    "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky",
    "am_adam", "am_michael", "am_eric", "am_liam", "am_onyx",
    "bf_emma", "bf_isabella", "bm_george", "bm_lewis",
]
DEFAULT_VOICE = "af_heart"


class TTSError(RuntimeError):
    """Raised with a user-facing message when synthesis fails."""


@dataclass
class TTSResult:
    audio_path: str
    duration: float
    words: list[dict] = field(default_factory=list)
    voice: str = ""


def kokoro_available() -> tuple[bool, str]:
    try:
        import kokoro  # noqa: F401

        return True, ""
    except Exception as exc:  # pragma: no cover - env dependent
        return False, f"{type(exc).__name__}: {exc}"


def resolve_voice(preferred: str = "") -> str:
    """Pick a usable voice id from a free-text field like 'Kokoro: am_adam'."""
    text = (preferred or "").strip().lower()
    for v in VOICES:
        if v in text:
            return v
    # bare id already?
    if re.fullmatch(r"[ab][fm]_[a-z]+", text):
        return text
    return DEFAULT_VOICE


# --------------------------------------------------------------------------- #
# script assembly + word-timing estimate (no heavy deps)
# --------------------------------------------------------------------------- #

def assemble_script(episode: dict) -> str:
    """The spoken text for an episode: hook, (recap), narration, cliffhanger."""
    parts = [episode.get("hook", "")]
    if (episode.get("part_number") or 1) > 1:
        parts.append(episode.get("previously", ""))
    parts += [episode.get("narration_script", ""), episode.get("cliffhanger", "")]
    return "\n".join(p.strip() for p in parts if p and p.strip())


def estimate_word_timings(text: str, duration: float) -> list[dict]:
    """Spread words across `duration`, weighting by length and punctuation.

    Not an acoustic alignment — a plausible karaoke timing good enough to drive
    burned-in captions and shot syncing when no aligner is available.
    """
    tokens = text.split()
    if not tokens or duration <= 0:
        return []
    weights: list[float] = []
    for tok in tokens:
        core = re.sub(r"[^\w']", "", tok)
        w = max(len(core), 1) + 2.0
        if tok.endswith((".", "!", "?", ":", ";", "…")):
            w += 6.0
        elif tok.endswith((",", "—", "–", ")")):
            w += 3.0
        weights.append(w)
    total = sum(weights)
    words: list[dict] = []
    t = 0.0
    for tok, w in zip(tokens, weights):
        span = duration * w / total
        words.append(
            {"word": tok, "start": round(t, 3), "end": round(t + span, 3)}
        )
        t += span
    return words


# --------------------------------------------------------------------------- #
# audio probing / writing (stdlib only)
# --------------------------------------------------------------------------- #

def probe_duration(path: str | Path) -> float:
    """Audio duration in seconds. Tries a WAV header first, then ffprobe."""
    p = Path(path)
    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as w:
                return w.getnframes() / float(w.getframerate() or SAMPLE_RATE)
        except (wave.Error, OSError):
            pass
    ffprobe = ffprobe_path()
    if ffprobe:
        import subprocess

        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        try:
            return float(proc.stdout.strip())
        except (ValueError, AttributeError):
            return 0.0
    return 0.0


def _write_wav_from_floats(samples, out_path: Path, sample_rate: int) -> float:
    """Write a mono 16-bit PCM WAV from a float array in [-1, 1]. Returns secs."""
    import numpy as np

    arr = np.asarray(samples, dtype="float32").reshape(-1)
    pcm = np.clip(arr, -1.0, 1.0)
    pcm = (pcm * 32767.0).astype("<i2")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return len(pcm) / float(sample_rate)


# --------------------------------------------------------------------------- #
# Kokoro synthesis
# --------------------------------------------------------------------------- #

@lru_cache(maxsize=2)
def _pipeline(lang_code: str):
    from kokoro import KPipeline

    return KPipeline(lang_code=lang_code)


def synthesize(text: str, out_path: Path, voice: str = "",
               lang_code: str = "") -> TTSResult:
    """Synthesize narration with Kokoro and estimate per-word timings.

    Raises TTSError (user-facing) if Kokoro is unavailable or synthesis fails.
    """
    text = (text or "").strip()
    if not text:
        raise TTSError("There is no script text to narrate yet.")

    ok, why = kokoro_available()
    if not ok:
        raise TTSError(
            "Local Kokoro TTS is not installed in this environment "
            f"({why}). You can still upload narration audio by hand. "
            "On Python 3.10–3.12, install it with: pip install kokoro soundfile."
        )

    voice = resolve_voice(voice)
    lang = lang_code or voice[0]  # 'a' / 'b' prefix encodes the language pack

    try:
        import numpy as np

        pipeline = _pipeline(lang)
        chunks = []
        for _graphemes, _phonemes, audio in pipeline(text, voice=voice):
            chunks.append(np.asarray(audio, dtype="float32").reshape(-1))
        if not chunks:
            raise TTSError("Kokoro produced no audio for this text.")
        full = np.concatenate(chunks)
    except TTSError:
        raise
    except Exception as exc:  # pragma: no cover - env dependent
        raise TTSError(f"Kokoro synthesis failed: {type(exc).__name__}: {exc}") from exc

    duration = _write_wav_from_floats(full, out_path, SAMPLE_RATE)
    words = estimate_word_timings(text, duration)
    return TTSResult(str(out_path.resolve()), duration, words, voice)
