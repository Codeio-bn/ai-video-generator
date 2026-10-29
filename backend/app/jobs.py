"""Background job runner for renders.

Jobs persist in the render_jobs table and run on a thread pool, so progress
survives a browser refresh (the UI just polls GET /api/jobs/{id}). On startup
any job left 'running' from a previous process is marked interrupted.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from . import crud
from .database import get_conn
from .render import RenderError, RenderOptions, render_episode

_executor = ThreadPoolExecutor(max_workers=1)  # one heavy render at a time


def reset_stale_jobs() -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE render_jobs SET status='error', "
            "error='Interrupted: the app was restarted during this job.' "
            "WHERE status IN ('queued','running')"
        )
        conn.commit()


def start_render(episode_id: int, options: dict) -> dict:
    job = crud.create_job(episode_id, "render", json.dumps(options))
    _executor.submit(_run_render, job["id"], episode_id, options)
    return job


def _run_render(job_id: int, episode_id: int, options: dict) -> None:
    try:
        crud.update_job(job_id, status="running", progress=0.0, message="Starting")
        episode = crud.get_episode(episode_id)
        if not episode:
            raise RenderError("Episode not found.")
        project = crud.get_project(episode["project_id"])
        shots = crud.list_shots(episode_id)
        opts = RenderOptions.from_dict(options)

        def progress(p: float, msg: str) -> None:
            crud.update_job(job_id, progress=p, message=msg)

        result = render_episode(project, episode, shots, opts, progress)

        crud.update_job(
            job_id, status="done", progress=1.0,
            message="; ".join(result.warnings) if result.warnings else "Render complete",
            output_path=result.output_path,
        )
        crud.update_episode(
            episode_id,
            {"last_render_path": result.output_path, "status": "rendered"},
        )
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        crud.update_job(job_id, status="error", error=f"{type(exc).__name__}: {exc}")
