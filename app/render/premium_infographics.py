"""Premium motion infographic scenes for vertical Reels."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from app.render.fonts import load_font
from app.render.layout import text_size
from app.render.native_reel_renderer import REEL_SIZE


CARD_LABELS = ["Oil Up", "Import Bill Up", "Dollar Demand Up", "Currency Pressure Up"]


def create_premium_infographic_still(scene: Any, output_path: Path, progress: float = 1.0) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = oil_dollar_premium_infographic(scene, progress)
    image.save(output_path, "JPEG", quality=95, optimize=True)
    return output_path


def oil_dollar_premium_infographic(scene: Any, progress: float = 1.0) -> Image.Image:
    progress = max(0.0, min(1.0, progress))
    image = Image.new("RGB", REEL_SIZE, (18, 24, 28))
    draw = ImageDraw.Draw(image, "RGBA")
    _draw_background(draw)
    _draw_header(draw, progress)
    card_positions = [(104, 430), (574, 430), (104, 790), (574, 790)]
    for index, (label, pos) in enumerate(zip(CARD_LABELS, card_positions)):
        appear = min(1.0, max(0.0, (progress - index * 0.12) / 0.22))
        _draw_card(draw, pos[0], pos[1], label, index, appear)
    _draw_arrows(draw, progress)
    _draw_caveat(draw, min(1.0, max(0.0, (progress - 0.62) / 0.28)))
    _draw_safe_zone_glow(draw)
    image = ImageEnhance.Contrast(image).enhance(1.08)
    image = image.filter(ImageFilter.UnsharpMask(radius=0.7, percent=110, threshold=4))
    return image


def _draw_background(draw: ImageDraw.ImageDraw) -> None:
    width, height = REEL_SIZE
    for y in range(height):
        t = y / height
        r = int(17 + 14 * t)
        g = int(24 + 26 * t)
        b = int(29 + 24 * t)
        draw.line((0, y, width, y), fill=(r, g, b, 255))
    draw.ellipse((-240, 120, 600, 820), fill=(224, 142, 64, 54))
    draw.ellipse((430, 260, 1350, 1120), fill=(55, 159, 184, 46))
    draw.ellipse((180, 980, 1150, 1800), fill=(74, 183, 132, 34))
    for y in range(320, 1360, 150):
        draw.line((74, y, 1006, y + 80), fill=(255, 255, 255, 15), width=2)


def _draw_header(draw: ImageDraw.ImageDraw, progress: float) -> None:
    title_font = load_font(size=58, bold=True, warnings=[])
    subtitle_font = load_font(size=27, bold=True, warnings=[])
    alpha = int(255 * min(1.0, progress / 0.18))
    draw.text((86, 190), "Oil-Dollar Chain", font=title_font, fill=(252, 245, 226, alpha))
    draw.text((88, 262), "one pressure, not the whole story", font=subtitle_font, fill=(222, 210, 176, int(alpha * 0.78)))


def _draw_card(draw: ImageDraw.ImageDraw, x: int, y: int, label: str, index: int, appear: float) -> None:
    if appear <= 0:
        return
    ease = 1 - (1 - appear) * (1 - appear)
    y_offset = int((1 - ease) * 42)
    alpha = int(255 * ease)
    width, height = 400, 230
    colors = [
        (230, 151, 72),
        (238, 188, 88),
        (75, 191, 138),
        (78, 177, 210),
    ]
    accent = colors[index]
    box = (x, y + y_offset, x + width, y + y_offset + height)
    draw.rounded_rectangle((box[0] + 12, box[1] + 16, box[2] + 12, box[3] + 16), radius=28, fill=(0, 0, 0, int(85 * ease)))
    draw.rounded_rectangle(box, radius=28, fill=(29, 39, 44, alpha), outline=(*accent, int(210 * ease)), width=4)
    draw.rounded_rectangle((x + 24, y + y_offset + 24, x + 116, y + y_offset + 116), radius=24, fill=(*accent, int(230 * ease)))
    _draw_icon(draw, x + 70, y + y_offset + 70, index, ease)
    font = load_font(size=40 if len(label) <= 12 else 34, bold=True, warnings=[])
    lines = label.split(" ", 1)
    ty = y + y_offset + 62
    for line in lines:
        draw.text((x + 144, ty), line, font=font, fill=(250, 247, 238, alpha))
        ty += 46


def _draw_icon(draw: ImageDraw.ImageDraw, cx: int, cy: int, index: int, ease: float) -> None:
    alpha = int(255 * ease)
    if index == 0:
        draw.ellipse((cx - 26, cy - 14, cx + 26, cy + 44), fill=(22, 28, 30, alpha))
        draw.polygon([(cx, cy - 50), (cx - 30, cy + 0), (cx + 30, cy + 0)], fill=(22, 28, 30, alpha))
        draw.line((cx + 38, cy + 40, cx + 38, cy - 34), fill=(255, 255, 255, int(210 * ease)), width=5)
        draw.polygon([(cx + 38, cy - 48), (cx + 20, cy - 16), (cx + 56, cy - 16)], fill=(255, 255, 255, int(210 * ease)))
    elif index == 1:
        draw.rounded_rectangle((cx - 42, cy - 28, cx + 42, cy + 34), radius=14, fill=(40, 48, 49, alpha))
        draw.line((cx - 28, cy - 42, cx + 28, cy + 48), fill=(255, 255, 255, int(190 * ease)), width=5)
    elif index == 2:
        draw.ellipse((cx - 42, cy - 42, cx + 42, cy + 42), outline=(34, 42, 42, alpha), width=8)
        font = load_font(size=58, bold=True, warnings=[])
        draw.text((cx - 16, cy - 38), "$", font=font, fill=(34, 42, 42, alpha))
    else:
        for i in range(4):
            h = 28 + i * 18
            draw.rounded_rectangle((cx - 42 + i * 25, cy + 44 - h, cx - 22 + i * 25, cy + 44), radius=6, fill=(34, 42, 42, alpha))
        draw.line((cx - 48, cy + 48, cx + 58, cy - 36), fill=(34, 42, 42, alpha), width=6)


def _draw_arrows(draw: ImageDraw.ImageDraw, progress: float) -> None:
    segments = [((505, 545), (573, 545)), ((774, 675), (774, 788)), ((505, 905), (573, 905))]
    for index, (start, end) in enumerate(segments):
        appear = min(1.0, max(0.0, (progress - 0.18 - index * 0.12) / 0.18))
        if appear <= 0:
            continue
        sx, sy = start
        ex, ey = end
        mx = sx + (ex - sx) * appear
        my = sy + (ey - sy) * appear
        draw.line((sx, sy, mx, my), fill=(244, 198, 98, int(230 * appear)), width=8)
        if appear >= 0.9:
            if abs(ex - sx) > abs(ey - sy):
                draw.polygon([(ex, ey), (ex - 24, ey - 18), (ex - 24, ey + 18)], fill=(244, 198, 98, 230))
            else:
                draw.polygon([(ex, ey), (ex - 18, ey - 24), (ex + 18, ey - 24)], fill=(244, 198, 98, 230))


def _draw_caveat(draw: ImageDraw.ImageDraw, appear: float) -> None:
    if appear <= 0:
        return
    ease = 1 - math.cos(appear * math.pi / 2)
    alpha = int(245 * ease)
    box = (112, 1210, 968, 1440)
    draw.rounded_rectangle((box[0] + 12, box[1] + 18, box[2] + 12, box[3] + 18), radius=30, fill=(0, 0, 0, int(92 * ease)))
    draw.rounded_rectangle(box, radius=30, fill=(246, 239, 218, alpha), outline=(247, 189, 92, alpha), width=4)
    font = load_font(size=52, bold=True, warnings=[])
    small = load_font(size=32, bold=True, warnings=[])
    text = "Not Always."
    width, height = text_size(draw, text, font)
    draw.text(((REEL_SIZE[0] - width) // 2, 1262), text, font=font, fill=(32, 36, 35, alpha))
    text2 = "Context matters."
    width2, _ = text_size(draw, text2, small)
    draw.text(((REEL_SIZE[0] - width2) // 2, 1338), text2, font=small, fill=(68, 72, 68, alpha))


def _draw_safe_zone_glow(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle((96, 1520, 984, 1648), radius=42, fill=(255, 255, 255, 18))
