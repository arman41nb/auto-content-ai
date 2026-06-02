"""Reel-native motion infographic backgrounds."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.render.fonts import load_font
from app.render.layout import text_size, wrap_text
from app.render.native_reel_renderer import REEL_SIZE


def create_motion_infographic_still(scene, output_path: Path, progress: float = 1.0) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = oil_dollar_infographic(scene, progress)
    image.save(output_path, "JPEG", quality=95, optimize=True)
    return output_path


def oil_dollar_infographic(scene, progress: float = 1.0) -> Image.Image:
    progress = max(0.0, min(1.0, progress))
    image = Image.new("RGB", REEL_SIZE, (22, 28, 30))
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(REEL_SIZE[1]):
        amount = y / REEL_SIZE[1]
        draw.line((0, y, REEL_SIZE[0], y), fill=(22 + int(18 * amount), 28 + int(16 * amount), 30 + int(8 * amount)))
    _draw_miko_small(draw, 210, 1330)
    _draw_oil_drop(draw, 250, 450, 110, float(min(1.0, progress * 2.2)))
    _draw_arrow(draw, (360, 500), (540, 500), float(min(1.0, max(0, progress - 0.15) * 2.0)))
    _draw_wallet(draw, 660, 410, float(min(1.0, max(0, progress - 0.28) * 2.0)))
    _draw_arrow(draw, (760, 640), (760, 850), float(min(1.0, max(0, progress - 0.42) * 2.0)))
    _draw_meter(draw, 580, 910, float(min(1.0, max(0, progress - 0.50) * 2.2)))
    _draw_caution(draw, 620, 1260, float(min(1.0, max(0, progress - 0.70) * 3.0)))

    font = load_font(size=50, bold=True, warnings=[])
    small_font = load_font(size=27, bold=True, warnings=[])
    draw.text((86, 210), "THE LINK", font=font, fill=(248, 242, 224, 255))
    draw.text((86, 284), "oil price up, dollar pressure can rise", font=small_font, fill=(234, 218, 178, 220))
    return image


def _draw_oil_drop(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, alpha_scale: float) -> None:
    alpha = int(255 * alpha_scale)
    draw.ellipse((cx - size, cy - 35, cx + size, cy + size * 2), fill=(32, 38, 43, alpha), outline=(235, 166, 78, alpha), width=5)
    draw.polygon([(cx, cy - size - 48), (cx - size + 18, cy + 10), (cx + size - 18, cy + 10)], fill=(32, 38, 43, alpha))
    draw.ellipse((cx - 35, cy + 20, cx - 5, cy + 50), fill=(255, 255, 255, int(120 * alpha_scale)))
    _badge(draw, cx - 90, cy + 240, "OIL UP", alpha_scale)


def _draw_wallet(draw: ImageDraw.ImageDraw, cx: int, cy: int, alpha_scale: float) -> None:
    alpha = int(255 * alpha_scale)
    draw.rounded_rectangle((cx - 150, cy - 80, cx + 150, cy + 105), radius=24, fill=(242, 191, 95, alpha), outline=(56, 52, 48, alpha), width=5)
    draw.rounded_rectangle((cx + 42, cy - 24, cx + 142, cy + 56), radius=18, fill=(255, 226, 147, alpha), outline=(56, 52, 48, alpha), width=4)
    draw.ellipse((cx + 82, cy + 6, cx + 112, cy + 36), fill=(56, 52, 48, alpha))
    draw.line((cx - 120, cy - 106, cx + 120, cy + 128), fill=(204, 72, 72, int(210 * alpha_scale)), width=7)
    draw.line((cx + 120, cy - 106, cx - 120, cy + 128), fill=(204, 72, 72, int(210 * alpha_scale)), width=7)
    _badge(draw, cx - 140, cy + 150, "WALLET SQUEEZED", alpha_scale)


def _draw_meter(draw: ImageDraw.ImageDraw, cx: int, cy: int, alpha_scale: float) -> None:
    alpha = int(255 * alpha_scale)
    draw.rounded_rectangle((cx - 150, cy - 52, cx + 150, cy + 52), radius=20, fill=(35, 46, 52, alpha), outline=(236, 209, 141, alpha), width=4)
    fill_w = int(258 * alpha_scale)
    draw.rounded_rectangle((cx - 129, cy - 30, cx - 129 + fill_w, cy + 30), radius=14, fill=(74, 183, 132, alpha))
    _badge(draw, cx - 112, cy + 118, "DOLLAR DEMAND", alpha_scale)


def _draw_caution(draw: ImageDraw.ImageDraw, cx: int, cy: int, alpha_scale: float) -> None:
    alpha = int(255 * alpha_scale)
    draw.polygon([(cx, cy - 110), (cx - 120, cy + 95), (cx + 120, cy + 95)], fill=(249, 189, 82, alpha), outline=(40, 38, 35, alpha), width=5)
    font = load_font(size=88, bold=True, warnings=[])
    draw.text((cx - 14, cy - 44), "!", font=font, fill=(40, 38, 35, alpha))
    _badge(draw, cx - 170, cy + 145, "NOT ALWAYS", alpha_scale)


def _draw_arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], alpha_scale: float) -> None:
    alpha = int(230 * alpha_scale)
    if alpha <= 0:
        return
    sx, sy = start
    ex, ey = end
    draw.line((sx, sy, ex, ey), fill=(239, 180, 82, alpha), width=9)
    if abs(ex - sx) > abs(ey - sy):
        draw.polygon([(ex, ey), (ex - 32, ey - 22), (ex - 32, ey + 22)], fill=(239, 180, 82, alpha))
    else:
        draw.polygon([(ex, ey), (ex - 22, ey - 32), (ex + 22, ey - 32)], fill=(239, 180, 82, alpha))


def _badge(draw: ImageDraw.ImageDraw, x: int, y: int, text: str, alpha_scale: float) -> None:
    font = load_font(size=28, bold=True, warnings=[])
    width, height = text_size(draw, text, font)
    alpha = int(235 * alpha_scale)
    draw.rounded_rectangle((x, y, x + width + 32, y + height + 20), radius=8, fill=(248, 242, 224, alpha), outline=(42, 38, 34, alpha), width=2)
    draw.text((x + 16, y + 10), text, font=font, fill=(42, 38, 34, alpha))


def _draw_miko_small(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    draw.rounded_rectangle((cx - 115, cy - 82, cx + 115, cy + 150), radius=62, fill=(238, 132, 55, 255), outline=(46, 44, 42, 230), width=5)
    draw.ellipse((cx - 72, cy - 38, cx + 72, cy + 92), fill=(255, 228, 188, 255))
    draw.polygon([(cx - 88, cy - 66), (cx - 42, cy - 164), (cx - 12, cy - 58)], fill=(238, 132, 55, 255), outline=(46, 44, 42, 230))
    draw.polygon([(cx + 88, cy - 66), (cx + 42, cy - 164), (cx + 12, cy - 58)], fill=(238, 132, 55, 255), outline=(46, 44, 42, 230))
    draw.ellipse((cx - 52, cy - 6, cx - 14, cy + 40), fill=(25, 27, 29, 255))
    draw.ellipse((cx + 14, cy - 6, cx + 52, cy + 40), fill=(25, 27, 29, 255))
    draw.ellipse((cx - 18, cy + 70, cx + 18, cy + 106), fill=(255, 211, 92, 255))

