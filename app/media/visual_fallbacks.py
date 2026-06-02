"""Guaranteed visual fallbacks for every mascot story scene."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance

from app.mascot.mascot_profile import MascotProfile
from app.media.media_item import MediaItem
from app.render.fonts import load_font
from app.render.layout import text_size, wrap_text
from app.render.motion_infographics import create_motion_infographic_still
from app.render.native_reel_renderer import REEL_SIZE


EXTERNAL_PROVIDERS = {"pexels", "unsplash", "wikimedia"}


def missing_media_api_keys() -> list[str]:
    missing: list[str] = []
    if not os.getenv("PEXELS_API_KEY"):
        missing.append("PEXELS_API_KEY")
    if not os.getenv("UNSPLASH_ACCESS_KEY"):
        missing.append("UNSPLASH_ACCESS_KEY")
    return missing


def scene_has_real_visual(item: MediaItem) -> bool:
    path = Path(item.local_path) if item.local_path else None
    return bool(path and path.exists() and path.stat().st_size > 0)


def visual_quality_warnings(item: MediaItem, relevance_threshold: int = 80) -> list[str]:
    warnings: list[str] = []
    if not scene_has_real_visual(item):
        warnings.append("Scene visual file is missing; fallback required.")
    if item.provider in EXTERNAL_PROVIDERS and item.relevance_score < relevance_threshold:
        warnings.append(f"External media relevance below {relevance_threshold}; fallback preferred.")
    if item.width and item.height and item.width < 720 and item.height < 1280:
        warnings.append("External media resolution is too low for a vertical Reel.")
    if item.vertical_usability_score and item.vertical_usability_score < 70:
        warnings.append("External media has weak vertical crop feasibility.")
    return warnings


def create_scene_fallback(scene: Any, output_path: Path, mascot: MascotProfile | None = None) -> MediaItem:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    visual_type = str(getattr(scene, "visual_type", "object_scene_ai"))
    if visual_type == "chart_motion":
        create_motion_infographic_still(scene, output_path)
        provider = "chart"
        media_type = "generated_chart_spec"
        attribution = "Generated in-app motion infographic"
        relevance = 96
        clarity = 94
    elif visual_type in {"mascot_ai", "mixed"}:
        _draw_mascot_scene(scene, output_path, mascot)
        provider = "ai_fallback"
        media_type = "generated_ai_prompt"
        attribution = "Generated local mascot fallback visual"
        relevance = 90
        clarity = 88
    elif visual_type == "object_scene_ai":
        _draw_object_scene(scene, output_path)
        provider = "ai_fallback"
        media_type = "generated_ai_prompt"
        attribution = "Generated local object-scene fallback visual"
        relevance = 88
        clarity = 86
    else:
        _draw_broll_fallback(scene, output_path)
        provider = "fallback"
        media_type = "generated_ai_prompt"
        attribution = "Generated fallback because suitable external media was unavailable"
        relevance = 82
        clarity = 80
    return MediaItem(
        provider=provider,
        media_type=media_type,
        title=str(getattr(scene, "visual_goal", "")),
        local_path=str(output_path),
        width=REEL_SIZE[0],
        height=REEL_SIZE[1],
        license="Generated fallback visual",
        attribution=attribution,
        relevance_score=relevance,
        vertical_usability_score=100,
        license_safety_score=90,
        visual_clarity_score=clarity,
        source_trust_score=70,
    )


def write_media_fallback_report(output_dir: Path, report: dict[str, object]) -> None:
    output_dir.joinpath("media_fallback_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _draw_background(draw: ImageDraw.ImageDraw, base: tuple[int, int, int]) -> None:
    for y in range(REEL_SIZE[1]):
        amount = y / REEL_SIZE[1]
        draw.line((0, y, REEL_SIZE[0], y), fill=(base[0] + int(18 * amount), base[1] + int(16 * amount), base[2] + int(12 * amount)))


def _draw_mascot_scene(scene: Any, output_path: Path, mascot: MascotProfile | None) -> None:
    image = Image.new("RGB", REEL_SIZE, (238, 226, 205))
    draw = ImageDraw.Draw(image, "RGBA")
    _draw_background(draw, (229, 214, 190))
    _draw_soft_shapes(draw)
    _draw_miko(draw, 540, 860, scale=1.0, pose=str(getattr(scene, "mascot_action", "")))
    _draw_prop_cluster(draw, str(getattr(scene, "visual_goal", "")), 540, 1240)
    _draw_safe_caption_hint(draw, str(getattr(scene, "on_screen_caption", "")))
    image = ImageEnhance.Contrast(image).enhance(1.04)
    image.save(output_path, "JPEG", quality=94, optimize=True)


def _draw_object_scene(scene: Any, output_path: Path) -> None:
    image = Image.new("RGB", REEL_SIZE, (231, 221, 204))
    draw = ImageDraw.Draw(image, "RGBA")
    _draw_background(draw, (226, 215, 196))
    _draw_wallet_large(draw, 330, 850)
    _draw_barrel(draw, 690, 835)
    draw.line((690, 640, 690, 520), fill=(205, 69, 59, 255), width=10)
    draw.polygon([(690, 500), (660, 550), (720, 550)], fill=(205, 69, 59, 255))
    _draw_miko(draw, 820, 1240, scale=0.55, pose="concerned")
    image.save(output_path, "JPEG", quality=94, optimize=True)


def _draw_broll_fallback(scene: Any, output_path: Path) -> None:
    image = Image.new("RGB", REEL_SIZE, (28, 35, 38))
    draw = ImageDraw.Draw(image, "RGBA")
    _draw_background(draw, (28, 35, 38))
    query = str(getattr(scene, "media_query", "")).lower()
    if "tanker" in query or "shipping" in query:
        _draw_tanker_scene(draw)
    elif "fuel" in query or "station" in query:
        _draw_fuel_scene(draw)
    else:
        _draw_refinery_scene(draw)
    _draw_safe_caption_hint(draw, str(getattr(scene, "on_screen_caption", "")))
    image.save(output_path, "JPEG", quality=94, optimize=True)


def _draw_safe_caption_hint(draw: ImageDraw.ImageDraw, caption: str) -> None:
    if not caption:
        return
    font = load_font(size=34, bold=True, warnings=[])
    lines = wrap_text(draw, caption, font, REEL_SIZE[0] - 160)[:1]
    if lines:
        width, height = text_size(draw, lines[0], font)
        x = (REEL_SIZE[0] - width) // 2
        y = 230
        draw.rounded_rectangle((x - 22, y - 14, x + width + 22, y + height + 14), radius=8, fill=(255, 245, 226, 205))
        draw.text((x, y), lines[0], font=font, fill=(45, 42, 38, 235))


def _draw_soft_shapes(draw: ImageDraw.ImageDraw) -> None:
    draw.ellipse((100, 220, 430, 550), fill=(255, 238, 206, 170))
    draw.ellipse((690, 300, 1010, 620), fill=(234, 144, 74, 80))
    draw.rounded_rectangle((120, 1320, 960, 1510), radius=40, fill=(255, 241, 216, 170))


def _draw_miko(draw: ImageDraw.ImageDraw, cx: int, cy: int, scale: float, pose: str) -> None:
    def s(value: int) -> int:
        return int(value * scale)

    draw.rounded_rectangle((cx - s(175), cy - s(115), cx + s(175), cy + s(245)), radius=s(96), fill=(239, 133, 54, 255), outline=(62, 58, 54, 220), width=max(3, s(8)))
    draw.ellipse((cx - s(112), cy - s(55), cx + s(112), cy + s(150)), fill=(255, 232, 194, 255))
    draw.polygon([(cx - s(145), cy - s(105)), (cx - s(72), cy - s(250)), (cx - s(18), cy - s(88))], fill=(239, 133, 54, 255), outline=(62, 58, 54, 220))
    draw.polygon([(cx + s(145), cy - s(105)), (cx + s(72), cy - s(250)), (cx + s(18), cy - s(88))], fill=(239, 133, 54, 255), outline=(62, 58, 54, 220))
    eye_y = cy + s(22)
    draw.ellipse((cx - s(82), eye_y - s(36), cx - s(20), eye_y + s(36)), fill=(28, 30, 32, 255))
    draw.ellipse((cx + s(20), eye_y - s(36), cx + s(82), eye_y + s(36)), fill=(28, 30, 32, 255))
    draw.ellipse((cx - s(61), eye_y - s(18), cx - s(42), eye_y + s(1)), fill=(255, 255, 255, 230))
    draw.ellipse((cx + s(41), eye_y - s(18), cx + s(60), eye_y + s(1)), fill=(255, 255, 255, 230))
    draw.ellipse((cx - s(28), cy + s(96), cx + s(28), cy + s(152)), fill=(255, 211, 92, 255), outline=(62, 58, 54, 180), width=max(2, s(4)))
    right_y = cy - s(20) if "point" in pose or "raising" in pose else cy + s(128)
    draw.line((cx - s(190), cy + s(48), cx - s(300), cy + s(128)), fill=(48, 48, 48, 255), width=max(6, s(18)))
    draw.line((cx + s(190), cy + s(48), cx + s(300), right_y), fill=(48, 48, 48, 255), width=max(6, s(18)))


def _draw_prop_cluster(draw: ImageDraw.ImageDraw, goal: str, cx: int, cy: int) -> None:
    lower = goal.lower()
    if "oil" in lower:
        draw.ellipse((cx - 250, cy - 60, cx - 120, cy + 120), fill=(34, 39, 42, 255), outline=(232, 154, 70, 255), width=5)
    if "dollar" in lower or "coin" in lower:
        draw.ellipse((cx + 120, cy - 60, cx + 260, cy + 80), fill=(224, 180, 74, 255), outline=(80, 62, 38, 255), width=5)
        draw.arc((cx + 158, cy - 34, cx + 222, cy + 54), 80, 280, fill=(80, 62, 38, 255), width=5)
    if "caution" in lower or "trap" in lower:
        draw.polygon([(cx, cy - 120), (cx - 130, cy + 80), (cx + 130, cy + 80)], fill=(250, 188, 82, 255), outline=(55, 47, 40, 255))


def _draw_wallet_large(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    draw.rounded_rectangle((cx - 190, cy - 110, cx + 190, cy + 130), radius=26, fill=(237, 186, 91, 255), outline=(55, 49, 42, 255), width=6)
    draw.rounded_rectangle((cx + 40, cy - 30, cx + 180, cy + 70), radius=20, fill=(255, 226, 150, 255), outline=(55, 49, 42, 255), width=5)
    draw.line((cx - 150, cy - 145, cx + 150, cy + 165), fill=(200, 68, 60, 235), width=10)
    draw.line((cx + 150, cy - 145, cx - 150, cy + 165), fill=(200, 68, 60, 235), width=10)


def _draw_barrel(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    draw.rectangle((cx - 110, cy - 150, cx + 110, cy + 150), fill=(45, 52, 56, 255), outline=(240, 156, 74, 255), width=6)
    draw.ellipse((cx - 110, cy - 180, cx + 110, cy - 110), fill=(62, 68, 70, 255), outline=(240, 156, 74, 255), width=6)
    draw.ellipse((cx - 110, cy + 110, cx + 110, cy + 180), fill=(35, 40, 44, 255), outline=(240, 156, 74, 255), width=6)


def _draw_refinery_scene(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((0, 1180, 1080, 1920), fill=(43, 45, 43, 255))
    for x in (160, 310, 640, 820):
        draw.rectangle((x, 650, x + 75, 1300), fill=(78, 87, 88, 255))
        draw.rectangle((x - 20, 620, x + 95, 670), fill=(110, 117, 112, 255))
    draw.line((130, 1040, 930, 780), fill=(165, 148, 111, 255), width=18)
    draw.line((170, 900, 960, 1160), fill=(95, 112, 118, 255), width=12)
    draw.ellipse((130, 470, 380, 620), fill=(214, 154, 92, 110))


def _draw_tanker_scene(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((0, 1120, 1080, 1920), fill=(31, 68, 82, 255))
    draw.polygon([(100, 960), (950, 960), (830, 1190), (170, 1190)], fill=(80, 86, 88, 255), outline=(220, 180, 95, 190))
    draw.rectangle((260, 830, 520, 960), fill=(205, 211, 207, 255))
    draw.rectangle((540, 790, 690, 960), fill=(180, 188, 187, 255))
    for y in range(1250, 1600, 78):
        draw.arc((60, y, 1020, y + 120), 8, 172, fill=(92, 132, 148, 180), width=6)


def _draw_fuel_scene(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((0, 1170, 1080, 1920), fill=(56, 58, 55, 255))
    draw.rectangle((170, 610, 460, 1250), fill=(210, 212, 205, 255), outline=(54, 54, 50, 255), width=7)
    draw.rectangle((220, 700, 410, 870), fill=(36, 50, 55, 255))
    draw.rectangle((625, 590, 820, 1250), fill=(210, 212, 205, 255), outline=(54, 54, 50, 255), width=7)
    draw.line((460, 780, 625, 720), fill=(42, 42, 42, 255), width=14)
    draw.ellipse((680, 760, 760, 840), fill=(238, 146, 68, 255))

