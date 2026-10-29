"""Paths, FFmpeg discovery, and the local API-key store.

Everything the app writes lives under the project root so the whole tool is
self-contained and portable:

    <root>/
        data/videos/<id>.json   one saved video project + its assets folder
        tools/ffmpeg/           vendored static FFmpeg build (gitignored)
        .secrets.json           API keys (gitignored, never in the bundle)
"""

from __future__ import annotations

import json
import os
import shutil
from functools import lru_cache
from pathlib import Path

# <root>/backend/app/config.py -> parents[2] == <root>
ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
VIDEOS_DIR = DATA_DIR / "videos"
TOOLS_DIR = ROOT_DIR / "tools"
SECRETS_PATH = ROOT_DIR / ".secrets.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)


def _find_binary(name: str) -> str | None:
    """Locate ffmpeg/ffprobe: env override -> vendored tools/ffmpeg -> PATH."""
    override = os.environ.get(f"{name.upper()}_PATH")
    if override and Path(override).exists():
        return str(Path(override).resolve())

    exe = f"{name}.exe" if os.name == "nt" else name
    ffmpeg_tools = TOOLS_DIR / "ffmpeg"
    if ffmpeg_tools.exists():
        candidates = list(ffmpeg_tools.glob(f"bin/{exe}")) + list(ffmpeg_tools.rglob(exe))
        for c in candidates:
            if c.is_file():
                return str(c.resolve())

    return shutil.which(name)


@lru_cache(maxsize=1)
def ffmpeg_path() -> str | None:
    return _find_binary("ffmpeg")


@lru_cache(maxsize=1)
def ffprobe_path() -> str | None:
    return _find_binary("ffprobe")


def require_ffmpeg() -> tuple[str, str]:
    """Return (ffmpeg, ffprobe) paths or raise a clear, user-facing error."""
    ff, fp = ffmpeg_path(), ffprobe_path()
    if not ff or not fp:
        raise RuntimeError(
            "FFmpeg was not found. Expected a vendored build under tools/ffmpeg/, "
            "an FFMPEG_PATH/FFPROBE_PATH environment variable, or ffmpeg on PATH. "
            "Run scripts/setup.sh (scripts\\setup.ps1 on Windows) to download it."
        )
    return ff, fp


# ---- lightweight local secrets store (API keys) -----------------------------

def load_secrets() -> dict:
    if SECRETS_PATH.exists():
        try:
            return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def save_secret(key: str, value: str) -> None:
    data = load_secrets()
    data[key] = value
    SECRETS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_secret(key: str) -> str | None:
    # An environment variable wins over the stored file.
    return os.environ.get(key) or load_secrets().get(key)
