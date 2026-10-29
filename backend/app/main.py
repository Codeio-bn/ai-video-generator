"""SCP Video Studio — FastAPI entry point.

Run from the backend/ directory:
    uvicorn app.main:app --reload --port 8000

Flow: enter an SCP -> OpenAI writes a 30s / 5-6 scene script (review & edit) ->
Veo generates a clip per scene + OpenAI narrates -> FFmpeg assembles the MP4.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai_script, jobs, scp_source, store, tts, veo
from .config import VIDEOS_DIR, ffmpeg_path, ffprobe_path, get_secret, save_secret

app = FastAPI(title="SCP Video Studio", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# system / settings
# --------------------------------------------------------------------------- #

@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/system")
def system():
    script_ok, script_detail = ai_script.available()
    veo_ok, veo_detail = veo.available()
    tts_ok, tts_detail = tts.available()
    return {
        "ffmpeg_ok": bool(ffmpeg_path() and ffprobe_path()),
        "openai_key_set": bool(get_secret("OPENAI_API_KEY")),
        "gemini_key_set": bool(get_secret("GEMINI_API_KEY")),
        "script_ok": script_ok, "script_detail": script_detail,
        "script_model": ai_script.model_name(),
        "tts_ok": tts_ok, "tts_detail": tts_detail,
        "tts_voices": tts.VOICES,
        "veo_ok": veo_ok, "veo_detail": veo_detail,
        "veo_model": veo.model_name(),
        "veo_price_per_sec": veo.price_per_sec(),
        "veo_clip_seconds": veo.clip_seconds(),
    }


class SecretBody(BaseModel):
    key: str
    value: str


@app.post("/api/settings/secret")
def set_secret(body: SecretBody):
    save_secret(body.key, body.value)
    if body.key in ("GEMINI_API_KEY", "VEO_MODEL"):
        veo.clear_cache()
    return {"ok": True}


# --------------------------------------------------------------------------- #
# videos
# --------------------------------------------------------------------------- #

class CreateBody(BaseModel):
    scp_ref: str
    guidance: str = ""
    voice: str = ""


class ScenePatch(BaseModel):
    narration: str | None = None
    visual: str | None = None
    sound: str | None = None


class VideoPatch(BaseModel):
    title: str | None = None
    voice: str | None = None


def _require(vid: str) -> dict:
    v = store.get(vid)
    if not v:
        raise HTTPException(404, "Video not found")
    return v


def _scenes_from_script(result: ai_script.ScriptResult) -> list[dict]:
    return [
        {"index": i, "narration": s["narration"], "visual": s["visual"],
         "sound": s["sound"], "duration": 5.0, "clip_path": None,
         "narration_audio": None, "status": "pending", "cost": 0.0}
        for i, s in enumerate(result.scenes)
    ]


@app.get("/api/videos")
def list_videos():
    return store.list_all()


@app.post("/api/videos")
def create_video(body: CreateBody):
    ref = (body.scp_ref or "").strip()
    if not ref:
        raise HTTPException(400, "Enter an SCP number or URL.")
    try:
        src = scp_source.fetch(ref)
    except scp_source.SCPSourceError as exc:
        raise HTTPException(400, str(exc))
    try:
        result = ai_script.generate_script(src.text, guidance=body.guidance)
    except ai_script.ScriptError as exc:
        raise HTTPException(400, str(exc))

    video = store.new_video(ref)
    return store.update(
        video["id"],
        title=result.title or src.title,
        authors=src.authors, source_url=src.source_url, license=src.license,
        voice=body.voice, status="ready",
        scenes=_scenes_from_script(result),
        message=f"Script ready ({len(result.scenes)} scenes, {result.model}).",
    )


@app.get("/api/videos/{vid}")
def get_video(vid: str):
    return _require(vid)


@app.delete("/api/videos/{vid}")
def delete_video(vid: str):
    _require(vid)
    store.delete(vid)
    return {"ok": True}


@app.patch("/api/videos/{vid}")
def patch_video(vid: str, body: VideoPatch):
    _require(vid)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    return store.update(vid, **fields)


@app.patch("/api/videos/{vid}/scenes/{index}")
def patch_scene(vid: str, index: int, body: ScenePatch):
    video = _require(vid)
    scenes = video["scenes"]
    if index < 0 or index >= len(scenes):
        raise HTTPException(404, "Scene not found")
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    scenes[index].update(changes)
    return store.update(vid, scenes=scenes)


@app.post("/api/videos/{vid}/regenerate-script")
def regenerate_script(vid: str, body: CreateBody | None = None):
    video = _require(vid)
    try:
        src = scp_source.fetch(video["scp_ref"])
        result = ai_script.generate_script(
            src.text, guidance=(body.guidance if body else ""))
    except (scp_source.SCPSourceError, ai_script.ScriptError) as exc:
        raise HTTPException(400, str(exc))
    return store.update(
        vid, title=result.title or video.get("title") or src.title,
        scenes=_scenes_from_script(result), status="ready", error="",
        final_path=None, final_duration=0.0, cost_total=0.0,
        message=f"Script regenerated ({len(result.scenes)} scenes).",
    )


@app.post("/api/videos/{vid}/produce")
def produce(vid: str):
    video = _require(vid)
    if not video.get("scenes"):
        raise HTTPException(400, "Generate a script first.")
    ok, detail = veo.available()
    if not ok:
        raise HTTPException(400, detail)
    ok, detail = tts.available()
    if not ok:
        raise HTTPException(400, detail)
    return jobs.start_produce(vid)


# --------------------------------------------------------------------------- #
# file serving
# --------------------------------------------------------------------------- #

@app.get("/api/file")
def serve_file(path: str = Query(...)):
    p = Path(path).resolve()
    try:
        p.relative_to(VIDEOS_DIR.resolve())
    except ValueError:
        raise HTTPException(403, "Path outside the data directory")
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(str(p))


# Serve the built frontend if present (production single-command mode).
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="frontend")
