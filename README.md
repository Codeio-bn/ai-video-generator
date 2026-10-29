# SCP Shorts Studio

A **local** production tool that turns an SCP Foundation story into a series of
vertical short videos (9:16, ~30–90 s). Human-in-the-loop by design: you review
and edit every script and shot before anything is generated or rendered.

Pipeline: source story → episode scripts → narration audio → shot list →
generated shots (Google Veo) → assembled MP4 with captions, music and an
attribution end card.

Everything runs on `localhost`. FastAPI (Python) backend · React + TypeScript
(Vite) frontend · SQLite storage · FFmpeg rendering.

---

## Status

| Milestone | Scope | State |
|-----------|-------|-------|
| **1. Render pipeline** | FFmpeg assembly: Ken Burns stills, 9:16 clip crop, title/attribution cards, captions, music ducking, background jobs, minimal UI | ✅ **Done** |
| 2. Script generation | Paste story → Gemini splits into episodes (hook / narration / cliffhanger) | ⬜ Next |
| 3. Narration audio | Local Kokoro TTS (pluggable) + word timestamps | ⬜ |
| 4. Shot list + Veo | LLM shot list, Google Veo 3.1 generation, cost control | ⬜ |
| 5. Export | MP4 + paste-ready description with attribution + hashtags | ⬜ |

---

## Requirements

- **Windows 11** (paths/scripts target Windows; the stack itself is cross-platform)
- **Python 3.10–3.13** recommended. Python **3.15 also works**, but the caption
  engine (`faster-whisper`) has no 3.15 binary wheels yet, so burned-in captions
  are disabled until those wheels ship — everything else works. See
  [Captions](#captions).
- **Node.js 18+**
- FFmpeg is **downloaded automatically** by the setup script (vendored into
  `tools/ffmpeg/`); nothing to install system-wide.

## Setup

```powershell
# from the repo root
powershell -File scripts\setup.ps1
```

This creates `.venv`, installs backend deps, downloads FFmpeg, and builds the
frontend.

## Run

```powershell
powershell -File scripts\run.ps1
# then open http://127.0.0.1:8000
```

The backend serves the built frontend and the API from the same origin.

### Dev mode (hot reload)

```powershell
# terminal 1 — backend
cd backend ; ..\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
# terminal 2 — frontend (proxies /api to :8000)
cd frontend ; npm run dev
# open http://127.0.0.1:5173
```

---

## Using Milestone 1

1. **New project** → enter the SCP number, title, original author(s) and source
   URL (the last two are required before export — license rule).
2. Open the project, fill in the **style bible** and metadata, **Save**.
3. **Add episode** → open it.
4. **Upload narration audio** (any wav/mp3). Optionally upload a **music** bed.
5. **Add shots**: image shots (pick a Ken Burns direction and duration) or text
   cards. Upload an image/clip per shot; reorder with ▲▼. Clips are auto-cropped
   to 9:16 and muted under narration.
6. In **Output**, pick render options (title card, end card, grain, vignette,
   music ducking, captions) and click **Render episode**. Progress streams live
   and survives a browser refresh. The finished 1080×1920 / 30 fps MP4 plays
   inline.

A warning appears if the result is under the project's target length (default
61 s — TikTok Creator Rewards only counts videos over 1 minute).

### Captions

Word-timestamped, burned-in captions use `faster-whisper` (CPU). It needs binary
wheels (`ctranslate2`, `av`, `onnxruntime`) for your Python version. On Python
3.10–3.12:

```powershell
.\.venv\Scripts\python.exe -m pip install faster-whisper
```

Then restart the app; the **Captions** chip in the top bar turns green and the
caption options unlock. Until then, renders simply omit captions (with a clear
warning). On Python 3.15 these wheels don't exist yet — see
[the note](#requirements).

### Google Gemini key (for Milestones 2+)

**Settings → Google Gemini API key.** Stored locally in `.secrets.json`
(gitignored, never in the frontend bundle). Get a key from Google AI Studio.

---

## Attribution (SCP license)

Every rendered video ends with an attribution card, and export (M5) will refuse
if author or source URL is empty. Each card shows: SCP number + title, original
author(s), source URL, "Licensed under CC BY-SA 3.0", and a line stating the
video is also released under CC BY-SA 3.0.

## Storage layout

```
data/app.db                         SQLite database
projects/<scp-number>/
  episodes/<n>/
    narration.*  music.*            audio
    shots/                          uploaded / generated shot assets
    render/                         working files + final.mp4
.secrets.json                       API keys (gitignored)
tools/ffmpeg/                       vendored FFmpeg (gitignored)
```

## Architecture notes

- **No ORM** — the backend uses Python's stdlib `sqlite3` to stay free of
  binary-wheel dependencies on new Python releases.
- **Pluggable by design**: the LLM, TTS and video providers are isolated behind
  seams so the Gemini API-key path (M2/M4) can later switch to Vertex AI.
- **Renders run as background jobs** on a thread pool; the UI polls job status,
  so a browser refresh never loses progress.
