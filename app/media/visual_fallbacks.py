"""Production visual fallback policy for explainer scenes."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance

from app.media.media_item import MediaItem
from app.render.fonts import load_font
from app.render.motion_infographics import create_motion_infographic_still
from app.render.native_reel_renderer import REEL_SIZE


EXTERNAL_PROVIDERS = {"pexels"}
PRODUCTION_VISUAL_MINIMUMS = True
AI_GENERATED_PROVIDER = "ai_generated"
PREMIUM_INFOGRAPHIC_PROVIDER = "premium_infographic"


def missing_media_api_keys() -> list[str]:
    missing: list[str] = []
    if not os.getenv("PEXELS_API_KEY"):
        missing.append("PEXELS_API_KEY")
    return missing


def scene_has_real_visual(item: MediaItem) -> bool:
    path = Path(item.local_path) if item.local_path else None
    return bool(path and path.exists() and path.stat().st_size > 0)


def scene_needs_ai_generation(item: MediaItem) -> bool:
    return item.provider == AI_GENERATED_PROVIDER and item.media_type == "generated_ai_prompt"


def visual_quality_warnings(item: MediaItem, relevance_threshold: int = 80) -> list[str]:
    warnings: list[str] = []
    if scene_needs_ai_generation(item):
        return warnings
    if not scene_has_real_visual(item):
        warnings.append("Scene visual file is missing; fallback required.")
    if item.provider in EXTERNAL_PROVIDERS and item.relevance_score < relevance_threshold:
        warnings.append(f"External media relevance below {relevance_threshold}; fallback preferred.")
    if item.width and item.height and item.width < 1080 and item.height < 1280:
        warnings.append("External media resolution is too low for a vertical Reel.")
    if item.vertical_usability_score and item.vertical_usability_score < 75:
        warnings.append("External media has weak vertical crop feasibility.")
    if item.visual_clarity_score and item.visual_clarity_score < 75:
        warnings.append("External media visual clarity is below production minimum.")
    return warnings


def create_scene_fallback(
    scene: Any,
    output_path: Path,
    production_visual_minimums: bool = PRODUCTION_VISUAL_MINIMUMS,
) -> MediaItem:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    visual_type = str(getattr(scene, "visual_type", "object_scene_ai"))
    if visual_type == "chart_motion":
        create_motion_infographic_still(scene, output_path)
        return MediaItem(
            provider=PREMIUM_INFOGRAPHIC_PROVIDER,
            media_type="generated_chart_spec",
            title=str(getattr(scene, "visual_goal", "Premium motion infographic")),
            local_path=str(output_path),
            width=REEL_SIZE[0],
            height=REEL_SIZE[1],
            license="Generated production infographic",
            attribution="Generated in-app premium motion infographic",
            relevance_score=96,
            vertical_usability_score=100,
            license_safety_score=94,
            visual_clarity_score=92,
            source_trust_score=82,
        )
    if production_visual_minimums:
        return MediaItem(
            provider=AI_GENERATED_PROVIDER,
            media_type="generated_ai_prompt",
            title=str(getattr(scene, "visual_goal", "")),
            local_path=str(output_path),
            width=REEL_SIZE[0],
            height=REEL_SIZE[1],
            license="AI-generated image",
            attribution="Generated with configured AI image provider",
            relevance_score=86,
            vertical_usability_score=100,
            license_safety_score=84,
            visual_clarity_score=84,
            source_trust_score=72,
        )
    _draw_debug_visual(scene, output_path)
    return MediaItem(
        provider="primitive_debug",
        media_type="debug_primitive_visual",
        title=str(getattr(scene, "visual_goal", "")),
        local_path=str(output_path),
        width=REEL_SIZE[0],
        height=REEL_SIZE[1],
        license="Debug-only local primitive visual",
        attribution="Debug-only primitive fallback; forbidden in production final render",
        relevance_score=45,
        vertical_usability_score=80,
        license_safety_score=50,
        visual_clarity_score=35,
        source_trust_score=25,
    )


def write_media_fallback_report(output_dir: Path, report: dict[str, object]) -> None:
    output_dir.joinpath("media_fallback_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _draw_debug_visual(scene: Any, output_path: Path) -> None:
    image = Image.new("RGB", REEL_SIZE, (34, 36, 38))
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(REEL_SIZE[1]):
        draw.line((0, y, REEL_SIZE[0], y), fill=(34 + y // 120, 36 + y // 100, 38 + y // 120))
    draw.rectangle((150, 520, 930, 1250), outline=(220, 150, 80, 180), width=6)
    font = load_font(size=42, bold=True, warnings=[])
    draw.text((180, 600), "DEBUG VISUAL", font=font, fill=(242, 220, 170, 210))
    draw.text((180, 680), str(getattr(scene, "visual_type", ""))[:24], font=font, fill=(242, 242, 235, 190))
    image = ImageEnhance.Contrast(image).enhance(1.05)
    image.save(output_path, "JPEG", quality=90, optimize=True)
