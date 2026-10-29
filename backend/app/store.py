"""Tiny JSON-file store for saved video projects.

One file per video at data/videos/<id>.json, with its assets (clips, narration,
final mp4) under data/videos/<id>/. No database — this is a local, single-user
tool, so flat JSON keeps it simple and inspectable. Writes are serialized with a
lock so the background producer thread and request threads don't clobber a file.
"""

from __future__ import annotations

import json
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from .config import VIDEOS_DIR

_lock = threading.RLock()


def _path(vid: str) -> Path:
    return VIDEOS_DIR / f"{vid}.json"


def asset_dir(vid: str) -> Path:
    d = VIDEOS_DIR / vid
    d.mkdir(parents=True, exist_ok=True)
    return d


def new_video(scp_ref: str) -> dict:
    vid = uuid.uuid4().hex[:12]
    video = {
        "id": vid,
        "scp_ref": scp_ref,
        "title": "",
        "authors": "",
        "source_url": "",
        "license": "CC BY-SA 3.0",
        "status": "draft",          # draft|ready|producing|done|error
        "progress": 0.0,
        "message": "",
        "error": "",
        "scenes": [],               # [{index,narration,visual,sound,duration,clip_path,status,cost}]
        "narration_path": None,
        "final_path": None,
        "final_duration": 0.0,
        "cost_total": 0.0,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    save(video)
    return video


def save(video: dict) -> dict:
    with _lock:
        _path(video["id"]).write_text(json.dumps(video, indent=2), encoding="utf-8")
    return video


def update(vid: str, **fields) -> Optional[dict]:
    """Merge top-level fields into a stored video (atomic under the lock)."""
    with _lock:
        video = get(vid)
        if not video:
            return None
        video.update(fields)
        _path(vid).write_text(json.dumps(video, indent=2), encoding="utf-8")
        return video


def get(vid: str) -> Optional[dict]:
    p = _path(vid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def list_all() -> list[dict]:
    out = []
    for p in VIDEOS_DIR.glob("*.json"):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    out.sort(key=lambda v: v.get("created_at", ""), reverse=True)
    return out


def delete(vid: str) -> None:
    with _lock:
        _path(vid).unlink(missing_ok=True)
        shutil.rmtree(VIDEOS_DIR / vid, ignore_errors=True)
