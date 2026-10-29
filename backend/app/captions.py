"""Caption generation.

Word timestamps come from faster-whisper (CPU). That package depends on
binary wheels (ctranslate2, av) that may not exist for a brand-new Python yet,
so every entry point degrades gracefully: if the model can't load, rendering
simply proceeds without burned-in captions.
"""

from __future__ import annotations

from functools import lru_cache

# Canvas is the final vertical video size.
PLAY_W = 1080
PLAY_H = 1920


def whisper_available() -> tuple[bool, str]:
    try:
        import faster_whisper  # noqa: F401

        return True, ""
    except Exception as exc:  # pragma: no cover - env dependent
        return False, f"{type(exc).__name__}: {exc}"


@lru_cache(maxsize=2)
def _load_model(size: str):
    from faster_whisper import WhisperModel

    # int8 keeps it light on a CPU-only laptop.
    return WhisperModel(size, device="cpu", compute_type="int8")


def transcribe_words(audio_path: str, model_size: str = "base") -> list[dict]:
    """Return [{'word': str, 'start': float, 'end': float}, ...].

    Raises if faster-whisper is unavailable; callers decide whether that's fatal.
    """
    model = _load_model(model_size)
    segments, _info = model.transcribe(
        audio_path, word_timestamps=True, vad_filter=True
    )
    words: list[dict] = []
    for seg in segments:
        for w in seg.words or []:
            text = (w.word or "").strip()
            if not text:
                continue
            words.append({"word": text, "start": float(w.start), "end": float(w.end)})
    return words


# --------------------------------------------------------------------------- #
# ASS subtitle generation
# --------------------------------------------------------------------------- #

def _ass_time(t: float) -> str:
    if t < 0:
        t = 0.0
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _ass_header(font: str, font_size: int) -> str:
    # Colours are &HAABBGGRR. White fill, black outline, strong shadow.
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {PLAY_W}
PlayResY: {PLAY_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Base,{font},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,3,2,80,80,520,1
Style: Hi,{font},{font_size},&H0000F0FF,&H000000FF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,3,2,80,80,520,1

[Events]
Format: Layer, Start, End, Style, MarginL, MarginR, MarginV, Effect, Text
"""


def _escape(text: str) -> str:
    return text.replace("{", "(").replace("}", ")").replace("\n", " ")


def build_ass(
    words: list[dict],
    offset: float = 0.0,
    mode: str = "word",
    font: str = "Arial",
    font_size: int = 92,
    phrase_size: int = 5,
) -> str:
    """Build an ASS document string.

    offset   seconds to add to every timestamp (narration starts after the
             title card, but whisper timed it from 0).
    mode     'word'   -> one big word at a time.
             'phrase' -> show a short phrase, highlighting the active word.
    """
    lines = [_ass_header(font, font_size)]

    def ev(start, end, style, text):
        lines.append(
            f"Dialogue: 0,{_ass_time(start + offset)},{_ass_time(end + offset)},"
            f"{style},,0,0,0,,{text}"
        )

    if not words:
        return "".join(l + "\n" for l in lines)

    if mode == "phrase":
        # Group into short phrases, highlight the currently spoken word.
        for i in range(0, len(words), phrase_size):
            group = words[i : i + phrase_size]
            for j, w in enumerate(group):
                start = w["start"]
                end = group[j + 1]["start"] if j + 1 < len(group) else w["end"]
                parts = []
                for k, g in enumerate(group):
                    token = _escape(g["word"])
                    if k == j:
                        parts.append(r"{\c&H0000F0FF&}" + token + r"{\c&H00FFFFFF&}")
                    else:
                        parts.append(token)
                ev(start, max(end, start + 0.05), "Base", " ".join(parts))
    else:
        # Word-by-word: each word shown until the next begins.
        for j, w in enumerate(words):
            start = w["start"]
            end = words[j + 1]["start"] if j + 1 < len(words) else w["end"]
            ev(start, max(end, start + 0.05), "Hi", _escape(w["word"]))

    return "".join(l + "\n" for l in lines)
