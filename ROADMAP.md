# SCP Shorts Studio — Roadmap & Build Log

> **Purpose:** the single source of truth for where this project is and what's
> next, so work survives switching machines or long gaps. This file lives in git
> — it travels with the repo. Update the checkboxes as you go.
>
> **Last updated:** 2026-10-29 · **Current milestone:** M1 ✅ done → **M2 next**

---

## 0. How to resume (read this first)

1. **New machine?** Do [§2 Setup on a new computer](#2-setup-on-a-new-computer).
2. **Where did I leave off?** See [§3 Status snapshot](#3-status-snapshot) and the
   first unchecked box in [§5 Milestones](#5-milestones).
3. **Why is something built the way it is?** See [§4 Key decisions](#4-key-decisions--constraints).
4. **Open questions to settle** before/while building: [§6 Parking lot](#6-open-decisions--parking-lot).

> ⚠️ **Your work data does NOT travel with git.** The code, this roadmap, and the
> setup scripts are committed, but `data/app.db` (your projects/episodes) and
> `projects/` (your audio, images, renders) and `.secrets.json` (API key) are
> **gitignored**. To move in-progress work to another computer, copy those
> folders manually (e.g. via a USB drive or private cloud sync). Nothing in them
> should ever be committed (they can contain large media and your API key).

---

## 1. What this is

A **local, human-in-the-loop** tool that turns one SCP Foundation story into a
series of vertical shorts (9:16, ~30–90 s). You review and edit every script and
shot before anything is generated or rendered. **Not** a one-click mass producer.

**Pipeline:** source story → episode scripts → narration audio → shot list →
generated shots (Google Veo) → assembled MP4 with captions, music, attribution.

**Stack:** FastAPI (Python) · React + TS (Vite) · stdlib `sqlite3` · FFmpeg
(vendored) · all on `localhost`.

---

## 2. Setup on a new computer

Prereqs: **Python 3.10–3.13** (3.15 works too — see captions caveat), **Node 18+**,
**git**.

```powershell
git clone <your-repo-url> ai-video-generator
cd ai-video-generator
powershell -File scripts\setup.ps1      # venv + deps + downloads FFmpeg + builds UI
powershell -File scripts\run.ps1        # serves http://127.0.0.1:8000
```

Then (optional): copy your old `data/`, `projects/`, `.secrets.json` into the
repo root to bring projects and renders across. Re-enter the Gemini key in
**Settings** if you didn't copy `.secrets.json`.

Full details and dev-mode (hot reload) are in [README.md](README.md).

---

## 3. Status snapshot

| Milestone | Scope | State |
|-----------|-------|-------|
| **M1 — Render pipeline** | FFmpeg assembly + minimal UI | ✅ **Done & demoed** |
| M2 — Script generation | Story → Gemini → episodes | ⬜ Next |
| M3 — Narration audio | Local Kokoro TTS + timestamps | ⬜ |
| M4 — Shot list + Veo | LLM shot list, Veo generation, cost control | ⬜ |
| M5 — Export | MP4 + description + checklist | ⬜ |

**Known open item:** burned-in captions are coded but **inactive** because
`faster-whisper` has no Python-3.15 wheels. See [§6](#6-open-decisions--parking-lot).

---

## 4. Key decisions & constraints

These are deliberate and explain the shape of the code. Don't "fix" them without
reading the why.

- **Python 3.15 on the dev machine.** `pydantic-core` and `pillow` ship cp315
  wheels (fine), but `av`, `onnxruntime`, `ctranslate2` do **not** → no
  `faster-whisper`/Kokoro yet. Before adding any new dependency, test with
  `pip install --only-binary=:all: <pkg>` to confirm a wheel exists.
- **Plain `uvicorn`, not `uvicorn[standard]`** — the extras pull `pyyaml`, which
  has no 3.15 wheel and needs a C compiler.
- **stdlib `sqlite3`, no ORM** — chosen to avoid binary-wheel/compat risk on new
  Python. Schema lives in `backend/app/database.py`.
- **FFmpeg is vendored** at `tools/ffmpeg/bin/` (gitignored, fetched by
  `scripts/setup.ps1`). Located at runtime by `backend/app/config.py`
  (env `FFMPEG_PATH`/`FFPROBE_PATH` → `tools/` → system PATH).
- **Cards drawn with Pillow**, not FFmpeg `drawtext`, to avoid Windows
  font-path escaping. Captions burn from an **ASS** file with the render dir as
  CWD for the same reason.
- **Renders run as background thread-pool jobs** persisted in `render_jobs`, so
  progress survives a browser refresh (UI polls `GET /api/jobs/{id}`).
- **Provider seams**: LLM, TTS, and video generation must stay behind interfaces
  so the Gemini API-key path can later swap to Vertex AI (OAuth/service account).

---

## 5. Milestones

### ✅ M1 — Render pipeline (no AI)

- [x] Project/episode/shot data model + SQLite (`database.py`, `crud.py`)
- [x] Per-project folder layout (`storage.py`)
- [x] 1080×1920/30fps MP4 via FFmpeg (`render.py`)
- [x] Ken Burns on stills (6 directions); grain / vignette / flicker options
- [x] Video clips cropped to 9:16, trimmed, audio muted under narration
- [x] "Part N" title card + attribution end card + text cards (Pillow)
- [x] Captions from word timestamps → ASS burn-in (word / phrase mode) *(code done; engine gated on wheels)*
- [x] Background music bed with sidechain ducking
- [x] Background jobs with live progress; survives refresh
- [x] Sub-target-length warning (configurable; default 61 s)
- [x] Minimal React UI: projects, metadata/attribution, episodes, shots (upload/reorder/options), render + inline playback
- [x] Settings page: Gemini key stored in gitignored `.secrets.json`; system-status chips
- [x] README + `scripts/setup.ps1` + `scripts/run.ps1`
- [ ] **Activate captions** (see parking lot) — the only incomplete piece of M1

### ⬜ M2 — Script generation

- [ ] Project field to paste **source story text** + metadata (field exists: `projects.source_text`)
- [ ] Pluggable **LLM provider** interface; implement **Gemini** (`google-genai`) first
- [ ] "Split into N episodes" (user picks N, e.g. 5–10): each with **hook**,
      ~130–180 words **narration**, **cliffhanger**
- [ ] Narration = retelling in the channel's voice, faithful to source
- [ ] Optional **"Previously…"** one-liner for parts 2+
- [ ] All generated text **editable before approval** (UI already has the fields)
- [ ] Live **Test connection** for the Gemini key (replace the M1 stub in `routers/system.py`)
- [ ] Clear errors: quota, safety-filter rejection, bad key
- [ ] Unit test against a **mocked** LLM so it's verifiable without burning quota

### ⬜ M3 — Narration audio

- [ ] Pluggable **TTS provider**; implement **Kokoro** (CPU) as default *(needs Python ≤3.12 or a wheel check)*
- [ ] One consistent narrator voice per project; per-episode regenerate; adjustable speed
- [ ] Store audio + **word timestamps** (→ feeds the existing caption path, replaces whisper dependency for TTS'd audio)
- [ ] Later pluggable to Gemini TTS / ElevenLabs

### ⬜ M4 — Shot list + Google Veo

- [ ] LLM proposes a **shot list** from narration: one shot / ~4–8 s, each with
      visual prompt (subject, action, ONE camera move, lighting, mood) + audio desc
- [ ] Auto-prepend **style bible** + relevant **character sheets** to each prompt
- [ ] Guardrail: prompts must **never** request readable text/labels (overlays instead)
- [ ] Generate via **Google Veo** (`google-genai`; verify current **Veo 3.1** model IDs,
      durations, 9:16, async operation/polling) — check live docs at build time
- [ ] Per-shot **model choice** (Veo Lite/Fast vs standard) + **cheap mode**
      (still image + Ken Burns)
- [ ] **Cost control**: per-shot & per-episode estimate, explicit Generate confirm,
      running cost log (`cost_log` table exists), **monthly budget cap**
      (`projects.monthly_budget_cap` exists)
- [ ] Generate single / batch; regenerate one shot; keep **takes**, pick best
      (shot `takes`/`selected_take` already modeled & used by the renderer)
- [ ] Manual upload per shot always available *(already works from M1)*

### ⬜ M5 — Export

- [ ] Export MP4 + a **paste-ready description** (TikTok + YouTube) with the
      attribution block + hashtags
- [ ] **Block export** if author or source URL is empty (license rule)
- [ ] Export checklist incl. "**Turn on the AI-generated content label** when uploading"

### Cross-cutting / non-functional (ongoing)

- [x] Long jobs as background tasks w/ progress (renders). [ ] Extend to TTS & Veo polling.
- [x] Per-project folder structure. [ ] Clear errors for every provider (quota, safety, missing FFmpeg — FFmpeg done).
- [x] API key in local store, never in repo/bundle.
- [ ] Vertex AI switch path kept open in the provider interfaces.

---

## 6. Open decisions & parking lot

- **Captions engine (blocks closing M1).** `faster-whisper` won't install on
  Python 3.15. Options:
  1. **Vendor whisper.cpp** (standalone CPU binary + ~140 MB model) — works on any
     Python, stays local. *(Leaning this way for 3.15.)*
  2. Separate **Python 3.10–3.12 venv** used only for the caption step.
  3. Wait for `av`/`onnxruntime` 3.15 wheels.
  4. Once **M3 (TTS)** lands, TTS can emit word timestamps directly, removing the
     need to transcribe TTS'd narration at all (whisper only needed for
     user-uploaded audio).
- **N episodes default** for M2 splitting — expose as a per-generation input.
- **Veo model IDs / pricing** — confirm against live Google docs when M4 starts
  (don't hardcode from memory).

---

## 7. File map

```
backend/app/
  main.py        FastAPI app, CORS, serves built frontend, startup hooks
  config.py      paths, FFmpeg/font discovery, local secrets store
  database.py    sqlite schema + connection helper
  crud.py        dict-based CRUD for projects/episodes/shots/jobs
  schemas.py     pydantic request models
  storage.py     per-project folder layout
  cards.py       Pillow title/text/attribution cards
  captions.py    faster-whisper (optional) + ASS subtitle builder
  render.py      the FFmpeg pipeline (segments → concat → audio → caption burn)
  jobs.py        background render runner (thread pool, DB-persisted)
  routers/       projects.py · render.py · system.py
frontend/src/
  App.tsx, api.ts, types.ts, styles.css
  components/    SystemBar, ProjectList, ProjectView, EpisodeView, RenderPanel, common
scripts/         setup.ps1 (install+ffmpeg+build) · run.ps1 (serve)
README.md        user-facing setup & usage
ROADMAP.md       this file
```
