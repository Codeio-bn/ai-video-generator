"""Projects, episodes, shots, and their media uploads."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

import json as _json

from .. import crud, tts
from ..llm import LLMError, generate_episodes
from ..schemas import (
    EpisodeCreate, EpisodeUpdate, ProjectCreate, ProjectUpdate,
    ReorderRequest, ScriptGenRequest, ShotCreate, ShotUpdate, TTSRequest,
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


@router.post("/projects/{pid}/generate-script")
def generate_script(pid: int, body: ScriptGenRequest):
    """Milestone 2: split a source story into episode drafts with Gemini."""
    project = _require_project(pid)

    # Persist the pasted story onto the project so it survives a reload.
    source = (body.source_text or project.get("source_text") or "").strip()
    if body.source_text and body.source_text != project.get("source_text"):
        crud.update_project(pid, {"source_text": body.source_text})
        project = crud.get_project(pid)
    if not source:
        raise HTTPException(400, "Paste the SCP source story before generating.")

    try:
        result = generate_episodes(project, source, body.num_parts, body.guidance)
    except LLMError as exc:
        # Expected, user-facing failures (missing key, blocked, bad response).
        raise HTTPException(400, str(exc))
    except Exception as exc:  # noqa: BLE001 - unexpected; still surface cleanly
        raise HTTPException(502, f"Gemini request failed: {exc}")

    if body.replace:
        for ep in crud.list_episodes(pid):
            crud.delete_episode(ep["id"])
        start = 1
    else:
        existing = crud.list_episodes(pid)
        start = (max((e["part_number"] for e in existing), default=0)) + 1

    created = []
    for offset, ep in enumerate(result.episodes):
        part = start + offset
        created.append(
            crud.create_episode(
                {
                    "project_id": pid,
                    "part_number": part,
                    "title": ep["title"] or f"Part {part}",
                    "hook": ep["hook"],
                    "previously": ep["previously"] if part > 1 else "",
                    "narration_script": ep["narration_script"],
                    "cliffhanger": ep["cliffhanger"],
                    "status": "draft",
                }
            )
        )

    crud.add_cost(
        pid,
        provider="gemini",
        model=result.model,
        amount=result.cost,
        note=(
            f"script gen: {len(created)} episodes, "
            f"{result.prompt_tokens}+{result.output_tokens} tokens (est.)"
        ),
    )

    return {
        "episodes": created,
        "model": result.model,
        "cost": round(result.cost, 4),
        "prompt_tokens": result.prompt_tokens,
        "output_tokens": result.output_tokens,
    }


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


@router.post("/episodes/{eid}/tts")
def generate_narration(eid: int, body: TTSRequest):
    """Milestone 3: synthesize narration from the script with local Kokoro TTS."""
    ep = _require_episode(eid)
    proj = _require_project(ep["project_id"])
    text = tts.assemble_script(ep)
    if not text:
        raise HTTPException(400, "Write the hook / narration / cliffhanger first.")
    voice = body.voice or proj.get("narrator_voice") or ""
    dest = episode_dir(proj["scp_number"], ep["part_number"]) / "narration.wav"
    try:
        result = tts.synthesize(text, dest, voice, body.lang_code)
    except tts.TTSError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:  # noqa: BLE001 - surface unexpected failures cleanly
        raise HTTPException(502, f"TTS failed: {exc}")
    return crud.update_episode(
        eid,
        {
            "narration_audio_path": result.audio_path,
            "narration_words": _json.dumps(result.words),
        },
    )


@router.post("/episodes/{eid}/estimate-timings")
def estimate_timings(eid: int):
    """Estimate caption word-timings from the narration audio's duration.

    Lets burned-in captions work without faster-whisper (e.g. on Python 3.15):
    the words come from the script, their timing from the audio length.
    """
    ep = _require_episode(eid)
    audio = ep.get("narration_audio_path")
    if not audio or not Path(audio).exists():
        raise HTTPException(400, "Set or generate narration audio first.")
    text = tts.assemble_script(ep)
    if not text:
        raise HTTPException(400, "Write the script text first so words can be timed.")
    duration = tts.probe_duration(audio)
    if duration <= 0:
        raise HTTPException(400, "Could not read the narration audio duration.")
    words = tts.estimate_word_timings(text, duration)
    return crud.update_episode(eid, {"narration_words": _json.dumps(words)})


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
