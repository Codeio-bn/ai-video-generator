"""LLM provider seam (Milestone 2: script generation).

The rest of the app talks to this module, never to a vendor SDK, so the Gemini
API-key path here can later be swapped for Vertex AI (or any other backend)
without touching the routers.

Gemini is called over its REST API with ``requests`` on purpose: it adds no new
dependency (``requests`` is already vendored for FFmpeg download / M1) and keeps
us off the ``google-genai`` SDK's transitive wheels, which are risky on brand-new
Python builds (see the project's environment notes).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from .config import get_secret

# Latest fast, cheap multimodal model. Override with the GEMINI_MODEL secret/env.
DEFAULT_MODEL = "gemini-2.5-flash"
_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
_TIMEOUT = 120  # seconds; a multi-episode split can take a while

# Rough public list price (USD per 1M tokens) for cost logging. These are
# estimates for budget awareness only, not billing-accurate.
_PRICING = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.0-flash": (0.10, 0.40),
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


def model_name() -> str:
    return get_secret("GEMINI_MODEL") or DEFAULT_MODEL


def _require_key() -> str:
    key = get_secret("GEMINI_API_KEY")
    if not key:
        raise LLMError(
            "No Google Gemini API key is saved. Add one under Settings "
            "(get a key from Google AI Studio)."
        )
    return key


def _estimate_cost(model: str, prompt_tokens: int, output_tokens: int) -> float:
    in_price, out_price = _PRICING.get(model, (0.0, 0.0))
    return (prompt_tokens * in_price + output_tokens * out_price) / 1_000_000


def check_connection() -> dict:
    """Light round-trip used by the Settings 'Test connection' button."""
    key = get_secret("GEMINI_API_KEY")
    if not key:
        return {"ok": False, "detail": "No Gemini API key saved yet."}
    model = model_name()
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
        msg = err.get("message") or resp.text
    except ValueError:
        msg = resp.text or resp.reason
    if resp.status_code in (401, 403):
        return f"Authentication failed ({resp.status_code}). Check the API key. {msg}"
    if resp.status_code == 429:
        return f"Rate limited by Gemini (429). Try again shortly. {msg}"
    return f"Gemini returned HTTP {resp.status_code}: {msg}"


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
    "speaker labels, no markdown. Pace it so reading aloud fits roughly the "
    "target length. Build dread; keep sentences short and voiceover-friendly.\n"
    "- cliffhanger: a final line that lands the beat and, except for the last "
    "episode, makes the viewer need part N+1.\n"
    "- previously: for every episode after the first, a single sentence recap of "
    "where the last part left off. Leave it empty for episode 1.\n"
    "- title: a short, evocative episode title (not just 'Part N').\n\n"
    "Stay faithful to the source. Do not invent a different ending. Return only "
    "the structured data requested."
)


def _build_prompt(
    project: dict, source_text: str, num_parts: int, guidance: str
) -> str:
    target = project.get("target_episode_length") or 61
    parts_line = (
        f"Split the story into exactly {num_parts} episodes."
        if num_parts and num_parts > 0
        else "Choose a sensible number of episodes (usually 1–6) based on how much "
        "story there is; do not pad."
    )
    lines = [
        f"SCP designation: {project.get('scp_number') or '(unknown)'}",
        f"Working title: {project.get('title') or '(none)'}",
        f"Language: {project.get('language') or 'en'}",
        f"Target spoken length per episode: about {target} seconds "
        "(roughly {} words).".format(int(target * 2.6)),
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


def generate_episodes(
    project: dict,
    source_text: str,
    num_parts: int = 0,
    guidance: str = "",
) -> GenResult:
    """Turn a source story into structured episode drafts via Gemini."""
    if not (source_text or "").strip():
        raise LLMError("The source story is empty — paste the SCP text first.")
    key = _require_key()
    model = model_name()

    body = {
        "systemInstruction": {"parts": [{"text": _SYSTEM_INSTRUCTION}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": _build_prompt(project, source_text, num_parts, guidance)}
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.9,
            "responseMimeType": "application/json",
            "responseSchema": _EPISODE_SCHEMA,
        },
    }

    url = f"{_API_ROOT}/models/{model}:generateContent"
    try:
        resp = requests.post(
            url, params={"key": key}, json=body, timeout=_TIMEOUT
        )
    except requests.Timeout as exc:
        raise LLMError(
            "Gemini took too long to respond. Try a shorter story or fewer parts."
        ) from exc
    except requests.RequestException as exc:
        raise LLMError(f"Could not reach Gemini: {exc}") from exc

    if resp.status_code != 200:
        raise LLMError(_http_error_detail(resp))

    payload = resp.json()
    episodes = _parse_episodes(payload)
    usage = payload.get("usageMetadata", {})
    prompt_tokens = int(usage.get("promptTokenCount", 0))
    output_tokens = int(usage.get("candidatesTokenCount", 0))
    return GenResult(
        episodes=episodes,
        model=model,
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        cost=_estimate_cost(model, prompt_tokens, output_tokens),
    )


def _parse_episodes(payload: dict) -> list[dict]:
    candidates = payload.get("candidates") or []
    if not candidates:
        block = payload.get("promptFeedback", {}).get("blockReason")
        if block:
            raise LLMError(
                f"Gemini blocked this request ({block}). Try different source text."
            )
        raise LLMError("Gemini returned no content.")

    cand = candidates[0]
    finish = cand.get("finishReason")
    if finish == "SAFETY":
        raise LLMError("Gemini stopped for safety reasons on this story.")

    parts = cand.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise LLMError(
            "Gemini returned an empty response"
            + (f" (finishReason={finish})." if finish else ".")
        )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMError(f"Could not parse Gemini's JSON response: {exc}") from exc

    raw = data.get("episodes") if isinstance(data, dict) else None
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
