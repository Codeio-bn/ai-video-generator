"""Render title / text / attribution cards to PNG with Pillow.

Doing cards as images (rather than FFmpeg drawtext) avoids Windows font-path
escaping pain and gives real word-wrapping and centering.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .config import find_system_font

W, H = 1080, 1920
_FONT_PATH = find_system_font()


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if _FONT_PATH is not None:
        try:
            return ImageFont.truetype(str(_FONT_PATH), size)
        except OSError:
            pass
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph:
            lines.append("")
            continue
        words = paragraph.split(" ")
        cur = ""
        for word in words:
            trial = f"{cur} {word}".strip()
            if draw.textlength(trial, font=font) <= max_width or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
    return lines


def _draw_block(
    draw: ImageDraw.ImageDraw,
    blocks: list[tuple[str, int, tuple]],
    top: int,
    max_width: int,
    line_gap: int = 18,
    block_gap: int = 48,
    align_center: bool = True,
) -> int:
    """Draw a sequence of (text, font_size, color) blocks stacked vertically."""
    y = top
    for idx, (text, size, color) in enumerate(blocks):
        font = _font(size)
        for line in _wrap(draw, text, font, max_width):
            tw = draw.textlength(line, font=font)
            x = (W - tw) / 2 if align_center else (W - max_width) / 2
            # subtle shadow for contrast
            draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0))
            draw.text((x, y), line, font=font, fill=color)
            bbox = font.getbbox(line or "Ag")
            y += (bbox[3] - bbox[1]) + line_gap
        if idx < len(blocks) - 1:
            y += block_gap
    return y


def title_card(path: Path, part_number: int, title: str, bg=(8, 8, 10)) -> Path:
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    blocks = [
        (f"PART {part_number}", 150, (235, 40, 40)),
        (title or "", 70, (240, 240, 240)),
    ]
    # Roughly vertically centered.
    _draw_block(draw, blocks, top=int(H * 0.36), max_width=int(W * 0.82))
    img.save(path)
    return path


def text_card(path: Path, text: str, bg=(8, 8, 10)) -> Path:
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    _draw_block(
        draw,
        [(text or "", 84, (240, 240, 240))],
        top=int(H * 0.40),
        max_width=int(W * 0.82),
    )
    img.save(path)
    return path


def attribution_card(
    path: Path,
    scp_number: str,
    title: str,
    authors: str,
    source_url: str,
    license_name: str = "CC BY-SA 3.0",
    bg=(8, 8, 10),
) -> Path:
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    heading = f"{scp_number}: {title}".strip(": ").strip()
    blocks = [
        ("ATTRIBUTION", 56, (235, 40, 40)),
        (heading, 68, (245, 245, 245)),
        (f"by {authors}", 52, (205, 205, 205)),
        (source_url, 40, (150, 180, 230)),
        (f"Licensed under {license_name}.", 46, (210, 210, 210)),
        (f"This video is also released under {license_name}.", 42, (190, 190, 190)),
    ]
    _draw_block(
        draw, blocks, top=int(H * 0.22), max_width=int(W * 0.86), block_gap=40
    )
    img.save(path)
    return path
