"""Per-project folder layout on disk.

    projects/<scp-number>/
        episodes/<n>/
            narration.*          narration audio
            music.*              background music bed
            shots/               uploaded / generated shot assets
            render/              working files + final.mp4
        uploads/                 loose uploaded media
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import PROJECTS_DIR


def _safe(name: str) -> str:
    """Make a filesystem-safe folder component from arbitrary text."""
    name = (name or "").strip()
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name)
    return name.strip("._-") or "untitled"


def project_dir(scp_number: str) -> Path:
    p = PROJECTS_DIR / _safe(scp_number)
    p.mkdir(parents=True, exist_ok=True)
    return p


def episode_dir(scp_number: str, part_number: int) -> Path:
    p = project_dir(scp_number) / "episodes" / str(part_number)
    p.mkdir(parents=True, exist_ok=True)
    return p


def shots_dir(scp_number: str, part_number: int) -> Path:
    p = episode_dir(scp_number, part_number) / "shots"
    p.mkdir(parents=True, exist_ok=True)
    return p


def render_dir(scp_number: str, part_number: int) -> Path:
    p = episode_dir(scp_number, part_number) / "render"
    p.mkdir(parents=True, exist_ok=True)
    return p


def uploads_dir(scp_number: str) -> Path:
    p = project_dir(scp_number) / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p
