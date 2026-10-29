"""LLM provider seam (Milestone 2: script generation).

The rest of the app talks to this module, never to a vendor SDK, so the text
backend can be swapped freely. Three providers are supported for the text work
(story / episodes / shots), selected at runtime:

- **groq**   — Groq's OpenAI-compatible API (fast, free tier, rarely congested).
- **openai** — OpenAI's chat-completions API (cheap, reliable, JSON mode).
- **gemini** — Google's Generative Language REST API.

The active provider is ``LLM_PROVIDER`` (secret/env); if unset it is Groq when a
``GROQ_API_KEY`` exists, else OpenAI when an ``OPENAI_API_KEY`` exists, else
Gemini. Video generation (Veo) stays on Gemini.

Everything goes over plain ``requests`` on purpose: no vendor SDKs, so no risky
transitive wheels on brand-new Python (see the project's environment notes).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

import requests

from .config import get_secret

# Transient server-side statuses worth retrying with backoff.
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3

# Latest fast, cheap multimodal model. Override with the GEMINI_MODEL secret/env.
DEFAULT_MODEL = "gemini-3.8-flash"
_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
_TIMEOUT = 90   # seconds per attempt. Enough for a big structured reply, but
                # bounded so a hung request fails fast instead of "loading"
                # forever (these run in a background job that streams progress).

# Groq: OpenAI-compatible chat completions. Fast, free tier, JSON mode.
# Model ids change over time, so we auto-pick an available one from the account
# (see _groq_pick_model); this is only the last-resort fallback / preference.
GROQ_DEFAULT_MODEL = "llama-3.1-8b-instant"
_GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
# Preferred chat models, best first; we use the first one the account actually has.
_GROQ_PREFS = [
    "llama-3.3-70b-versatile", "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant", "llama3-70b-8192",
    "mixtral-8x7b-32768", "gemma2-9b-it",
]
_groq_model_cache: str | None = None

# OpenAI: same chat-completions shape as Groq. Cheap, reliable, JSON mode.
OPENAI_DEFAULT_MODEL = "gpt-4o-mini"
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# Rough public list price (USD per 1M tokens) for cost logging. These are
# estimates for budget awareness only, not billing-accurate; an unknown model
# falls through to (0, 0). Override the model with the GEMINI_MODEL secret/env.
_PRICING = {
    "gemini-3.8-flash": (0.30, 2.50),   # estimate (flash tier)
    "gemini-3.8-pro": (1.25, 10.00),    # estimate (pro tier)
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
}


class LLMError(RuntimeError):
    """Raised with a user-facing message when a generation request fails."""


@dataclass
class GenResult:
    episodes: list[dict]
    model: str
    prompt_tokens: int
    output_tokens: int
    cost: float


def provider_name() -> str:
    """Active text provider: 'groq', 'openai', or 'gemini'."""
    explicit = (get_secret("LLM_PROVIDER") or "").strip().lower()
    if explicit in ("groq", "openai", "gemini"):
        return explicit
    if get_secret("GROQ_API_KEY"):
        return "groq"
    if get_secret("OPENAI_API_KEY"):
        return "openai"
    return "gemini"


def model_name() -> str:
    """Model id for the active provider (what cost/status reports use)."""
    p = provider_name()
    if p == "groq":
        return get_secret("GROQ_MODEL") or _groq_model_cache or GROQ_DEFAULT_MODEL
    if p == "openai":
        return get_secret("OPENAI_MODEL") or OPENAI_DEFAULT_MODEL
    return get_secret("GEMINI_MODEL") or DEFAULT_MODEL


def _groq_pick_model(key: str) -> str | None:
    """Ask Groq which models the key can use; pick the best available chat one."""
    try:
        resp = requests.get(_GROQ_MODELS_URL,
                            headers={"Authorization": f"Bearer {key}"}, timeout=15)
        if resp.status_code != 200:
            return None
        ids = [m.get("id", "") for m in resp.json().get("data", [])]
    except (requests.RequestException, ValueError):
        return None
    for pref in _GROQ_PREFS:
        if pref in ids:
            return pref
    # Otherwise the first plain text chat model (skip audio/guard/embeddings).
    skip = ("whisper", "guard", "tts", "embedding", "distil", "allam", "prompt")
    for i in ids:
        if i and not any(s in i.lower() for s in skip):
            return i
    return None


def _groq_model(key: str) -> str:
    """Resolve the Groq model to use, caching the auto-picked one."""
    global _groq_model_cache
    explicit = get_secret("GROQ_MODEL")
    if explicit:
        return explicit
    if _groq_model_cache:
        return _groq_model_cache
    _groq_model_cache = _groq_pick_model(key) or GROQ_DEFAULT_MODEL
    return _groq_model_cache


def _require_gemini_key() -> str:
    key = get_secret("GEMINI_API_KEY")
    if not key:
        raise LLMError(
            "No Google Gemini API key is saved. Add one under Settings "
            "(get a key from Google AI Studio)."
        )
    return key


def _require_groq_key() -> str:
    key = get_secret("GROQ_API_KEY")
    if not key:
        raise LLMError(
            "No Groq API key is saved. Add one under Settings "
            "(get a free key from console.groq.com)."
        )
    return key


def _require_openai_key() -> str:
    key = get_secret("OPENAI_API_KEY")
    if not key:
        raise LLMError(
            "No OpenAI API key is saved. Add one under Settings "
            "(get a key from platform.openai.com)."
        )
    return key


def _estimate_cost(model: str, prompt_tokens: int, output_tokens: int) -> float:
    in_price, out_price = _PRICING.get(model, (0.0, 0.0))
    return (prompt_tokens * in_price + output_tokens * out_price) / 1_000_000


def check_connection() -> dict:
    """Light round-trip used by the Settings 'Test connection' button."""
    provider = provider_name()
    model = model_name()
    if provider == "groq":
        key = get_secret("GROQ_API_KEY")
        if not key:
            return {"ok": False, "detail": "No Groq API key saved yet."}
        try:
            resp = requests.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}"}, timeout=20,
            )
        except requests.RequestException as exc:
            return {"ok": False, "detail": f"Could not reach Groq: {exc}"}
        if resp.status_code == 200:
            names = {m.get("id", "") for m in resp.json().get("data", [])}
            if model in names:
                return {"ok": True, "detail": f"Connected to Groq. Using “{model}”."}
            return {"ok": True, "detail":
                    f"Groq key works, but model “{model}” isn't listed — "
                    "set GROQ_MODEL to one that is."}
        return {"ok": False, "detail": _http_error_detail(resp)}

    if provider == "openai":
        key = get_secret("OPENAI_API_KEY")
        if not key:
            return {"ok": False, "detail": "No OpenAI API key saved yet."}
        try:
            resp = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {key}"}, timeout=20,
            )
        except requests.RequestException as exc:
            return {"ok": False, "detail": f"Could not reach OpenAI: {exc}"}
        if resp.status_code == 200:
            names = {m.get("id", "") for m in resp.json().get("data", [])}
            if model in names:
                return {"ok": True, "detail": f"Connected to OpenAI. Using “{model}”."}
            return {"ok": True, "detail":
                    f"OpenAI key works, but model “{model}” isn't listed — "
                    "set OPENAI_MODEL to one that is."}
        return {"ok": False, "detail": _http_error_detail(resp)}

    key = get_secret("GEMINI_API_KEY")
    if not key:
        return {"ok": False, "detail": "No Gemini API key saved yet."}
    try:
        resp = requests.get(f"{_API_ROOT}/models", params={"key": key}, timeout=20)
    except requests.RequestException as exc:
        return {"ok": False, "detail": f"Could not reach Gemini: {exc}"}
    if resp.status_code == 200:
        names = {
            m.get("name", "").split("/")[-1]
            for m in resp.json().get("models", [])
        }
        if model in names:
            return {"ok": True, "detail": f"Connected. Using model “{model}”."}
        return {
            "ok": True,
            "detail": (
                f"Key works, but model “{model}” was not listed for this key. "
                "Generation may fail — check the GEMINI_MODEL setting."
            ),
        }
    return {"ok": False, "detail": _http_error_detail(resp)}


def _http_error_detail(resp: requests.Response) -> str:
    try:
        err = resp.json().get("error", {})
        msg = (err.get("message") if isinstance(err, dict) else None) or resp.text
    except ValueError:
        msg = resp.text or resp.reason
    if resp.status_code in (401, 403):
        return f"Authentication failed ({resp.status_code}). Check the API key. {msg}"
    if resp.status_code == 404:
        return f"Model not found (404) — set GROQ_MODEL/GEMINI_MODEL to an available one. {msg}"
    if resp.status_code == 429:
        return f"Rate limited (429). Try again shortly. {msg}"
    return f"The model API returned HTTP {resp.status_code}: {msg}"


# --------------------------------------------------------------------------- #
# script generation
# --------------------------------------------------------------------------- #

_EPISODE_SCHEMA = {
    "type": "object",
    "properties": {
        "episodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "previously": {"type": "string"},
                    "narration_script": {"type": "string"},
                    "cliffhanger": {"type": "string"},
                },
                "required": ["title", "hook", "narration_script", "cliffhanger"],
                "propertyOrdering": [
                    "title", "hook", "previously", "narration_script", "cliffhanger",
                ],
            },
        }
    },
    "required": ["episodes"],
}

_SYSTEM_INSTRUCTION = (
    "You are a scriptwriter for a series of vertical short-form videos (9:16, "
    "~30–90 seconds each) that retell SCP Foundation creepypasta stories. You "
    "write for narration read aloud by a single voice over moody archival "
    "footage. Your job is to split one source story into a sequence of episodes "
    "that each stand as a satisfying short while pulling the viewer to the next.\n\n"
    "Rules for every episode:\n"
    "- hook: one or two punchy sentences for the first ~2 seconds that stop the "
    "scroll. No throat-clearing.\n"
    "- narration_script: the spoken body. Plain prose, no stage directions, no "
    "speaker labels, no markdown. This is a TikTok short, so keep it BRIEF and "
    "punchy — hit only the essential beats, short sentences, no padding, and "
    "never exceed the word budget in the prompt. Build dread fast.\n"
    "- cliffhanger: a final line that lands the beat and, except for the last "
    "episode, makes the viewer need part N+1.\n"
    "- previously: for every episode after the first, a single sentence recap of "
    "where the last part left off. Leave it empty for episode 1.\n"
    "- title: a short, evocative episode title (not just 'Part N').\n\n"
    "Stay faithful to the source. Do not invent a different ending. Return only "
    "the structured data requested."
)


# TikTok shorts stay tight: the narration target is capped here no matter how
# long the project's target_episode_length is, so scripts never ramble.
_MAX_TIKTOK_SECS = 35
_WORDS_PER_SEC = 2.2  # ~130 wpm narration


def _build_prompt(
    project: dict, source_text: str, num_parts: int, guidance: str
) -> str:
    raw = project.get("target_episode_length") or _MAX_TIKTOK_SECS
    target = max(12, min(int(raw), _MAX_TIKTOK_SECS))
    words = int(target * _WORDS_PER_SEC)
    parts_line = (
        f"Split the story into exactly {num_parts} episodes."
        if num_parts and num_parts > 0
        else "Use as FEW episodes as the story needs (often just 1–2). Do not "
        "split a short story into many parts, and never pad to fill episodes."
    )
    lines = [
        f"SCP designation: {project.get('scp_number') or '(unknown)'}",
        f"Working title: {project.get('title') or '(none)'}",
        f"Language: {project.get('language') or 'en'}",
        "",
        "THIS IS A TIKTOK SHORT — a tight vertical clip, not an audiobook.",
        f"Each episode's narration MUST be short: about {target} seconds read "
        f"aloud, i.e. roughly {words} words, and NEVER more than ~{words + 15} "
        "words. Shorter is better. Open on the hook, deliver only the essential "
        "beats in punchy sentences, end on the cliffhanger. Cut all filler, "
        "background lore and repetition.",
        "",
        parts_line,
    ]
    style = (project.get("style_bible") or "").strip()
    if style:
        lines += ["", f"Tone / style bible to honor:\n{style}"]
    extra = (guidance or "").strip()
    if extra:
        lines += ["", f"Extra instructions from the editor:\n{extra}"]
    lines += [
        "",
        "SOURCE STORY (verbatim, between the markers):",
        "<<<STORY",
        source_text.strip(),
        "STORY>>>",
    ]
    return "\n".join(lines)


def _retry_after(resp: requests.Response, fallback: float) -> float:
    """Honor a Retry-After header (seconds) if present, else the backoff."""
    header = resp.headers.get("Retry-After")
    if header:
        try:
            return min(max(float(header), 1.0), 30.0)
        except ValueError:
            pass
    return fallback


def _post_with_retry(url: str, body: dict, *, params=None, headers=None,
                     provider: str = "the model",
                     status_cb=None) -> requests.Response:
    """POST with exponential backoff on transient (429/5xx) errors & timeouts.

    Calls status_cb(msg) and logs each step so a long call is observable rather
    than a frozen spinner. Raises LLMError once retries are exhausted.
    """
    def note(msg: str) -> None:
        print(f"[llm] {msg}", flush=True)
        if status_cb:
            try:
                status_cb(msg)
            except Exception:  # noqa: BLE001 - status is best-effort
                pass

    last_detail = "unknown error"
    for attempt in range(_MAX_ATTEMPTS):
        backoff = min(2.0 * (2 ** attempt), 15.0)  # 2, 4, 8 s
        note(f"Contacting {provider} (attempt {attempt + 1}/{_MAX_ATTEMPTS})…")
        t0 = time.monotonic()
        try:
            resp = requests.post(url, params=params, headers=headers, json=body,
                                 timeout=_TIMEOUT)
        except requests.Timeout:
            last_detail = f"{provider} didn't respond within {_TIMEOUT}s."
        except requests.RequestException as exc:
            last_detail = f"Could not reach {provider}: {exc}"
        else:
            if resp.status_code == 200:
                note(f"{provider} responded in {time.monotonic() - t0:.0f}s.")
                return resp
            last_detail = _http_error_detail(resp)
            if resp.status_code not in _RETRY_STATUSES:
                raise LLMError(last_detail)  # e.g. 400/401/403 won't fix on retry
            backoff = _retry_after(resp, backoff)
        if attempt < _MAX_ATTEMPTS - 1:
            note(f"{last_detail} Retrying in {backoff:.0f}s…")
            time.sleep(backoff)
    raise LLMError(
        f"{last_detail} {provider} stayed unavailable after {_MAX_ATTEMPTS} "
        "attempts — usually a temporary spike, so try again shortly, or switch "
        "provider/model in Settings."
    )


def _generate_json(system: str, user_text: str, schema: dict,
                   temperature: float = 0.9,
                   status_cb=None) -> tuple[str, str, int, int]:
    """One structured-output request to the active provider.

    Returns (json_text, model, prompt_tokens, output_tokens).
    """
    p = provider_name()
    if p == "groq":
        return _chat_generate("Groq", _GROQ_URL, _require_groq_key(),
                              _groq_model(get_secret("GROQ_API_KEY") or ""),
                              system, user_text, schema, temperature, status_cb)
    if p == "openai":
        key = _require_openai_key()
        model = get_secret("OPENAI_MODEL") or OPENAI_DEFAULT_MODEL
        return _chat_generate("OpenAI", _OPENAI_URL, key, model,
                              system, user_text, schema, temperature, status_cb)
    return _gemini_generate(system, user_text, schema, temperature, status_cb)


def _gemini_generate(system, user_text, schema, temperature, status_cb):
    key = _require_gemini_key()
    model = model_name()
    gen_cfg = {
        "temperature": temperature,
        "responseMimeType": "application/json",
        "responseSchema": schema,
    }
    # Optional speed lever: GEMINI_THINKING_BUDGET=0 disables flash "thinking".
    tb = get_secret("GEMINI_THINKING_BUDGET")
    if tb not in (None, ""):
        try:
            gen_cfg["thinkingConfig"] = {"thinkingBudget": int(tb)}
        except ValueError:
            pass
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": gen_cfg,
    }
    url = f"{_API_ROOT}/models/{model}:generateContent"
    resp = _post_with_retry(url, body, params={"key": key}, provider="Gemini",
                            status_cb=status_cb)
    payload = resp.json()
    usage = payload.get("usageMetadata", {})
    return (
        _response_text(payload), model,
        int(usage.get("promptTokenCount", 0)),
        int(usage.get("candidatesTokenCount", 0)),
    )


def _chat_generate(label, url, key, model, system, user_text, schema,
                   temperature, status_cb):
    """Shared OpenAI-compatible chat-completions call (Groq & OpenAI)."""
    # JSON mode needs the word "json" + a shape in the prompt; embedding the
    # schema keeps it DRY and steers the output.
    user_full = (
        user_text
        + "\n\nReturn ONLY a JSON object (no markdown, no prose) that matches "
        "this JSON schema:\n" + json.dumps(schema)
    )
    body = {
        "model": model,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_full},
        ],
    }
    headers = {"Authorization": f"Bearer {key}"}
    resp = _post_with_retry(url, body, headers=headers, provider=label,
                            status_cb=status_cb)
    payload = resp.json()
    choices = payload.get("choices") or []
    if not choices:
        raise LLMError(f"{label} returned no content.")
    choice = choices[0]
    if choice.get("finish_reason") == "length":
        raise LLMError(
            f"{label}'s reply was cut off (hit the output limit). Try fewer "
            "episodes/parts, or a shorter source story."
        )
    text = ((choice.get("message") or {}).get("content") or "").strip()
    if not text:
        raise LLMError(f"{label} returned an empty response.")
    usage = payload.get("usage", {})
    return (
        text, model,
        int(usage.get("prompt_tokens", 0)),
        int(usage.get("completion_tokens", 0)),
    )


def _response_text(payload: dict) -> str:
    """Extract and validate the text part of a Gemini generateContent response."""
    candidates = payload.get("candidates") or []
    if not candidates:
        block = payload.get("promptFeedback", {}).get("blockReason")
        if block:
            raise LLMError(f"Gemini blocked this request ({block}). Try different input.")
        raise LLMError("Gemini returned no content.")
    cand = candidates[0]
    finish = cand.get("finishReason")
    if finish == "SAFETY":
        raise LLMError("Gemini stopped for safety reasons on this content.")
    if finish == "MAX_TOKENS":
        raise LLMError(
            "Gemini's reply was cut off (hit the output limit). Try fewer "
            "episodes/parts, or a shorter source story."
        )
    parts = cand.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise LLMError(
            "Gemini returned an empty response"
            + (f" (finishReason={finish})." if finish else ".")
        )
    return text


def generate_episodes(
    project: dict,
    source_text: str,
    num_parts: int = 0,
    guidance: str = "",
) -> GenResult:
    """Turn a source story into structured episode drafts."""
    if not (source_text or "").strip():
        raise LLMError("The source story is empty — paste the SCP text first.")
    text, model, pt, ot = _generate_json(
        _SYSTEM_INSTRUCTION,
        _build_prompt(project, source_text, num_parts, guidance),
        _EPISODE_SCHEMA,
    )
    episodes = _parse_episodes(text)
    return GenResult(
        episodes=episodes, model=model, prompt_tokens=pt, output_tokens=ot,
        cost=_estimate_cost(model, pt, ot),
    )


def _loads(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Could not parse the model's JSON response: {exc}") from exc
    if not isinstance(data, dict):
        raise LLMError("The model's response was not a JSON object.")
    return data


def _parse_episodes(text: str) -> list[dict]:
    raw = _loads(text).get("episodes")
    if not isinstance(raw, list) or not raw:
        raise LLMError("Gemini's response contained no episodes.")
    episodes: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        episodes.append(
            {
                "title": str(item.get("title", "")).strip(),
                "hook": str(item.get("hook", "")).strip(),
                "previously": str(item.get("previously", "")).strip(),
                "narration_script": str(item.get("narration_script", "")).strip(),
                "cliffhanger": str(item.get("cliffhanger", "")).strip(),
            }
        )
    if not episodes:
        raise LLMError("Gemini's response contained no usable episodes.")
    return episodes


# --------------------------------------------------------------------------- #
# shot-list generation (Milestone 4)
# --------------------------------------------------------------------------- #

_SHOT_SCHEMA = {
    "type": "object",
    "properties": {
        "shots": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "narration_excerpt": {"type": "string"},
                    "duration": {"type": "number"},
                    "prompt": {"type": "string"},
                    "camera_motion": {"type": "string"},
                    "audio_description": {"type": "string"},
                },
                "required": ["narration_excerpt", "duration", "prompt"],
                "propertyOrdering": [
                    "narration_excerpt", "duration", "prompt",
                    "camera_motion", "audio_description",
                ],
            },
        }
    },
    "required": ["shots"],
}

_SHOT_SYSTEM = (
    "You are a cinematographer and shot designer for vertical (9:16) short-form "
    "horror videos that retell SCP Foundation stories over narration. Given an "
    "episode's narration, break it into an ordered sequence of short shots whose "
    "visuals, read end to end, cover the whole narration.\n\n"
    "For every shot:\n"
    "- narration_excerpt: the exact span of narration this shot plays under. In "
    "order, the excerpts must cover the narration with no large gaps.\n"
    "- duration: seconds of footage, between 4 and 8 (AI video clips are short). "
    "Match it roughly to how long the excerpt takes to read aloud.\n"
    "- prompt: a vivid, concrete visual description for an AI video generator — "
    "subject, setting, lighting, lens/framing, atmosphere. Vertical 9:16. Describe "
    "ONLY what is on screen. No on-screen text, captions, logos or watermarks. Do "
    "NOT restate the house style (it is added automatically); focus on this shot.\n"
    "- camera_motion: a short phrase, e.g. 'slow push in', 'handheld pan left', "
    "'static locked-off', 'crane up'.\n"
    "- audio_description: a brief ambient/sound-design note for the shot (the "
    "generator can add audio), e.g. 'low hum, distant dripping water'.\n\n"
    "Keep it faithful and grounded. Avoid gore or anything a platform would reject. "
    "Return only the structured data requested."
)


def _build_shot_prompt(project: dict, episode: dict, avg_secs: float) -> str:
    spoken = "\n".join(
        s for s in [
            episode.get("hook", ""),
            episode.get("narration_script", ""),
            episode.get("cliffhanger", ""),
        ] if s and s.strip()
    )
    lines = [
        f"SCP designation: {project.get('scp_number') or '(unknown)'}",
        f"Episode: Part {episode.get('part_number', 1)} — "
        f"{episode.get('title') or '(untitled)'}",
        f"Aim for shots of about {avg_secs:.0f} seconds each; use as many shots as "
        "it takes to cover the narration, and do not pad.",
        "",
        "NARRATION to illustrate (verbatim, between the markers):",
        "<<<NARRATION",
        spoken,
        "NARRATION>>>",
    ]
    style = (project.get("style_bible") or "").strip()
    if style:
        lines += [
            "",
            "House style (already applied to every generated shot — do not repeat "
            f"it in the prompts, just design shots that fit it):\n{style}",
        ]
    return "\n".join(lines)


def generate_shot_list(
    project: dict, episode: dict, avg_shot_secs: float = 6.0
) -> GenResult:
    """Break an episode's narration into an ordered shot list via Gemini."""
    spoken = " ".join(
        s for s in [
            episode.get("hook", ""),
            episode.get("narration_script", ""),
            episode.get("cliffhanger", ""),
        ] if s
    ).strip()
    if not spoken:
        raise LLMError("Write the episode script before generating a shot list.")

    text, model, pt, ot = _generate_json(
        _SHOT_SYSTEM,
        _build_shot_prompt(project, episode, avg_shot_secs),
        _SHOT_SCHEMA,
        temperature=0.8,
    )
    shots = _parse_shots(text)
    # GenResult.episodes carries the shot dicts; keeps one result shape.
    return GenResult(
        episodes=shots, model=model, prompt_tokens=pt, output_tokens=ot,
        cost=_estimate_cost(model, pt, ot),
    )


def _parse_shots(text: str) -> list[dict]:
    raw = _loads(text).get("shots")
    if not isinstance(raw, list) or not raw:
        raise LLMError("The model's response contained no shots.")
    shots: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            dur = float(item.get("duration") or 6.0)
        except (TypeError, ValueError):
            dur = 6.0
        dur = max(2.0, min(8.0, dur))  # keep within AI-clip limits
        shots.append(
            {
                "narration_excerpt": str(item.get("narration_excerpt", "")).strip(),
                "duration": round(dur, 1),
                "prompt": str(item.get("prompt", "")).strip(),
                "camera_motion": str(item.get("camera_motion", "")).strip(),
                "audio_description": str(item.get("audio_description", "")).strip(),
            }
        )
    if not shots:
        raise LLMError("Gemini's response contained no usable shots.")
    return shots


# --------------------------------------------------------------------------- #
# combined one-shot generation (Milestone 4 auto-generate): episodes + shots
# --------------------------------------------------------------------------- #

_FULL_SCHEMA = {
    "type": "object",
    "properties": {
        "episodes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "previously": {"type": "string"},
                    "narration_script": {"type": "string"},
                    "cliffhanger": {"type": "string"},
                    "shots": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "narration_excerpt": {"type": "string"},
                                "duration": {"type": "number"},
                                "prompt": {"type": "string"},
                                "camera_motion": {"type": "string"},
                                "audio_description": {"type": "string"},
                            },
                            "required": ["narration_excerpt", "duration", "prompt"],
                            "propertyOrdering": [
                                "narration_excerpt", "duration", "prompt",
                                "camera_motion", "audio_description",
                            ],
                        },
                    },
                },
                "required": [
                    "title", "hook", "narration_script", "cliffhanger", "shots",
                ],
                "propertyOrdering": [
                    "title", "hook", "previously", "narration_script",
                    "cliffhanger", "shots",
                ],
            },
        }
    },
    "required": ["episodes"],
}

_FULL_SYSTEM = (
    _SYSTEM_INSTRUCTION
    + "\n\nIn the SAME response, also design the SHOTS for each episode — the "
    "ordered footage that plays under its narration. Put them in that episode's "
    "'shots' array. For every shot:\n"
    "- narration_excerpt: the span of that episode's narration the shot plays "
    "under; in order the excerpts cover the whole episode.\n"
    "- duration: 4 to 8 seconds (AI video clips are short).\n"
    "- prompt: a vivid, concrete visual description for an AI video generator — "
    "subject, setting, lighting, framing, atmosphere; vertical 9:16; only what is "
    "on screen; no on-screen text/logos; do not restate the house style.\n"
    "- camera_motion: a short phrase (e.g. 'slow push in', 'static locked-off').\n"
    "- audio_description: a brief ambient/sound note.\n"
    "Keep prompts tight so the whole reply fits. Return only the structured data."
)


def generate_full(
    project: dict, source_text: str, num_parts: int = 0,
    guidance: str = "", avg_shot_secs: float = 6.0, status_cb=None,
) -> GenResult:
    """One request: split the story into episodes AND design each one's shots.

    GenResult.episodes holds episode dicts, each with a nested 'shots' list.
    """
    if not (source_text or "").strip():
        raise LLMError("The source story is empty — nothing to generate from.")
    extra = (guidance or "").strip()
    guide = (
        extra + "\n" if extra else ""
    ) + f"Aim for shots of about {avg_shot_secs:.0f} seconds each."
    text, model, pt, ot = _generate_json(
        _FULL_SYSTEM,
        _build_prompt(project, source_text, num_parts, guide),
        _FULL_SCHEMA,
        status_cb=status_cb,
    )
    episodes = _parse_full(text)
    return GenResult(
        episodes=episodes, model=model, prompt_tokens=pt, output_tokens=ot,
        cost=_estimate_cost(model, pt, ot),
    )


def _parse_full(text: str) -> list[dict]:
    raw = _loads(text).get("episodes")
    if not isinstance(raw, list) or not raw:
        raise LLMError("The model's response contained no episodes.")
    episodes: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        shots: list[dict] = []
        for sh in item.get("shots") or []:
            if not isinstance(sh, dict):
                continue
            try:
                dur = float(sh.get("duration") or 6.0)
            except (TypeError, ValueError):
                dur = 6.0
            shots.append({
                "narration_excerpt": str(sh.get("narration_excerpt", "")).strip(),
                "duration": round(max(2.0, min(8.0, dur)), 1),
                "prompt": str(sh.get("prompt", "")).strip(),
                "camera_motion": str(sh.get("camera_motion", "")).strip(),
                "audio_description": str(sh.get("audio_description", "")).strip(),
            })
        episodes.append({
            "title": str(item.get("title", "")).strip(),
            "hook": str(item.get("hook", "")).strip(),
            "previously": str(item.get("previously", "")).strip(),
            "narration_script": str(item.get("narration_script", "")).strip(),
            "cliffhanger": str(item.get("cliffhanger", "")).strip(),
            "shots": shots,
        })
    if not episodes:
        raise LLMError("Gemini's response contained no usable episodes.")
    return episodes
