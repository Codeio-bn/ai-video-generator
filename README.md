# SCP Video Studio

Turn an SCP Foundation article into a **30-second vertical (9:16) video** in a
few clicks. Enter an SCP designation and the tool:

1. **Fetches** the real article (with its author credit + source URL).
2. **Writes a script** with OpenAI — a 5–6 scene, ~30-second story. Each scene
   gets a line of **narration**, a **visual** description, and **sound** design.
3. Lets you **review and edit** every scene before spending anything.
4. **Generates the video** — Google **Veo** renders a clip per scene, OpenAI
   **narrates** each line, and FFmpeg assembles the final MP4.

Everything runs on `localhost`. FastAPI backend · React + TypeScript (Vite)
frontend · FFmpeg for assembly. API keys are stored locally and never bundled.

---

## Requirements

- **Linux or macOS** (bash scripts); **Windows 11** also supported (PowerShell
  scripts). The stack itself is cross-platform.
- **Python 3.12–3.15** (3.15 works — all AI calls are plain HTTP, no heavy wheels).
- **Node.js 18+**.
- **An OpenAI API key** (script + narration) and a **Google Gemini API key with
  Veo access** (video). FFmpeg is downloaded automatically by setup.

## Setup

```bash
./scripts/setup.sh          # Windows: powershell -File scripts\setup.ps1
```

Creates `.venv`, installs backend deps, vendors a static FFmpeg build, and
builds the frontend. (If your arch isn't x86_64/arm64, install ffmpeg with your
package manager — e.g. `sudo apt install ffmpeg` — and re-run.)

## Run

```bash
./scripts/dev.sh            # Windows: powershell -File scripts\dev.ps1
# then open http://127.0.0.1:5173
```

Both servers start together; one Ctrl+C stops both. Backend Python changes
hot-reload, frontend changes hot-reload over Vite.

## First use

1. Open **Settings** and paste your **OpenAI** and **Gemini** keys (pick a
   narrator voice if you like). The top-bar chips turn green when each is ready.
2. On the intake screen, enter an SCP (e.g. `SCP-173`) and click **Generate
   script**. OpenAI returns a 5–6 scene, ~30s script.
3. **Review and edit** the scenes — narration, visual, and sound are all
   editable. Rewrite the whole script if you want a different take.
4. Click **Produce video**. A background job narrates each line, generates a Veo
   clip per scene, and assembles the final MP4. Progress streams live.
5. Watch and **download** the finished video.

## About Veo (the video step)

Veo costs **real money** per clip (unlike the cheap OpenAI text/voice calls), and
it needs a **paid/billed** Google Gemini API project — a free AI Studio key has
no Veo model. The app detects this and disables **Produce** with a clear message
until a Veo-capable key is in place; it then auto-detects the right model id.

Tune it with secrets/env vars: `VEO_MODEL` (force a model id), `VEO_PRICE_PER_SEC`
(cost estimate, default `$0.40/s`), `VEO_DURATION` (clip length for estimates),
`OPENAI_MODEL`, `OPENAI_TTS_MODEL`, `OPENAI_TTS_VOICE`.

## Attribution (SCP license)

SCP content is CC BY-SA 3.0. Each video's case file records the original
author(s) and source URL (pulled from the wiki); keep them with anything you
publish.

## Storage layout

```
data/videos/<id>.json        one saved video project
data/videos/<id>/            its narration, Veo clips, and final.mp4
.secrets.json                API keys (gitignored)
tools/ffmpeg/                vendored FFmpeg (gitignored)
```

## Architecture

- **AI behind seams**: `ai_script.py` (OpenAI script), `tts.py` (OpenAI voice),
  `veo.py` (Gemini Veo), `scp_source.py` (wiki fetch) — all plain `requests`, no
  vendor SDKs, so nothing risky to build on new Python.
- **Background production** runs on a thread; the UI polls the video's status, so
  a browser refresh never loses progress.
- **No database** — each video is a JSON file under `data/videos/`.
