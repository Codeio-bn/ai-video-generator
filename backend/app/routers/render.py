"""Render orchestration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import crud, jobs
from ..schemas import RenderRequest

router = APIRouter(prefix="/api", tags=["render"])


@router.post("/episodes/{eid}/render")
def start_render(eid: int, body: RenderRequest):
    ep = crud.get_episode(eid)
    if not ep:
        raise HTTPException(404, "Episode not found")
    project = crud.get_project(ep["project_id"])
    options = dict(body.options or {})
    # Fill the target length from the project if the UI didn't override it.
    options.setdefault("target_length", project.get("target_episode_length", 61))
    job = jobs.start_render(eid, options)
    return job


@router.get("/jobs/{jid}")
def get_job(jid: int):
    job = crud.get_job(jid)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@router.get("/episodes/{eid}/latest-job")
def latest_job(eid: int):
    return crud.latest_job_for_episode(eid) or {}
