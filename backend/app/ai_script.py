"""Script generation via OpenAI (the "write the story" half of the AI link).

Given a real SCP article, OpenAI returns a tight 30-second script split into
5-6 scenes. Each scene carries three things the rest of the pipeline needs:

    narration  - one short spoken line (read aloud by TTS)
    visual     - a cinematic description of the shot (fed to Veo)
    sound      - ambient / sound-design notes (fed to Veo)

Plain ``requests`` against OpenAI's chat-completions API (JSON mode) — no SDK,
so nothing risky to install on Python 3.15.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass

import requests

from .config import get_secret

_URL = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"
_TIMEOUT = 90
_MAX_ATTEMPTS = 3
_RETRY_STATUSES = {429, 500, 502, 503, 504}

MIN_SCENES = 5
MAX_SCENES = 6
TARGET_SECONDS = 30

_SYSTEM = (
    "You are a scriptwriter for 30-second vertical (9:16) SCP horror shorts for "
    "TikTok/Shorts. You retell a real SCP article as a tense, cinematic micro-story "
    "that hooks in the first 2 seconds and ends on a chilling beat. You write for "
    "an AI video generator, so every scene's visual is concrete and filmable."
)

_INSTRUCTIONS = f"""\
Write a script of {MIN_SCENES} to {MAX_SCENES} scenes that runs about \
{TARGET_SECONDS} seconds total when the narration is read aloud.

Rules:
- The WHOLE narration across all scenes must be about 70-80 words (≈{TARGET_SECONDS}s).
- Each scene's `narration` is ONE short sentence (roughly 2-5 seconds spoken).
- `visual` describes a single filmable shot for an AI video model: setting,
  subject, lighting, mood, camera framing/motion. Dark, grainy, cinematic SCP
  aesthetic. 9:16 vertical. No on-screen text. One continuous shot, ~5 seconds.
- `sound` is short ambient / sound-design (e.g. "low hum, distant dripping").
- Scene 1 is a hook; the last scene is an ominous cliffhanger.
- Be faithful to the SCP but dramatize it. Do not invent a different SCP.

Return ONLY a JSON object of this exact shape (no markdown, no commentary):
{{"title": string, "scenes": [{{"narration": string, "visual": string, "sound": string}}]}}
"""


class ScriptError(RuntimeError):
    """User-facing failure while generating the script."""


@dataclass
class ScriptResult:
    title: str
    scenes: list[dict]          # each: {narration, visual, sound}
    model: str
    prompt_tokens: int
    output_tokens: int


def model_name() -> str:
    return get_secret("OPENAI_MODEL") or DEFAULT_MODEL


def available() -> tuple[bool, str]:
    if not get_secret("OPENAI_API_KEY"):
        return False, "No OpenAI API key saved — the script writer needs one."
    return True, f"Ready (model {model_name()})."


def generate_script(source_text: str, *, guidance: str = "",
                    status_cb=None) -> ScriptResult:
    key = get_secret("OPENAI_API_KEY")
    if not key:
        raise ScriptError(
            "No OpenAI API key saved. Add one under Settings "
            "(get a key from platform.openai.com).")

    user = _INSTRUCTIONS
    if (guidance or "").strip():
        user += f"\nExtra direction from the editor: {guidance.strip()}\n"
    user += (
        "\nSOURCE SCP ARTICLE (verbatim, between the markers):\n<<<SCP\n"
        + source_text.strip()[:12000] + "\nSCP>>>"
    )

    body = {
        "model": model_name(),
        "temperature": 0.9,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user},
        ],
    }
    payload = _post(body, key, status_cb)
    choices = payload.get("choices") or []
    if not choices:
        raise ScriptError("OpenAI returned no content.")
    if choices[0].get("finish_reason") == "length":
        raise ScriptError("OpenAI's reply was cut off — try again.")
    text = ((choices[0].get("message") or {}).get("content") or "").strip()
    data = _loads(text)

    scenes = _clean_scenes(data.get("scenes"))
    if not scenes:
        raise ScriptError("OpenAI didn't return any usable scenes. Try again.")
    usage = payload.get("usage", {})
    return ScriptResult(
        title=(data.get("title") or "").strip(),
        scenes=scenes,
        model=model_name(),
        prompt_tokens=int(usage.get("prompt_tokens", 0)),
        output_tokens=int(usage.get("completion_tokens", 0)),
    )


# --------------------------------------------------------------------------- #
# internals
# --------------------------------------------------------------------------- #

def _clean_scenes(raw) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out = []
    for s in raw[:MAX_SCENES]:
        if not isinstance(s, dict):
            continue
        narration = str(s.get("narration") or "").strip()
        visual = str(s.get("visual") or "").strip()
        sound = str(s.get("sound") or "").strip()
        if narration or visual:
            out.append({"narration": narration, "visual": visual, "sound": sound})
    return out


def _loads(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Salvage a JSON object embedded in stray prose.
        start, end = text.find("{"), text.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise ScriptError("OpenAI returned a response that wasn't valid JSON.")


def _post(body: dict, key: str, status_cb) -> dict:
    def note(msg: str) -> None:
        print(f"[script] {msg}", flush=True)
        if status_cb:
            try:
                status_cb(msg)
            except Exception:  # noqa: BLE001
                pass

    last = "unknown error"
    for attempt in range(_MAX_ATTEMPTS):
        note(f"Asking OpenAI for the script (attempt {attempt + 1}/{_MAX_ATTEMPTS})…")
        try:
            resp = requests.post(_URL, headers={"Authorization": f"Bearer {key}"},
                                 json=body, timeout=_TIMEOUT)
        except requests.Timeout:
            last = f"OpenAI didn't respond within {_TIMEOUT}s."
        except requests.RequestException as exc:
            last = f"Could not reach OpenAI: {exc}"
        else:
            if resp.status_code == 200:
                return resp.json()
            last = _http_error(resp)
            if resp.status_code not in _RETRY_STATUSES:
                raise ScriptError(last)
        if attempt < _MAX_ATTEMPTS - 1:
            time.sleep(2.0 * (2 ** attempt))
    raise ScriptError(f"{last} OpenAI stayed unavailable after {_MAX_ATTEMPTS} attempts.")


def _http_error(resp: requests.Response) -> str:
    try:
        msg = (resp.json().get("error") or {}).get("message") or resp.text
    except ValueError:
        msg = resp.text or resp.reason
    if resp.status_code in (401, 403):
        return f"OpenAI rejected the API key ({resp.status_code}). {msg}"
    if resp.status_code == 404:
        return f"OpenAI model not found (404) — set OPENAI_MODEL. {msg}"
    if resp.status_code == 429:
        return f"OpenAI rate-limited the request (429). {msg}"
    return f"OpenAI returned HTTP {resp.status_code}: {msg}"
