"""Layout helpers for Pillow text rendering."""

from __future__ import annotations

from PIL import ImageDraw, ImageFont


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    lines: list[str] = []
    for paragraph in text.splitlines() or [text]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue

        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            width, _ = text_size(draw, candidate, font)
            if width <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word

        if current:
            lines.append(current)
    return lines


def multiline_height(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    font: ImageFont.ImageFont,
    line_spacing: int,
) -> int:
    if not lines:
        return 0
    heights = [text_size(draw, line or " ", font)[1] for line in lines]
    return sum(heights) + line_spacing * (len(lines) - 1)

