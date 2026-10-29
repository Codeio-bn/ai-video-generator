"""Background job runner for renders.

Jobs persist in the render_jobs table and run on a thread pool, so progress
survives a browser refresh (the UI just polls GET /api/jobs/{id}). On startup
any job left 'running' from a previous process is marked interrupted.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor

from . import costs, crud, scp_source
from .database import get_conn
from .llm import LLMError, generate_full
from .render import RenderError, RenderOptions, render_episode

_executor = ThreadPoolExecutor(max_workers=1)  # one heavy render at a time
_gen_executor = ThreadPoolExecutor(max_workers=1)  # LLM auto-generation jobs


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


# --------------------------------------------------------------------------- #
# auto-generate (Milestone 4): fetch a real SCP -> episodes -> shot lists
# --------------------------------------------------------------------------- #

def start_autogen(project_id: int, options: dict) -> dict:
    # Don't stack: one generation runs at a time. If one is already active,
    # return it so the UI tracks that instead of queuing a duplicate.
    active = crud.latest_active_job("autogen")
    if active:
        return active
    job = crud.create_job(None, "autogen", json.dumps(options))
    _gen_executor.submit(_run_autogen, job["id"], project_id, options)
    return job


def _run_autogen(job_id: int, project_id: int, options: dict) -> None:
    try:
        crud.update_job(job_id, status="running", progress=0.02,
                        message="Starting")
        project = crud.get_project(project_id)
        if not project:
            raise RuntimeError("Project not found.")
        costs.require_budget(project, 0.0)  # block if already over the cap

        # 1. Fetch the real SCP article + attribution.
        crud.update_job(job_id, progress=0.05, message="Fetching SCP source")
        src = scp_source.fetch(options.get("scp_ref") or project["scp_number"])
        updates = {"source_text": src.text, "source_url": src.source_url}
        if not (project.get("title") or "").strip():
            updates["title"] = src.title
        if not (project.get("authors") or "").strip() and src.authors:
            updates["authors"] = src.authors
        if src.license:
            updates["license"] = src.license
        project = crud.update_project(project_id, updates)

        # 2. One Gemini request: retell into episodes AND design their shots.
        crud.update_job(job_id, progress=0.2,
                        message="Writing episodes & shots (one request)")
        want_shots = options.get("generate_shots", True)
        _t0 = time.monotonic()
        result = generate_full(
            project, src.text, options.get("num_parts", 0),
            options.get("guidance", ""), float(options.get("avg_shot_secs", 6.0)),
            status_cb=lambda m: crud.update_job(job_id, message=m),
        )
        gen_secs = time.monotonic() - _t0
        crud.add_cost(project_id, provider="gemini", model=result.model,
                      amount=result.cost,
                      note=f"autogen: {len(result.episodes)} episodes "
                           f"({result.prompt_tokens}+{result.output_tokens} tok)")

        # 3. Persist episodes + their shots.
        crud.update_job(job_id, progress=0.9, message="Saving episodes & shots")
        if options.get("replace", True):
            for ep in crud.list_episodes(project_id):
                crud.delete_episode(ep["id"])
        start = max((e["part_number"] for e in crud.list_episodes(project_id)),
                    default=0) + 1

        stype = options.get("shot_type", "veo_video")
        n_eps = shot_total = 0
        for offset, ep in enumerate(result.episodes):
            part = start + offset
            row = crud.create_episode({
                "project_id": project_id, "part_number": part,
                "title": ep["title"] or f"Part {part}", "hook": ep["hook"],
                "previously": ep["previously"] if part > 1 else "",
                "narration_script": ep["narration_script"],
                "cliffhanger": ep["cliffhanger"], "status": "draft",
            })
            n_eps += 1
            if want_shots:
                for j, shot in enumerate(ep.get("shots") or []):
                    crud.create_shot({
                        "episode_id": row["id"], "order_index": j,
                        "narration_excerpt": shot["narration_excerpt"],
                        "duration": shot["duration"], "shot_type": stype,
                        "prompt": shot["prompt"],
                        "camera_motion": shot["camera_motion"],
                        "audio_description": shot["audio_description"],
                        "status": "empty",
                    })
                    shot_total += 1

        msg = (f"Created {n_eps} episode(s)"
               + (f" and {shot_total} shots" if shot_total else "")
               + f" from {src.title}. "
               + f"Gemini took {gen_secs:.0f}s, "
               + f"{result.output_tokens} output tokens.")
        crud.update_job(job_id, status="done", progress=1.0, message=msg)
    except (scp_source.SCPSourceError, LLMError, costs.BudgetError) as exc:
        crud.update_job(job_id, status="error", error=str(exc))
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        crud.update_job(job_id, status="error",
                        error=f"{type(exc).__name__}: {exc}")
