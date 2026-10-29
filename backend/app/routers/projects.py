"""Projects, episodes, shots, and their media uploads."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from .. import crud
from ..schemas import (
    EpisodeCreate, EpisodeUpdate, ProjectCreate, ProjectUpdate,
    ReorderRequest, ShotCreate, ShotUpdate,
)
from ..storage import episode_dir, shots_dir

router = APIRouter(prefix="/api", tags=["projects"])


def _save_upload(file: UploadFile, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as fh:
        shutil.copyfileobj(file.file, fh)
    return dest


def _require_project(pid: int) -> dict:
    p = crud.get_project(pid)
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def _require_episode(eid: int) -> dict:
    e = crud.get_episode(eid)
    if not e:
        raise HTTPException(404, "Episode not found")
    return e


def _require_shot(sid: int) -> dict:
    s = crud.get_shot(sid)
    if not s:
        raise HTTPException(404, "Shot not found")
    return s


# --------------------------------------------------------------------------- #
# projects
# --------------------------------------------------------------------------- #

@router.get("/projects")
def list_projects():
    return crud.list_projects()


@router.post("/projects")
def create_project(body: ProjectCreate):
    return crud.create_project(body.model_dump())


@router.get("/projects/{pid}")
def get_project(pid: int):
    return _require_project(pid)


@router.patch("/projects/{pid}")
def update_project(pid: int, body: ProjectUpdate):
    _require_project(pid)
    return crud.update_project(pid, body.model_dump(exclude_none=True))


@router.delete("/projects/{pid}")
def delete_project(pid: int):
    _require_project(pid)
    crud.delete_project(pid)
    return {"ok": True}


# --------------------------------------------------------------------------- #
# episodes
# --------------------------------------------------------------------------- #

@router.get("/projects/{pid}/episodes")
def list_episodes(pid: int):
    _require_project(pid)
    return crud.list_episodes(pid)


@router.post("/projects/{pid}/episodes")
def create_episode(pid: int, body: EpisodeCreate):
    _require_project(pid)
    data = body.model_dump()
    data["project_id"] = pid
    return crud.create_episode(data)


@router.get("/episodes/{eid}")
def get_episode(eid: int):
    return _require_episode(eid)


@router.patch("/episodes/{eid}")
def update_episode(eid: int, body: EpisodeUpdate):
    _require_episode(eid)
    return crud.update_episode(eid, body.model_dump(exclude_none=True))


@router.delete("/episodes/{eid}")
def delete_episode(eid: int):
    _require_episode(eid)
    crud.delete_episode(eid)
    return {"ok": True}


@router.post("/episodes/{eid}/narration")
def upload_narration(eid: int, file: UploadFile = File(...)):
    ep = _require_episode(eid)
    proj = _require_project(ep["project_id"])
    ext = Path(file.filename or "narration.mp3").suffix or ".mp3"
    dest = episode_dir(proj["scp_number"], ep["part_number"]) / f"narration{ext}"
    _save_upload(file, dest)
    # New audio invalidates cached word timestamps.
    return crud.update_episode(
        eid, {"narration_audio_path": str(dest.resolve()), "narration_words": None}
    )


@router.post("/episodes/{eid}/music")
def upload_music(eid: int, file: UploadFile = File(...)):
    ep = _require_episode(eid)
    proj = _require_project(ep["project_id"])
    ext = Path(file.filename or "music.mp3").suffix or ".mp3"
    dest = episode_dir(proj["scp_number"], ep["part_number"]) / f"music{ext}"
    _save_upload(file, dest)
    return crud.update_episode(eid, {"music_path": str(dest.resolve())})


# --------------------------------------------------------------------------- #
# shots
# --------------------------------------------------------------------------- #

@router.get("/episodes/{eid}/shots")
def list_shots(eid: int):
    _require_episode(eid)
    return crud.list_shots(eid)


@router.post("/episodes/{eid}/shots")
def create_shot(eid: int, body: ShotCreate):
    _require_episode(eid)
    data = body.model_dump()
    data["episode_id"] = eid
    existing = crud.list_shots(eid)
    if not data.get("order_index"):
        data["order_index"] = len(existing)
    if data["shot_type"] == "text_card":
        data["status"] = "ready"
    return crud.create_shot(data)


@router.patch("/shots/{sid}")
def update_shot(sid: int, body: ShotUpdate):
    _require_shot(sid)
    return crud.update_shot(sid, body.model_dump(exclude_none=True))


@router.delete("/shots/{sid}")
def delete_shot(sid: int):
    _require_shot(sid)
    crud.delete_shot(sid)
    return {"ok": True}


@router.post("/episodes/{eid}/shots/reorder")
def reorder_shots(eid: int, body: ReorderRequest):
    _require_episode(eid)
    for idx, sid in enumerate(body.shot_ids):
        crud.update_shot(sid, {"order_index": idx})
    return crud.list_shots(eid)


@router.post("/shots/{sid}/asset")
def upload_shot_asset(sid: int, file: UploadFile = File(...)):
    shot = _require_shot(sid)
    ep = _require_episode(shot["episode_id"])
    proj = _require_project(ep["project_id"])
    sdir = shots_dir(proj["scp_number"], ep["part_number"])
    # Keep previous takes so the user can pick the best one later.
    try:
        takes = json.loads(shot["takes"]) if shot.get("takes") else []
    except (ValueError, json.JSONDecodeError):
        takes = []
    ext = Path(file.filename or "asset").suffix or ".bin"
    dest = sdir / f"shot{sid}_take{len(takes) + 1}{ext}"
    _save_upload(file, dest)
    takes.append(str(dest.resolve()))
    return crud.update_shot(
        sid,
        {
            "asset_path": str(dest.resolve()),
            "takes": json.dumps(takes),
            "selected_take": len(takes) - 1,
            "shot_type": "uploaded_media",
            "status": "ready",
        },
    )
