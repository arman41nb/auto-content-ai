"""Heuristic visual aesthetic QA for production Reel frames."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageStat

from app.content.mascot_story_schemas import MascotStoryPlan
from app.render.native_reel_renderer import REEL_SIZE


HIGH = "high"
MEDIUM = "medium"
LOW = "low"


def analyze_visual_aesthetic_quality(output_dir: Path, plan: MascotStoryPlan, metadata: dict[str, Any]) -> dict[str, Any]:
    media_plan = _read_json(output_dir / "media_plan.json")
    render = metadata.get("mascot_story_render", {}) if isinstance(metadata.get("mascot_story_render", {}), dict) else {}
    image_generation_failed = _metadata_has_ai_generation_failure(metadata)
    frames = _frame_paths(output_dir, len(plan.scenes))
    scene_metrics = [_image_metrics(path) for path in frames]
    media_scenes = media_plan.get("scenes", []) if isinstance(media_plan.get("scenes", []), list) else []

    primitive_scene_numbers = _primitive_scene_numbers(media_scenes, scene_metrics)
    placeholder_scene_numbers = _placeholder_scene_numbers(media_scenes, scene_metrics)
    powerpoint_chart_numbers = _powerpoint_chart_numbers(media_scenes)
    empty_scene_numbers = [index + 1 for index, item in enumerate(scene_metrics) if item.get("empty_scene_risk")]
    dark_empty_area_ratio = _average([float(item.get("dark_empty_area_ratio", 0.0) or 0.0) for item in scene_metrics])
    subject_visibility_score = round(_average([float(item.get("subject_visibility_score", 0.0) or 0.0) for item in scene_metrics]))
    caption_box_ratio = float(render.get("caption_box_dominance_ratio", 0.0) or 0.0)
    prompt_text_risk = HIGH if int(render.get("prompt_text_visible_count", 0) or 0) > 0 else LOW

    primitive_mascot_risk = HIGH if any(_scene_is_mascot(plan, number) for number in primitive_scene_numbers) else LOW
    placeholder_visual_risk = HIGH if placeholder_scene_numbers or image_generation_failed else LOW
    powerpoint_chart_risk = HIGH if powerpoint_chart_numbers else LOW
    empty_scene_ratio = len(empty_scene_numbers) / max(1, len(plan.scenes))
    flat_shape_scene_risk = HIGH if primitive_scene_numbers else LOW
    cropped_text_risk = HIGH if int(render.get("text_crop_count", 0) or 0) > 0 else LOW
    broll_or_ai_scene_quality_score = _broll_or_ai_score(media_scenes, scene_metrics)

    penalty = 0
    penalty += 28 if primitive_mascot_risk == HIGH else 0
    penalty += 24 if placeholder_visual_risk == HIGH else 0
    penalty += 22 if powerpoint_chart_risk == HIGH else 0
    penalty += round(empty_scene_ratio * 35)
    penalty += max(0, 74 - subject_visibility_score) // 2
    penalty += 10 if caption_box_ratio > 0.18 else 0
    visual_asset_quality_score = max(0, min(100, broll_or_ai_scene_quality_score - penalty))

    report = {
        "production_visual_minimums": True,
        "flat_shape_scene_risk": flat_shape_scene_risk,
        "primitive_mascot_risk": primitive_mascot_risk,
        "empty_scene_ratio": round(empty_scene_ratio, 3),
        "dark_empty_area_ratio": round(dark_empty_area_ratio, 3),
        "cropped_text_risk": cropped_text_risk,
        "prompt_text_risk": prompt_text_risk,
        "placeholder_visual_risk": placeholder_visual_risk,
        "powerpoint_chart_risk": powerpoint_chart_risk,
        "caption_box_dominance_ratio": round(caption_box_ratio, 3),
        "subject_visibility_score": subject_visibility_score,
        "visual_asset_quality_score": visual_asset_quality_score,
        "broll_or_ai_scene_quality_score": broll_or_ai_scene_quality_score,
        "primitive_scene_numbers": primitive_scene_numbers,
        "placeholder_scene_numbers": placeholder_scene_numbers,
        "powerpoint_chart_scene_numbers": powerpoint_chart_numbers,
        "empty_scene_numbers": empty_scene_numbers,
        "scene_metrics": scene_metrics,
        "blocking_issues": _blocking_issues(
            primitive_mascot_risk,
            placeholder_visual_risk,
            powerpoint_chart_risk,
            empty_scene_ratio,
            visual_asset_quality_score,
            broll_or_ai_scene_quality_score,
        ),
    }
    write_visual_aesthetic_report(output_dir, report)
    return report


def write_visual_aesthetic_report(output_dir: Path, report: dict[str, Any]) -> None:
    (output_dir / "visual_aesthetic_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Visual Aesthetic Report", ""]
    for key in (
        "flat_shape_scene_risk",
        "primitive_mascot_risk",
        "empty_scene_ratio",
        "dark_empty_area_ratio",
        "cropped_text_risk",
        "prompt_text_risk",
        "placeholder_visual_risk",
        "powerpoint_chart_risk",
        "caption_box_dominance_ratio",
        "subject_visibility_score",
        "visual_asset_quality_score",
        "broll_or_ai_scene_quality_score",
    ):
        lines.append(f"- {key}: {report.get(key)}")
    lines.extend(["", "## Blocking Issues"])
    blockers = report.get("blocking_issues", [])
    lines.extend(f"- {item}" for item in blockers) if blockers else lines.append("- None")
    (output_dir / "visual_aesthetic_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _frame_paths(output_dir: Path, count: int) -> list[Path]:
    frames_dir = output_dir / "final_reel" / "frames"
    raw_dir = output_dir / "raw_images"
    return [
        frames_dir / f"frame_{index:02d}.jpg"
        if (frames_dir / f"frame_{index:02d}.jpg").exists()
        else raw_dir / f"slide_{index:02d}.jpg"
        for index in range(1, count + 1)
    ]


def _image_metrics(path: Path) -> dict[str, object]:
    if not path.exists():
        return {
            "path": str(path),
            "exists": False,
            "empty_scene_risk": True,
            "flat_shape_risk": True,
            "dark_empty_area_ratio": 1.0,
            "subject_visibility_score": 0,
        }
    try:
        with Image.open(path) as source:
            image = source.convert("RGB")
            size_ok = image.size == REEL_SIZE
            small = image.resize((90, 160), Image.Resampling.BILINEAR)
            stat = ImageStat.Stat(small)
            brightness = sum(stat.mean) / 3
            variance = sum(stat.var) / 3
            colors = small.convert("P", palette=Image.Palette.ADAPTIVE, colors=64).getcolors(maxcolors=90 * 160)
            dominant_ratio = max((count for count, _ in colors), default=0) / max(1, small.width * small.height)
            dark_ratio = _dark_ratio(small)
            edge = small.convert("L").filter(ImageFilter.FIND_EDGES)
            edge_mean = ImageStat.Stat(edge).mean[0] / 255
            flat_shape_risk = dominant_ratio > 0.34 or (len(colors or []) < 28 and edge_mean < 0.035)
            empty_scene_risk = brightness < 12 or variance < 12 or (dark_ratio > 0.74 and edge_mean < 0.028)
            subject_score = round(max(0, min(100, 38 + edge_mean * 780 + (1 - dominant_ratio) * 42 - dark_ratio * 18)))
            return {
                "path": str(path),
                "exists": True,
                "size_ok": size_ok,
                "brightness": round(brightness, 2),
                "variance": round(variance, 2),
                "unique_palette_colors": len(colors or []),
                "dominant_color_ratio": round(dominant_ratio, 3),
                "edge_density": round(edge_mean, 4),
                "dark_empty_area_ratio": round(dark_ratio, 3),
                "flat_shape_risk": flat_shape_risk,
                "empty_scene_risk": empty_scene_risk,
                "subject_visibility_score": subject_score,
            }
    except Exception as exc:
        return {
            "path": str(path),
            "exists": False,
            "error": str(exc),
            "empty_scene_risk": True,
            "flat_shape_risk": True,
            "dark_empty_area_ratio": 1.0,
            "subject_visibility_score": 0,
        }


def _dark_ratio(image: Image.Image) -> float:
    lum = image.convert("L")
    histogram = lum.histogram()
    return sum(histogram[:28]) / max(1, lum.width * lum.height)


def _primitive_scene_numbers(media_scenes: list[Any], scene_metrics: list[dict[str, object]]) -> list[int]:
    numbers: list[int] = []
    for index, scene in enumerate(media_scenes, start=1):
        selected = scene.get("selected", {}) if isinstance(scene, dict) else {}
        provider = str(selected.get("provider", "") if isinstance(selected, dict) else "")
        media_type = str(selected.get("media_type", "") if isinstance(selected, dict) else "")
        metric = scene_metrics[index - 1] if index - 1 < len(scene_metrics) else {}
        if provider in {"fallback", "ai_fallback", "primitive_debug"} or media_type == "debug_primitive_visual":
            numbers.append(index)
        elif bool(metric.get("flat_shape_risk")) and provider not in {"ai_generated", "pexels", "unsplash", "wikimedia", "premium_infographic"}:
            numbers.append(index)
    return numbers


def _placeholder_scene_numbers(media_scenes: list[Any], scene_metrics: list[dict[str, object]]) -> list[int]:
    numbers: list[int] = []
    for index, scene in enumerate(media_scenes, start=1):
        selected = scene.get("selected", {}) if isinstance(scene, dict) else {}
        provider = str(selected.get("provider", "") if isinstance(selected, dict) else "")
        title = str(selected.get("title", "") if isinstance(selected, dict) else "").lower()
        metric = scene_metrics[index - 1] if index - 1 < len(scene_metrics) else {}
        if provider in {"fallback", "ai_fallback", "primitive_debug", "ai_generation_failed_fallback"}:
            numbers.append(index)
        elif "placeholder" in title or "fallback" in title:
            numbers.append(index)
        elif bool(metric.get("empty_scene_risk")):
            numbers.append(index)
    return numbers


def _powerpoint_chart_numbers(media_scenes: list[Any]) -> list[int]:
    numbers: list[int] = []
    for index, scene in enumerate(media_scenes, start=1):
        if not isinstance(scene, dict):
            continue
        selected = scene.get("selected", {}) if isinstance(scene.get("selected", {}), dict) else {}
        requested = str(scene.get("requested_visual_type", ""))
        provider = str(selected.get("provider", ""))
        if requested == "chart_motion" and provider != "premium_infographic":
            numbers.append(index)
    return numbers


def _broll_or_ai_score(media_scenes: list[Any], scene_metrics: list[dict[str, object]]) -> int:
    scores: list[float] = []
    for index, scene in enumerate(media_scenes, start=1):
        selected = scene.get("selected", {}) if isinstance(scene, dict) else {}
        if not isinstance(selected, dict):
            continue
        provider = str(selected.get("provider", ""))
        clarity = float(selected.get("visual_clarity_score", 78) or 78)
        metric = scene_metrics[index - 1] if index - 1 < len(scene_metrics) else {}
        subject = float(metric.get("subject_visibility_score", 70) or 70)
        if provider in {"fallback", "ai_fallback", "primitive_debug", "ai_generation_failed_fallback"}:
            clarity = min(clarity, 48)
        if provider == "premium_infographic":
            clarity = max(clarity, 88)
        scores.append((clarity * 0.62) + (subject * 0.38))
    return round(_average(scores)) if scores else 50


def _scene_is_mascot(plan: MascotStoryPlan, number: int) -> bool:
    if number < 1 or number > len(plan.scenes):
        return False
    return plan.scenes[number - 1].visual_type in {"mascot_ai", "mixed"}


def _blocking_issues(
    primitive_mascot_risk: str,
    placeholder_visual_risk: str,
    powerpoint_chart_risk: str,
    empty_scene_ratio: float,
    visual_asset_quality_score: int,
    broll_or_ai_scene_quality_score: int,
) -> list[str]:
    issues: list[str] = []
    if primitive_mascot_risk == HIGH:
        issues.append("primitive_mascot_risk is high.")
    if placeholder_visual_risk == HIGH:
        issues.append("placeholder_visual_risk is high.")
    if powerpoint_chart_risk == HIGH:
        issues.append("powerpoint_chart_risk is high.")
    if empty_scene_ratio > 0:
        issues.append(f"empty_scene_ratio is above 0: {empty_scene_ratio:.3f}.")
    if visual_asset_quality_score < 75:
        issues.append(f"visual_asset_quality_score < 75: {visual_asset_quality_score}.")
    if broll_or_ai_scene_quality_score < 75:
        issues.append(f"broll_or_ai_scene_quality_score < 75: {broll_or_ai_scene_quality_score}.")
    return issues


def _metadata_has_ai_generation_failure(metadata: dict[str, Any]) -> bool:
    warnings = metadata.get("image_quality_warnings", {})
    if isinstance(warnings, dict):
        for value in warnings.values():
            if isinstance(value, list) and any("ai image provider failed" in str(item).lower() for item in value):
                return True
    blocking = metadata.get("publish_blocking_image_warnings", [])
    return isinstance(blocking, list) and any("ai image provider failed" in str(item).lower() for item in blocking)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
