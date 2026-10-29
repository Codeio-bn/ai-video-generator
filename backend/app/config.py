"""Application configuration and path / binary discovery.

Everything the app writes lives under the project root so the whole tool is
self-contained and portable:

    <root>/
        data/app.db             SQLite database
        projects/<scp>/...      per-project assets (audio, images, renders)
        tools/ffmpeg/           vendored static FFmpeg build
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
PROJECTS_DIR = ROOT_DIR / "projects"
TOOLS_DIR = ROOT_DIR / "tools"
DB_PATH = DATA_DIR / "app.db"
SECRETS_PATH = ROOT_DIR / ".secrets.json"

# Windows system fonts – used for caption burn-in (libass) and Pillow cards.
WINDOWS_FONTS_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

DATA_DIR.mkdir(parents=True, exist_ok=True)
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _find_binary(name: str) -> str | None:
    """Locate an ffmpeg/ffprobe binary.

    Order: explicit env override -> vendored tools/ffmpeg (recursive) -> PATH.
    Returns an absolute path string, or None if not found.
    """
    env_key = f"{name.upper()}_PATH"
    override = os.environ.get(env_key)
    if override and Path(override).exists():
        return str(Path(override).resolve())

    exe = f"{name}.exe" if os.name == "nt" else name
    ffmpeg_tools = TOOLS_DIR / "ffmpeg"
    if ffmpeg_tools.exists():
        # Prefer a shallow bin/ layout, else search the whole vendored tree.
        candidates = list(ffmpeg_tools.glob(f"bin/{exe}")) + list(
            ffmpeg_tools.rglob(exe)
        )
        for c in candidates:
            if c.is_file():
                return str(c.resolve())

    on_path = shutil.which(name)
    if on_path:
        return on_path
    return None


@lru_cache(maxsize=1)
def ffmpeg_path() -> str | None:
    return _find_binary("ffmpeg")


@lru_cache(maxsize=1)
def ffprobe_path() -> str | None:
    return _find_binary("ffprobe")


def require_ffmpeg() -> tuple[str, str]:
    """Return (ffmpeg, ffprobe) paths or raise a clear, user-facing error."""
    ff = ffmpeg_path()
    fp = ffprobe_path()
    if not ff or not fp:
        raise RuntimeError(
            "FFmpeg was not found. Expected a vendored build under tools/ffmpeg/, "
            "an FFMPEG_PATH/FFPROBE_PATH environment variable, or ffmpeg on PATH. "
            "Run the setup step in the README to download it."
        )
    return ff, fp


def find_system_font(preferred: list[str] | None = None) -> Path | None:
    """Return a path to a usable .ttf for Pillow text rendering."""
    preferred = preferred or [
        "arialbd.ttf",
        "Arial.ttf",
        "arial.ttf",
        "segoeui.ttf",
        "tahomabd.ttf",
    ]
    for name in preferred:
        p = WINDOWS_FONTS_DIR / name
        if p.exists():
            return p
    # Fall back to any ttf we can find.
    if WINDOWS_FONTS_DIR.exists():
        for p in WINDOWS_FONTS_DIR.glob("*.ttf"):
            return p
    return None


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
    # Environment variable wins over the stored file.
    return os.environ.get(key) or load_secrets().get(key)
