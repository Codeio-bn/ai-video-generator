"""Background producer: turn a reviewed script into the finished video.

Pipeline, as one job per video (polled via GET /api/videos/{id}):

  1. Narration  - OpenAI TTS for each scene; each scene's length is set from
                  its spoken narration.
  2. Video      - Veo generates a clip per scene (the slow, paid step). Scenes
                  that already have a clip are skipped, so a retry after fixing
                  Veo access only pays for the ones that failed.
  3. Assemble   - FFmpeg stitches the scenes into one 9:16 MP4.

Progress + per-scene status are written back onto the stored video so the UI
reflects them live and a refresh never loses state.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import assemble, store, tts, veo

_executor = ThreadPoolExecutor(max_workers=1)   # one paid production at a time

_MIN_SCENE_SECS = 2.0
_MAX_SCENE_SECS = 9.0


def start_produce(vid: str) -> dict | None:
    video = store.get(vid)
    if not video:
        return None
    if video.get("status") == "producing":
        return video
    video = store.update(vid, status="producing", progress=0.02,
                         message="Starting…", error="")
    _executor.submit(_run_produce, vid)
    return video


def _set(vid: str, **fields) -> None:
    store.update(vid, **fields)


def _run_produce(vid: str) -> None:
    try:
        video = store.get(vid)
        scenes = video["scenes"]
        n = len(scenes)
        if not n:
            raise RuntimeError("This video has no scenes.")
        adir = store.asset_dir(vid)

        # 1. Narration (cheap) — also fixes each scene's duration.
        for i, scene in enumerate(scenes):
            _set(vid, progress=0.05 + 0.15 * (i / n),
                 message=f"Narrating scene {i + 1} of {n}…")
            narr = adir / f"narration_{i:02d}.mp3"
            if not (scene.get("narration") or "").strip():
                scene["narration_audio"] = None
                scene["duration"] = scene.get("duration") or 5.0
            else:
                tts.synthesize(scene["narration"], narr,
                               voice=video.get("voice", ""))
                dur = assemble.probe_duration(narr)
                scene["narration_audio"] = str(narr.resolve())
                scene["duration"] = round(
                    min(max(dur + 0.4, _MIN_SCENE_SECS), _MAX_SCENE_SECS), 2)
            store.update(vid, scenes=scenes)

        # 2. Video clips (slow, paid) — skip scenes already generated.
        cost_total = 0.0
        for i, scene in enumerate(scenes):
            base = 0.20 + 0.65 * (i / n)
            existing = scene.get("clip_path")
            if existing and Path(existing).exists():
                scene["status"] = "ready"
                cost_total += scene.get("cost") or 0.0
                store.update(vid, scenes=scenes, progress=base)
                continue
            scene["status"] = "generating"
            store.update(vid, scenes=scenes, progress=base,
                         message=f"Generating video for scene {i + 1} of {n}…")
            prompt = veo.compose_prompt(scene.get("visual", ""), scene.get("sound", ""))
            dest = adir / f"clip_{i:02d}.mp4"
            veo.generate_clip(
                prompt, dest, aspect_ratio="9:16",
                status_cb=lambda m, k=i: _set(
                    vid, message=f"Scene {k + 1} of {n}: {m}"),
            )
            cost = veo.estimate_cost(scene.get("duration"))
            scene["clip_path"] = str(dest.resolve())
            scene["status"] = "ready"
            scene["cost"] = round(cost, 4)
            cost_total += cost
            store.update(vid, scenes=scenes, cost_total=round(cost_total, 4))

        # 3. Assemble.
        _set(vid, progress=0.88, message="Assembling the final video…")
        final_path, duration = assemble.assemble(store.get(vid))
        store.update(vid, status="done", progress=1.0,
                     message=f"Done — {duration:.0f}s video ready.",
                     final_path=final_path, final_duration=round(duration, 2))
    except (veo.VeoError, tts.TTSError, assemble.AssembleError) as exc:
        _mark_error(vid, str(exc))
    except Exception as exc:  # noqa: BLE001 - surface anything else cleanly
        _mark_error(vid, f"{type(exc).__name__}: {exc}")


def _mark_error(vid: str, msg: str) -> None:
    scenes = (store.get(vid) or {}).get("scenes", [])
    for s in scenes:
        if s.get("status") == "generating":
            s["status"] = "error"
    store.update(vid, status="error", error=msg, message="Production failed.",
                 scenes=scenes)
