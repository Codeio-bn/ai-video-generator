"""FFmpeg render pipeline for an episode (Milestone 1).

Staged, debuggable pipeline:

  1. Render the "Part N" title card and attribution end card (Pillow PNGs).
  2. Encode every shot + card into an identically-encoded 1080x1920/30fps
     video-only segment (Ken Burns on stills, crop/scale on clips).
  3. Concat the segments (demuxer).
  4. Build one audio track: narration delayed past the title card, optional
     music bed ducked under it (sidechaincompress).
  5. Transcribe narration -> ASS captions (faster-whisper, optional).
  6. Final pass: burn captions, mux audio, clamp to exact duration.

All timestamps/geometry target a 1080x1920 canvas at 30 fps.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from . import captions as captions_mod
from . import cards
from .config import require_ffmpeg
from .storage import render_dir

W, H, FPS = 1080, 1920, 30
ProgressCb = Callable[[float, str], None]


class RenderError(RuntimeError):
    pass


@dataclass
class RenderOptions:
    title_card_seconds: float = 2.0
    end_card_seconds: float = 3.0
    show_title_card: bool = True
    show_end_card: bool = True
    captions: bool = True
    caption_mode: str = "word"          # 'word' | 'phrase'
    whisper_model: str = "base"
    film_grain: bool = False
    vignette: bool = False
    flicker: bool = False
    music: bool = False
    music_volume: float = 0.18
    duck_music: bool = True
    target_length: int = 61

    @staticmethod
    def from_dict(d: dict | None) -> "RenderOptions":
        d = d or {}
        known = RenderOptions().__dict__.keys()
        return RenderOptions(**{k: v for k, v in d.items() if k in known})


@dataclass
class RenderResult:
    output_path: str
    duration: float
    captions_used: bool
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# subprocess helpers
# --------------------------------------------------------------------------- #

def _run(cmd: list[str], cwd: Optional[Path] = None) -> None:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join((proc.stderr or "").strip().splitlines()[-12:])
        raise RenderError(f"FFmpeg failed (exit {proc.returncode}):\n{tail}")


def _probe_duration(ffprobe: str, path: Path) -> float:
    proc = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        return float(proc.stdout.strip())
    except (ValueError, AttributeError):
        return 0.0


# --------------------------------------------------------------------------- #
# filters
# --------------------------------------------------------------------------- #

def _kenburns(direction: str, frames: int) -> str:
    """Ken Burns zoompan on a single still (pre-scaled to 2x for pan room)."""
    f = max(frames, 1)
    base = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},scale={W*2}:{H*2},"
    )
    cx = "iw/2-(iw/zoom/2)"
    cy = "ih/2-(ih/zoom/2)"
    if direction == "out":
        z, x, y = f"1.14-(0.14*on/{f})", cx, cy
    elif direction == "left":
        z, x, y = "1.08", f"(iw-iw/zoom)*(1-on/{f})", "(ih-ih/zoom)/2"
    elif direction == "right":
        z, x, y = "1.08", f"(iw-iw/zoom)*(on/{f})", "(ih-ih/zoom)/2"
    elif direction == "up":
        z, x, y = "1.08", "(iw-iw/zoom)/2", f"(ih-ih/zoom)*(1-on/{f})"
    elif direction == "down":
        z, x, y = "1.08", "(iw-iw/zoom)/2", f"(ih-ih/zoom)*(on/{f})"
    else:  # 'in' / default
        z, x, y = f"1.0+(0.14*on/{f})", cx, cy
    return (
        base
        + f"zoompan=z='{z}':x='{x}':y='{y}':d={f}:s={W}x{H}:fps={FPS}"
    )


def _looks(opts: RenderOptions) -> str:
    extra = []
    if opts.film_grain:
        extra.append("noise=alls=11:allf=t+u")
    if opts.flicker:
        extra.append("noise=alls=20:allf=t")
    if opts.vignette:
        extra.append("vignette=PI/5")
    return ("," + ",".join(extra)) if extra else ""


_VENC = [
    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
    "-preset", "veryfast", "-crf", "20",
    "-video_track_timescale", "30000", "-an",
]


# --------------------------------------------------------------------------- #
# segment builders
# --------------------------------------------------------------------------- #

def _seg_from_image(ffmpeg, img: Path, out: Path, dur: float,
                    direction: str, opts: RenderOptions) -> None:
    frames = max(int(round(dur * FPS)), 1)
    vf = _kenburns(direction, frames) + _looks(opts) + ",setsar=1,format=yuv420p"
    _run([ffmpeg, "-y", "-i", str(img), "-vf", vf, "-frames:v", str(frames),
          *_VENC, str(out)])


def _seg_from_static_image(ffmpeg, img: Path, out: Path, dur: float,
                           opts: RenderOptions) -> None:
    """Cards: no Ken Burns, just hold the image for `dur`."""
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
          + ",setsar=1,format=yuv420p")
    _run([ffmpeg, "-y", "-loop", "1", "-i", str(img), "-t", f"{dur:.3f}",
          "-vf", vf, *_VENC, str(out)])


def _seg_from_video(ffmpeg, clip: Path, out: Path, dur: float,
                    opts: RenderOptions) -> None:
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"fps={FPS}" + _looks(opts) + ",setsar=1,format=yuv420p")
    _run([ffmpeg, "-y", "-i", str(clip), "-t", f"{dur:.3f}", "-vf", vf,
          *_VENC, str(out)])


# --------------------------------------------------------------------------- #
# audio
# --------------------------------------------------------------------------- #

def _build_audio(ffmpeg, work: Path, narration: Optional[Path],
                 music: Optional[Path], title_sec: float, total: float,
                 opts: RenderOptions) -> Optional[Path]:
    if not narration and not (music and opts.music):
        return None
    out = work / "mix.m4a"
    delay_ms = int(round(title_sec * 1000))
    cmd = [ffmpeg, "-y"]
    use_music = bool(music and opts.music)

    if narration and use_music:
        cmd += ["-i", str(narration), "-stream_loop", "-1", "-i", str(music)]
        duck = (
            f"[0:a]adelay={delay_ms}|{delay_ms},asplit=2[n1][n2];"
            f"[1:a]volume={opts.music_volume}[m];"
        )
        if opts.duck_music:
            duck += ("[m][n1]sidechaincompress=threshold=0.02:ratio=6:"
                     "attack=5:release=350[md];"
                     "[md][n2]amix=inputs=2:normalize=0,apad[a]")
        else:
            duck += "[m][n2]amix=inputs=2:normalize=0,apad[a]"
        cmd += ["-filter_complex", duck, "-map", "[a]"]
    elif narration:
        cmd += ["-i", str(narration),
                "-filter_complex", f"[0:a]adelay={delay_ms}|{delay_ms},apad[a]",
                "-map", "[a]"]
    else:  # music only
        cmd += ["-stream_loop", "-1", "-i", str(music),
                "-filter_complex", f"[0:a]volume={opts.music_volume},apad[a]",
                "-map", "[a]"]

    cmd += ["-t", f"{total:.3f}", "-c:a", "aac", "-b:a", "192k", str(out)]
    _run(cmd)
    return out


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #

def render_episode(project: dict, episode: dict, shots: list[dict],
                   opts: RenderOptions,
                   progress: Optional[ProgressCb] = None) -> RenderResult:
    ffmpeg, ffprobe = require_ffmpeg()
    warnings: list[str] = []

    def report(p: float, msg: str) -> None:
        if progress:
            progress(max(0.0, min(1.0, p)), msg)

    scp = project["scp_number"]
    part = episode["part_number"]
    work = render_dir(scp, part)
    for stale in work.glob("seg_*.mp4"):
        stale.unlink(missing_ok=True)

    playable = [s for s in shots if _shot_asset(s) or s["shot_type"] == "text_card"]
    if not playable:
        raise RenderError(
            "This episode has no renderable shots. Add at least one shot with "
            "an image/clip, or a text card."
        )

    report(0.02, "Preparing cards")
    segments: list[Path] = []
    title_sec = opts.title_card_seconds if opts.show_title_card else 0.0

    # --- title card ---
    if opts.show_title_card:
        tc_img = work / "title.png"
        cards.title_card(tc_img, part, episode.get("title") or project.get("title", ""))
        tc = work / "seg_000_title.mp4"
        _seg_from_static_image(ffmpeg, tc_img, tc, title_sec, opts)
        segments.append(tc)

    # --- shots ---
    total_shot = len(playable)
    for i, shot in enumerate(playable):
        report(0.05 + 0.55 * (i / max(total_shot, 1)),
               f"Rendering shot {i + 1} of {total_shot}")
        dur = max(float(shot.get("duration") or 5.0), 0.3)
        out = work / f"seg_{i + 1:03d}.mp4"
        stype = shot["shot_type"]
        asset = _shot_asset(shot)

        if stype == "text_card":
            img = work / f"textcard_{i + 1:03d}.png"
            cards.text_card(img, shot.get("text_content") or
                            shot.get("narration_excerpt") or "")
            _seg_from_static_image(ffmpeg, img, out, dur, opts)
        elif asset and _is_video(asset):
            _seg_from_video(ffmpeg, Path(asset), out, dur, opts)
        elif asset:
            direction = shot.get("kenburns_direction") or "in"
            _seg_from_image(ffmpeg, Path(asset), out, dur, direction, opts)
        else:
            continue
        segments.append(out)

    # --- end / attribution card ---
    end_sec = opts.end_card_seconds if opts.show_end_card else 0.0
    if opts.show_end_card:
        ac_img = work / "attribution.png"
        cards.attribution_card(
            ac_img, scp, project.get("title", ""), project.get("authors", ""),
            project.get("source_url", ""),
            project.get("license") or "CC BY-SA 3.0",
        )
        ac = work / "seg_999_end.mp4"
        _seg_from_static_image(ffmpeg, ac_img, ac, end_sec, opts)
        segments.append(ac)

    total_duration = (title_sec + end_sec +
                      sum(max(float(s.get("duration") or 5.0), 0.3)
                          for s in playable))

    # --- concat ---
    report(0.62, "Joining segments")
    list_file = work / "segments.txt"
    list_file.write_text(
        "".join(f"file '{p.resolve().as_posix()}'\n" for p in segments),
        encoding="utf-8",
    )

    # --- audio ---
    report(0.66, "Building audio track")
    narration = _existing(episode.get("narration_audio_path"))
    music = _existing(episode.get("music_path"))
    audio = _build_audio(ffmpeg, work, narration, music, title_sec,
                         total_duration, opts)
    if opts.music and not music:
        warnings.append("Music was enabled but no music file is set for this episode.")

    # --- captions ---
    captions_used = False
    ass_name: Optional[str] = None
    if opts.captions and narration:
        report(0.72, "Transcribing narration for captions")
        words = _get_words(episode, narration, opts, warnings)
        if words:
            ass_name = "captions.ass"
            (work / ass_name).write_text(
                captions_mod.build_ass(words, offset=title_sec,
                                       mode=opts.caption_mode),
                encoding="utf-8",
            )
            captions_used = True
    elif opts.captions and not narration:
        warnings.append("Captions need narration audio; none is set, so captions were skipped.")

    # --- final mux + caption burn ---
    report(0.82, "Final encode")
    final = work / "final.mp4"
    cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file)]
    if audio:
        cmd += ["-i", str(audio)]
    if ass_name:
        cmd += ["-filter_complex", f"[0:v]ass={ass_name},format=yuv420p[v]",
                "-map", "[v]"]
    else:
        cmd += ["-map", "0:v"]
    if audio:
        cmd += ["-map", "1:a", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-t", f"{total_duration:.3f}", "-movflags", "+faststart", str(final)]
    # cwd=work so the .ass path needs no Windows escaping.
    _run(cmd, cwd=work)

    actual = _probe_duration(ffprobe, final) or total_duration
    if actual < opts.target_length:
        warnings.append(
            f"Final video is {actual:.1f}s, under the {opts.target_length}s target "
            f"(TikTok Creator Rewards only counts videos over 1 minute)."
        )
    report(1.0, "Done")
    return RenderResult(str(final.resolve()), actual, captions_used, warnings)


# --------------------------------------------------------------------------- #
# small helpers
# --------------------------------------------------------------------------- #

_VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}


def _is_video(path: str) -> bool:
    return Path(path).suffix.lower() in _VIDEO_EXT


def _existing(path: Optional[str]) -> Optional[Path]:
    if path and Path(path).exists():
        return Path(path)
    return None


def _shot_asset(shot: dict) -> Optional[str]:
    """Resolve the asset for a shot, honouring the selected take."""
    takes_raw = shot.get("takes")
    if takes_raw:
        try:
            takes = json.loads(takes_raw) if isinstance(takes_raw, str) else takes_raw
            idx = int(shot.get("selected_take") or 0)
            if takes and 0 <= idx < len(takes) and Path(takes[idx]).exists():
                return takes[idx]
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
    ap = shot.get("asset_path")
    if ap and Path(ap).exists():
        return ap
    return None


def _get_words(episode: dict, narration: Path, opts: RenderOptions,
               warnings: list[str]) -> list[dict]:
    # Reuse stored timestamps if present.
    stored = episode.get("narration_words")
    if stored:
        try:
            words = json.loads(stored) if isinstance(stored, str) else stored
            if words:
                return words
        except (ValueError, json.JSONDecodeError):
            pass
    ok, why = captions_mod.whisper_available()
    if not ok:
        warnings.append(
            "Captions skipped: faster-whisper is not installed in this environment "
            f"({why}). Install it to enable burned-in captions."
        )
        return []
    try:
        return captions_mod.transcribe_words(str(narration), opts.whisper_model)
    except Exception as exc:  # pragma: no cover - env dependent
        warnings.append(f"Caption transcription failed: {type(exc).__name__}: {exc}")
        return []
