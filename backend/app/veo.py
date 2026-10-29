"""Video generation via Google Veo (the "make the video" half of the AI link).

Reached over the Generative Language REST API with plain ``requests`` (no SDK).
Veo is a long-running operation: POST a prompt, get an operation name, poll it
until done, then download the finished clip. Runs only inside a background job.

Veo access is gated per key and the model ids change, so the real model id is
auto-resolved from the account's model list (any model advertising the
``predictLongRunning`` method), overridable with the VEO_MODEL secret/env.

Veo costs real money. Veo is only available on a paid/billed Gemini API project.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path

import requests

from .config import get_secret

_API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_VEO_MODEL = "veo-3.0-fast-generate-001"   # fallback only
DEFAULT_PRICE_PER_SEC = 0.40                        # USD, rough — override VEO_PRICE_PER_SEC
DEFAULT_CLIP_SECONDS = 8.0                          # Veo 3 returns ~8s clips

_VEO_METHOD = "predictLongRunning"
_VEO_PREFS = ("veo", "fast")
_REQUEST_TIMEOUT = 60
_POLL_INTERVAL = 10
_POLL_TIMEOUT = 420

# {api_key: (model_id, reason)} — positives only, so enabling billing is noticed.
_resolve_cache: dict[str, tuple[str, str]] = {}


class VeoError(RuntimeError):
    """User-facing failure while generating a clip."""


def price_per_sec() -> float:
    raw = get_secret("VEO_PRICE_PER_SEC")
    try:
        return float(raw) if raw else DEFAULT_PRICE_PER_SEC
    except (TypeError, ValueError):
        return DEFAULT_PRICE_PER_SEC


def clip_seconds() -> float:
    raw = get_secret("VEO_DURATION")
    try:
        return float(raw) if raw else DEFAULT_CLIP_SECONDS
    except (TypeError, ValueError):
        return DEFAULT_CLIP_SECONDS


def estimate_cost(seconds: float | None = None) -> float:
    return max(0.0, seconds if seconds is not None else clip_seconds()) * price_per_sec()


def clear_cache() -> None:
    _resolve_cache.clear()


def available() -> tuple[bool, str]:
    key = get_secret("GEMINI_API_KEY")
    if not key:
        return False, "No Google Gemini API key saved — Veo needs one."
    model, reason = _resolve_model(key)
    return (bool(model), reason)


def model_name() -> str:
    override = get_secret("VEO_MODEL")
    if override:
        return override
    key = get_secret("GEMINI_API_KEY")
    if key:
        model, _ = _resolve_model(key)
        if model:
            return model
    return DEFAULT_VEO_MODEL


def compose_prompt(visual: str, sound: str, style: str = "") -> str:
    """Fold the shot visual + sound design (+ optional house style) into one prompt."""
    parts = [p.strip() for p in (style, visual) if (p or "").strip()]
    if (sound or "").strip():
        parts.append(f"Audio: {sound.strip()}.")
    return "\n\n".join(parts).strip()


def generate_clip(prompt: str, dest: Path, *, aspect_ratio: str = "9:16",
                  status_cb=None) -> Path:
    key = get_secret("GEMINI_API_KEY")
    if not key:
        raise VeoError("No Google Gemini API key saved. Add one under Settings.")
    model, reason = _resolve_model(key)
    if not model:
        raise VeoError(reason)

    def note(msg: str) -> None:
        print(f"[veo] {msg}", flush=True)
        if status_cb:
            try:
                status_cb(msg)
            except Exception:  # noqa: BLE001
                pass

    params = {"aspectRatio": aspect_ratio}
    person = get_secret("VEO_PERSON_GENERATION")
    if person:
        params["personGeneration"] = person
    body = {"instances": [{"prompt": prompt}], "parameters": params}

    note(f"Submitting to Veo ({model})…")
    op = _submit(f"{_API_ROOT}/models/{model}:predictLongRunning", key, body)
    note("Veo accepted the job — rendering (this can take a few minutes)…")
    response = _poll(op, key, note)

    uri, raw = _extract_video(response)
    if raw is None and uri:
        note("Downloading the finished clip…")
        raw = _download(uri, key)
    if not raw:
        raise VeoError("Veo finished but returned no video data.")

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    note(f"Saved {len(raw) // 1024} KB clip.")
    return dest


# --------------------------------------------------------------------------- #
# internals
# --------------------------------------------------------------------------- #

def _list_models(key: str) -> list[dict]:
    out: list[dict] = []
    token = None
    try:
        for _ in range(10):
            params = {"key": key, "pageSize": 200}
            if token:
                params["pageToken"] = token
            resp = requests.get(f"{_API_ROOT}/models", params=params, timeout=20)
            if resp.status_code != 200:
                break
            body = resp.json()
            out += body.get("models", [])
            token = body.get("nextPageToken")
            if not token:
                break
    except (requests.RequestException, ValueError):
        pass
    return out


def _resolve_model(key: str) -> tuple[str | None, str]:
    override = get_secret("VEO_MODEL")
    if override:
        return override, f"Using VEO_MODEL override “{override}”."
    if key in _resolve_cache:
        return _resolve_cache[key]

    models = _list_models(key)
    candidates = [
        m.get("name", "").split("/")[-1]
        for m in models if _VEO_METHOD in m.get("supportedGenerationMethods", [])
    ]
    pick = next((c for c in candidates if all(p in c.lower() for p in _VEO_PREFS)), None)
    pick = pick or next((c for c in candidates if "veo" in c.lower()), None)
    pick = pick or (candidates[0] if candidates else None)

    if pick:
        result = (pick, f"Veo model “{pick}” available.")
        _resolve_cache[key] = result
        return result
    if models:
        return None, ("This Google Gemini API key has no Veo video model. Veo needs "
                      "a paid/billed Gemini API project — enable billing (or use a key "
                      "with Veo access), then try again. You can also set VEO_MODEL "
                      "manually if you know your model id.")
    return None, "Couldn't read the model list for this Gemini key — check the key."


def _submit(url: str, key: str, body: dict) -> str:
    try:
        resp = requests.post(url, params={"key": key}, json=body, timeout=_REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise VeoError(f"Could not reach Veo: {exc}") from exc
    if resp.status_code != 200:
        raise VeoError(_http_error(resp))
    name = (resp.json() or {}).get("name")
    if not name:
        raise VeoError("Veo did not return an operation to track.")
    return name


def _poll(op_name: str, key: str, note) -> dict:
    url = f"{_API_ROOT}/{op_name}"
    deadline = time.monotonic() + _POLL_TIMEOUT
    waited = 0
    while True:
        try:
            resp = requests.get(url, params={"key": key}, timeout=_REQUEST_TIMEOUT)
        except requests.RequestException as exc:
            raise VeoError(f"Lost contact with Veo while rendering: {exc}") from exc
        if resp.status_code != 200:
            raise VeoError(_http_error(resp))
        op = resp.json() or {}
        if op.get("done"):
            err = op.get("error")
            if err:
                msg = err.get("message") if isinstance(err, dict) else str(err)
                raise VeoError(f"Veo failed: {msg}")
            return op.get("response") or {}
        if time.monotonic() >= deadline:
            raise VeoError(f"Veo didn't finish within {_POLL_TIMEOUT // 60} minutes. "
                           "Try again, or set VEO_MODEL to a faster model.")
        waited += _POLL_INTERVAL
        note(f"Still rendering… ({waited}s elapsed)")
        time.sleep(_POLL_INTERVAL)


def _extract_video(response: dict) -> tuple[str | None, bytes | None]:
    gvr = response.get("generateVideoResponse") or response
    samples = (gvr.get("generatedSamples") or gvr.get("samples")
               or gvr.get("videos") or response.get("predictions") or [])
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        video = sample.get("video") or sample
        if isinstance(video, dict):
            uri = video.get("uri") or video.get("url")
            if uri:
                return uri, None
            b64 = (video.get("videoBytes") or video.get("bytesBase64Encoded")
                   or video.get("encodedVideo"))
            if b64:
                try:
                    return None, base64.b64decode(b64)
                except (ValueError, TypeError):
                    pass
        elif isinstance(video, str):
            try:
                return None, base64.b64decode(video)
            except (ValueError, TypeError):
                pass
    return None, None


def _download(uri: str, key: str) -> bytes:
    try:
        resp = requests.get(uri, params={"key": key}, timeout=_REQUEST_TIMEOUT * 3)
    except requests.RequestException as exc:
        raise VeoError(f"Could not download the finished clip: {exc}") from exc
    if resp.status_code != 200:
        raise VeoError(f"Downloading the clip failed (HTTP {resp.status_code}).")
    return resp.content


def _http_error(resp: requests.Response) -> str:
    try:
        msg = (resp.json().get("error") or {}).get("message") or resp.text
    except ValueError:
        msg = resp.text or resp.reason
    if resp.status_code in (401, 403):
        return f"Gemini rejected the API key ({resp.status_code}). {msg}"
    if resp.status_code == 404:
        return (f"Veo model not found (404) — your key may lack Veo access, or set "
                f"VEO_MODEL to an available one. {msg}")
    if resp.status_code == 429:
        return f"Veo rate-limited the request (429). {msg}"
    return f"Veo returned HTTP {resp.status_code}: {msg}"
