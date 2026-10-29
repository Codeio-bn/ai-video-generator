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
| **2. Script generation** | Paste story → Gemini splits into episodes (hook / narration / cliffhanger) | ✅ **Done** |
| **3. Narration audio** | Local Kokoro TTS (pluggable) + word timestamps | ✅ **Done** |
| 4. Shot list + Veo | LLM shot list ✅ · cost control ✅ · Veo generation ⬜ | 🟡 **In progress** |
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
powershell -File scripts\dev.ps1
# then open http://127.0.0.1:5173
```

`dev.ps1` starts **both** servers in one command — the API and the Vite
frontend — and one Ctrl+C stops both. **This is the way to run day to day:**
nothing needs restarting as you work.

- **Frontend** changes hot-reload instantly over Vite HMR (`:5173`), which
  proxies `/api` to the backend, so the browser only ever talks to one origin.
- **Backend** Python changes auto-restart the API via `uvicorn --reload`. With
  `watchfiles` installed (it's in `requirements.txt` and works on Python 3.15)
  the restart is near-instant; otherwise uvicorn falls back to slower polling.

Use the production `run.ps1` below only to sanity-check the built bundle — it
serves a **pre-built** frontend and does **not** reload, so it's not for
iterating.

### Production mode (single origin)

To serve the built frontend and the API from one origin instead:

```powershell
powershell -File scripts\run.ps1
# then open http://127.0.0.1:8000
```

This serves the **pre-built** bundle in `frontend\dist`, so after any change to
the frontend, rebuild it to see the update:

```powershell
cd frontend ; npm run build
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

A warning appears if the result is under the project's **Target episode length**
(default **30 s** — these are short TikToks). Generated narration is written to
fit that target and is **capped at ~35 s** regardless, so scripts stay tight and
punchy; set the field lower (e.g. 20 s) for even shorter clips. If you instead
want videos over a minute (e.g. for TikTok Creator Rewards), raise the cap in
`backend/app/llm.py` (`_MAX_TIKTOK_SECS`).

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

### API keys (for Milestones 2+)

All text work (story, episodes, shots) goes through a pluggable provider. Pick
which AI runs a generation with the **AI model for generation** dropdown that
sits right in each generate panel (auto-generate, script generation, shot
list) — or under **Settings → Active text provider**. Either way, save that
provider's key:

- **Groq** — **Settings → Groq API key**. Free and fast when available. Get a
  key at `console.groq.com`. The model id is auto-picked from your account
  (override with the `GROQ_MODEL` secret/env).
- **OpenAI (GPT)** — **Settings → OpenAI API key**. Cheap and reliable. Get a
  key at `platform.openai.com` (default model `gpt-4o-mini`, override with
  `OPENAI_MODEL`).
- **Google Gemini** — **Settings → Google Gemini API key** (from Google AI
  Studio). Used for Veo **video** generation (Milestone 4+), and as a text
  provider too (model via `GEMINI_MODEL`).

The selector writes the `LLM_PROVIDER` secret (`groq`, `openai` or `gemini`). If
it's unset, the provider is auto-chosen: Groq if a Groq key exists, else OpenAI
if an OpenAI key exists, else Gemini. **Video (Veo) always uses Gemini.** Keys
are stored locally in `.secrets.json` (gitignored, never in the frontend
bundle).

---

## Using Milestone 2 (script generation)

1. Save a **Google Gemini API key** under **Settings** (see above). The
   **Gemini** chip in the top bar turns green and the test button does a live
   round-trip.
2. Open a project and paste the full SCP story into **Generate episodes from
   the story**.
3. Pick a number of parts (or leave it on **Auto**) and optionally add guidance
   (e.g. "keep each part under 60 s"). Click **Generate episodes**.
4. Gemini splits the story into episode drafts — each with a hook, narration
   script and cliffhanger (plus a "previously…" recap on parts 2+). They appear
   as **draft** episodes; tick **Replace existing episodes** to start the set
   over instead of appending.
5. Open each episode, review and edit the script, then continue with the
   Milestone 1 audio/shots/render flow.

Generation is **human-in-the-loop**: nothing is produced until you approve a
script. The call runs over the Gemini REST API (model `gemini-3.8-flash` by
default; override with a `GEMINI_MODEL` env var or secret). A rough token-cost
estimate is recorded per project in the `cost_log` table for budget awareness.

## Using Milestone 3 (narration audio)

In an episode's **Audio** panel:

1. Pick a **Kokoro voice** and click **Generate narration**. The hook, "previously…"
   recap (parts 2+), narration and cliffhanger are read in order into
   `narration.wav`, and per-word caption timings are stored at the same time.
2. Or **Upload** your own narration file (any wav/mp3), exactly as in Milestone 1.
3. **Estimate caption timings** derives word timings from the narration audio's
   length and the script text. This lets burned-in captions work **even without
   faster-whisper** — handy on Python 3.15. A chip shows how many word timings
   are stored; the renderer prefers these over a live transcription.

Kokoro runs locally through torch/ONNX, whose wheels don't exist for Python 3.15
yet, so the **Kokoro TTS** chip shows unavailable there and the generate button
is disabled — upload narration by hand instead (captions still work via the
timing estimate). On Python 3.10–3.12, install it with:

```powershell
.\.venv\Scripts\python.exe -m pip install kokoro soundfile
```

The TTS provider lives behind a seam (`backend/app/tts.py`), so a cloud voice
can later replace Kokoro without touching the routers.

## Using Milestone 4 — shot list & budget (Veo generation next)

### Hands-off: auto-generate from a real SCP

On the project page, use **✨ Auto-generate from a real SCP**: enter an SCP number
(or URL), click once, and a background job fetches the real article from the SCP
wiki — **including its author credit and source URL, filled in automatically for
the CC BY-SA license** — retells it into episodes, and builds each episode's shot
list. Progress streams live and survives a refresh. Everything it produces stays
fully editable; nothing is final until you say so.

> Attribution note: the author and source URL are pulled from the wiki (via the
> Crom index). For a few older articles the author may come back blank — fill it
> in before export (M5 requires it).

### Manual: generate a shot list for one episode

In an episode's **Shots** section, click **✨ Generate shot list**. Gemini reads
the script and produces an ordered set of shots — each with a visual **prompt**,
**camera motion**, **audio/sound-design** note and a duration (4–8 s, the length
of an AI video clip). Edit any prompt inline; the project's style bible is added
to each prompt automatically at generation time, so you don't repeat it.

**Cost control.** Set a **Monthly budget cap** (USD) on the project; `0` means no
cap. Every paid call (Gemini tokens now, Veo seconds soon) is recorded, the
project header shows **spent / cap / remaining**, and a call that would exceed
the cap is refused with a clear message (HTTP 402) before any money is spent.

Veo shots show their prompt and controls but can't be generated in one click
**yet** — that (the Veo video provider, a background generation job, takes, and
hard per-clip budget enforcement) is the next step. For now you can refine the
prompts and upload a clip per shot by hand, or switch a shot to a still image.

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
