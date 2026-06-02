"""Prompting and emergency non-primitive fallback scenes for mascot Reels."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from app.mascot.mascot_asset_manager import MIKO_NEGATIVE_PROMPT, MIKO_VISUAL_PROMPT
from app.mascot.mascot_profile import MascotProfile
from app.render.native_reel_renderer import REEL_SIZE


MASCOT_ENVIRONMENT_PROMPTS = [
    "Miko in a tiny newsroom desk with oil barrel and dollar symbol props",
    "Miko pointing at a glowing flow diagram",
    "Miko standing near oil barrels and currency exchange board",
    "Miko holding a tiny wallet while oil prices rise",
    "Miko explaining a caution sign: indirect link, not fixed",
]


def build_production_mascot_scene_prompt(profile: MascotProfile, scene: Any, scene_number: int) -> str:
    environment = _environment_for_scene(scene_number)
    base = MIKO_VISUAL_PROMPT if profile.mascot_id == "miko" else profile.image_prompt_base
    negative = MIKO_NEGATIVE_PROMPT if profile.mascot_id == "miko" else profile.negative_prompt
    return " ".join(
        [
            base,
            environment,
            f"action: {getattr(scene, 'mascot_action', '')}",
            f"scene goal: {getattr(scene, 'visual_goal', '')}",
            "premium educational Reel frame, cinematic 9:16 vertical composition, high contrast, detailed props",
            "subject visible, clean caption-safe lower area, no black caption box, no flat vector style",
            "strict image-only rule: no text, no letters, no readable signs, no labels, no logo, no watermark",
            f"avoid: {negative}",
        ]
    )


def build_production_non_mascot_scene_prompt(scene: Any) -> str:
    query = str(getattr(scene, "media_query", "") or getattr(scene, "visual_goal", ""))
    goal = str(getattr(scene, "visual_goal", ""))
    return " ".join(
        [
            goal,
            query,
            "premium cinematic educational Reel background, 9:16 vertical, real-world economy visual language",
            "clear primary subject, layered depth, practical lighting, professional editorial color grade",
            "no empty dark slide, no PowerPoint chart, no primitive vector icons, no flat placeholder design",
            "clean caption-safe area, no text, no letters, no logos, no watermark, no human host",
        ]
    )


def create_neutral_scene_fallback(scene: Any, output_path: Path) -> Path:
    """Create a non-mascot emergency visual if the image provider fails.

    This is intentionally marked as an emergency fallback by metadata callers;
    it avoids primitive mascot drawing and is not considered publish-ready.
    """

    output_path.parent.mkdir(parents=True, exist_ok=True)
    role = str(getattr(scene, "role", "")).lower()
    query = str(getattr(scene, "media_query", "")).lower()
    palette = _palette_for_scene(role, query)
    image = Image.new("RGB", REEL_SIZE, palette[0])
    draw = ImageDraw.Draw(image, "RGBA")
    _draw_grain_gradient(draw, palette)
    _draw_light_sweep(draw, palette)
    _draw_cinematic_subject(draw, query)
    image = ImageEnhance.Contrast(image).enhance(1.14)
    image = ImageEnhance.Color(image).enhance(1.08)
    image = image.filter(ImageFilter.UnsharpMask(radius=0.9, percent=120, threshold=4))
    image.save(output_path, "JPEG", quality=94, optimize=True)
    return output_path


def _environment_for_scene(scene_number: int) -> str:
    if 1 <= scene_number <= len(MASCOT_ENVIRONMENT_PROMPTS):
        return MASCOT_ENVIRONMENT_PROMPTS[scene_number - 1]
    return MASCOT_ENVIRONMENT_PROMPTS[-1]


def _palette_for_scene(role: str, query: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    if "fuel" in query or "refinery" in query or "oil" in query:
        return (22, 31, 34), (210, 134, 66), (76, 118, 126)
    if "currency" in query or "dollar" in query:
        return (25, 34, 42), (62, 176, 134), (224, 184, 82)
    if role == "takeaway":
        return (28, 34, 38), (236, 164, 83), (88, 162, 187)
    return (24, 31, 38), (218, 151, 78), (76, 148, 172)


def _draw_grain_gradient(draw: ImageDraw.ImageDraw, palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> None:
    base, warm, cool = palette
    width, height = REEL_SIZE
    for y in range(height):
        t = y / height
        r = int(base[0] * (1 - t) + cool[0] * t * 0.7 + warm[0] * max(0.0, 0.35 - abs(t - 0.32)))
        g = int(base[1] * (1 - t) + cool[1] * t * 0.7 + warm[1] * max(0.0, 0.28 - abs(t - 0.32)))
        b = int(base[2] * (1 - t) + cool[2] * t * 0.7 + warm[2] * max(0.0, 0.20 - abs(t - 0.32)))
        draw.line((0, y, width, y), fill=(min(255, r), min(255, g), min(255, b), 255))
    for x in range(-200, width + 200, 70):
        alpha = 10 + (x // 70) % 4 * 5
        draw.line((x, 0, x + 500, height), fill=(255, 255, 255, alpha), width=3)


def _draw_light_sweep(draw: ImageDraw.ImageDraw, palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> None:
    _, warm, cool = palette
    draw.ellipse((-250, 120, 760, 950), fill=(*warm, 70))
    draw.ellipse((430, 580, 1340, 1620), fill=(*cool, 54))
    draw.rounded_rectangle((88, 1280, 992, 1580), radius=42, fill=(255, 255, 255, 24))


def _draw_cinematic_subject(draw: ImageDraw.ImageDraw, query: str) -> None:
    cx, cy = 540, 980
    if "tanker" in query or "ship" in query or "port" in query:
        draw.polygon([(130, cy + 40), (950, cy + 40), (820, cy + 245), (210, cy + 245)], fill=(84, 94, 100, 230), outline=(236, 198, 126, 150))
        for x in range(270, 720, 120):
            draw.rounded_rectangle((x, cy - 80, x + 90, cy + 42), radius=8, fill=(190, 202, 198, 230))
        for row in range(5):
            y = cy + 330 + row * 80
            draw.arc((60, y, 1020, y + 130), 8, 172, fill=(120, 180, 198, 96), width=5)
        return
    if "fuel" in query or "station" in query:
        for x in (250, 650):
            draw.rounded_rectangle((x - 90, cy - 210, x + 90, cy + 330), radius=22, fill=(225, 226, 216, 230), outline=(42, 47, 48, 210), width=6)
            draw.rectangle((x - 52, cy - 135, x + 52, cy - 30), fill=(28, 42, 47, 230))
            draw.ellipse((x - 30, cy + 58, x + 30, cy + 118), fill=(232, 152, 72, 230))
        draw.line((430, cy - 60, 600, cy - 130), fill=(34, 36, 36, 220), width=12)
        return
    if "wallet" in query:
        draw.rounded_rectangle((170, cy - 105, 520, cy + 150), radius=34, fill=(226, 174, 78, 235), outline=(52, 47, 41, 210), width=6)
        draw.rounded_rectangle((580, cy - 155, 850, cy + 185), radius=22, fill=(42, 50, 53, 240), outline=(232, 152, 72, 210), width=7)
        draw.line((690, cy - 260, 690, cy - 390), fill=(220, 78, 68, 230), width=12)
        draw.polygon([(690, cy - 420), (650, cy - 350), (730, cy - 350)], fill=(220, 78, 68, 230))
        return
    for x in (180, 330, 620, 800):
        h = 390 + int(80 * math.sin(x))
        draw.rounded_rectangle((x, cy - h, x + 78, cy + 260), radius=10, fill=(76, 88, 90, 225))
        draw.rectangle((x - 20, cy - h - 45, x + 98, cy - h + 10), fill=(126, 132, 124, 210))
    draw.line((120, cy + 60, 940, cy - 190), fill=(212, 176, 112, 150), width=18)
