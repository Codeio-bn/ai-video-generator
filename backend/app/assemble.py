"""Stitch the generated scenes into one 9:16 vertical MP4 with FFmpeg.

For each scene: crop its Veo clip to 1080x1920/30fps, lay the scene's narration
voiceover on top (ducking the clip's own Veo audio to a low ambient bed), and
hold the length to the narration's duration. Then concat the scene segments.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import require_ffmpeg
from .store import asset_dir

W, H, FPS = 1080, 1920, 30
_AMBIENT_VOLUME = 0.18          # Veo's own audio, tucked under the voiceover


class AssembleError(RuntimeError):
    pass


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-12:])
        raise AssembleError(f"FFmpeg failed (exit {proc.returncode}):\n{tail}")


def probe_duration(path: str | Path) -> float:
    _, ffprobe = require_ffmpeg()
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        return float((proc.stdout or "").strip())
    except (ValueError, AttributeError):
        return 0.0


def _has_audio(path: str | Path) -> bool:
    _, ffprobe = require_ffmpeg()
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries",
         "stream=index", "-of", "csv=p=0", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    return bool((proc.stdout or "").strip())


def _segment(ffmpeg: str, clip: Path, narration: Path, dur: float, out: Path) -> None:
    """One scene: cropped clip + narration voiceover, exactly `dur` seconds."""
    d = max(float(dur), 0.5)
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,"
          f"crop={W}:{H},setsar=1,fps={FPS},"
          f"tpad=stop_mode=clone:stop_duration={d},trim=0:{d},setpts=PTS-STARTPTS")

    cmd = [ffmpeg, "-y", "-i", str(clip), "-i", str(narration)]
    if _has_audio(clip):
        # Duck the clip's Veo audio under the narration, mix the two.
        af = (f"[0:a]volume={_AMBIENT_VOLUME},atrim=0:{d},asetpts=PTS-STARTPTS[amb];"
              f"[1:a]volume=1.0,apad,atrim=0:{d},asetpts=PTS-STARTPTS[nar];"
              f"[amb][nar]amix=inputs=2:duration=first:dropout_transition=0[a]")
        filter_complex = f"[0:v]{vf}[v];{af}"
    else:
        filter_complex = (f"[0:v]{vf}[v];"
                          f"[1:a]volume=1.0,apad,atrim=0:{d},asetpts=PTS-STARTPTS[a]")

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]", "-t", f"{d}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-r", str(FPS),
        str(out),
    ]
    _run(cmd)


def assemble(video: dict) -> tuple[str, float]:
    """Build the final MP4 from a video's scenes. Returns (path, duration)."""
    ffmpeg, _ = require_ffmpeg()
    work = asset_dir(video["id"]) / "work"
    work.mkdir(parents=True, exist_ok=True)

    segments: list[Path] = []
    for scene in video["scenes"]:
        clip = scene.get("clip_path")
        narr = scene.get("narration_audio")
        if not clip or not Path(clip).exists():
            raise AssembleError(f"Scene {scene['index'] + 1} has no video clip.")
        if not narr or not Path(narr).exists():
            raise AssembleError(f"Scene {scene['index'] + 1} has no narration audio.")
        seg = work / f"seg_{scene['index']:02d}.mp4"
        _segment(ffmpeg, Path(clip), Path(narr), scene.get("duration") or 5.0, seg)
        segments.append(seg)

    if not segments:
        raise AssembleError("No scenes to assemble.")

    list_file = work / "segments.txt"
    list_file.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in segments),
        encoding="utf-8",
    )
    out = asset_dir(video["id"]) / "final.mp4"
    _run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
          "-c", "copy", str(out)])
    return str(out.resolve()), probe_duration(out)
