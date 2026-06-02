"""Quality gate and reports for mascot story explainer Reels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from app.content.mascot_story_schemas import MascotStoryPlan
from app.quality.visual_aesthetic_quality import analyze_visual_aesthetic_quality
from app.render.native_reel_renderer import REEL_SIZE


def run_mascot_story_quality_gate(output_dir: Path, plan: MascotStoryPlan, metadata: dict[str, Any], voiceover_requested: bool) -> dict[str, Any]:
    media_plan = _read_json(output_dir / "media_plan.json")
    attribution = _read_json(output_dir / "media_attribution.json")
    fallback = _read_json(output_dir / "media_fallback_report.json")
    media_quality = _read_json(output_dir / "media_quality_report.json")
    voiceover = metadata.get("voiceover", {}) if isinstance(metadata.get("voiceover", {}), dict) else {}
    render = metadata.get("mascot_story_render", {}) if isinstance(metadata.get("mascot_story_render", {}), dict) else {}
    mascot = metadata.get("mascot_consistency", {}) if isinstance(metadata.get("mascot_consistency", {}), dict) else {}
    visual_aesthetic = analyze_visual_aesthetic_quality(output_dir, plan, metadata)

    blank_scene_count = _blank_scene_count(output_dir, len(plan.scenes))
    prompt_text_visible_count = int(render.get("prompt_text_visible_count", 0) or 0)
    text_crop_count = int(render.get("text_crop_count", 0) or 0)
    caption_collision_count = int(voiceover.get("caption_collision_count", render.get("caption_collision_count", 0)) or 0)
    caption_sync_score = int(voiceover.get("caption_sync_score", 100 if not voiceover_requested else 0) or 0)
    caption_layout_score = int(voiceover.get("caption_layout_score", render.get("caption_layout_score", 100 if not voiceover_requested else 0)) or 0)
    mascot_presence_score = int(mascot.get("mascot_presence_score", 92) or 92)
    mascot_consistency_score = int(mascot.get("mascot_consistency_score", 88) or 88)
    visual_asset_quality_score = int(visual_aesthetic.get("visual_asset_quality_score", 0) or 0)
    broll_or_ai_scene_quality_score = int(visual_aesthetic.get("broll_or_ai_scene_quality_score", 0) or 0)
    scene_visual_completeness_score = (
        min(100, max(70, visual_asset_quality_score + 8))
        if blank_scene_count == 0 and _all_scene_visuals_exist(output_dir, len(plan.scenes))
        else 45
    )
    media_relevance_score = _media_relevance_score(media_plan)
    broll_quality_score = _broll_quality_score(media_plan)
    infographic_quality_score = int(render.get("infographic_quality_score", 88) or 88)
    if visual_aesthetic.get("powerpoint_chart_risk") == "high":
        infographic_quality_score = min(infographic_quality_score, 58)
    story_clarity_score = _story_clarity_score(plan)
    explanation_value_score = 94 if plan.simple_answer and plan.analogy and plan.caveat else 72
    financial_safety_score = _financial_safety_score(plan)
    attribution_score = _attribution_score(attribution)
    professional_edit_score = int(render.get("professional_edit_score", 82) or 82)
    professional_edit_score = min(professional_edit_score, max(45, visual_asset_quality_score + 8))
    viral_readiness_score = round(
        mascot_presence_score * 0.10
        + story_clarity_score * 0.16
        + explanation_value_score * 0.16
        + scene_visual_completeness_score * 0.12
        + media_relevance_score * 0.10
        + infographic_quality_score * 0.10
        + caption_layout_score * 0.08
        + professional_edit_score * 0.12
        + financial_safety_score * 0.06
    )

    visual_types = [scene.visual_type for scene in plan.scenes]
    blockers: list[str] = []
    if blank_scene_count > 0:
        blockers.append(f"blank_scene_count > 0: {blank_scene_count}.")
    if prompt_text_visible_count > 0:
        blockers.append(f"prompt_text_visible_count > 0: {prompt_text_visible_count}.")
    if text_crop_count > 0:
        blockers.append(f"text_crop_count > 0: {text_crop_count}.")
    if caption_collision_count > 0:
        blockers.append(f"caption_collision_count > 0: {caption_collision_count}.")
    if not any(item in {"mascot_ai", "mixed"} for item in visual_types):
        blockers.append("mascot appears in zero scenes.")
    if all(item == "chart_motion" for item in visual_types):
        blockers.append("all scenes are charts.")
    if all(item in {"mascot_ai", "mixed"} for item in visual_types):
        blockers.append("all scenes are mascot closeups.")
    if len(set(visual_types)) < 4:
        blockers.append("no visual variety.")
    if media_relevance_score < 80:
        blockers.append(f"media relevance < 80: {media_relevance_score}.")
    if story_clarity_score < 80:
        blockers.append(f"story clarity < 80: {story_clarity_score}.")
    if professional_edit_score < 80:
        blockers.append(f"professional edit < 80: {professional_edit_score}.")
    if financial_safety_score < 85:
        blockers.append(f"financial safety < 85: {financial_safety_score}.")
    if attribution.get("external_media_used") and attribution.get("missing_attribution_count", 0):
        blockers.append("attribution missing for external media used.")
    for issue in visual_aesthetic.get("blocking_issues", []):
        if isinstance(issue, str):
            blockers.append(issue)
    if media_quality.get("failed_scene_visual_quality_numbers"):
        blockers.append("one or more scenes failed media visual quality.")
    if visual_aesthetic.get("primitive_mascot_risk") == "high":
        blockers.append("primitive mascot risk is high.")
    if visual_aesthetic.get("placeholder_visual_risk") == "high":
        blockers.append("placeholder visual risk is high.")
    if visual_aesthetic.get("powerpoint_chart_risk") == "high":
        blockers.append("PowerPoint-like chart risk is high.")
    if visual_asset_quality_score < 75:
        blockers.append(f"visual asset quality < 75: {visual_asset_quality_score}.")
    if infographic_quality_score < 85:
        blockers.append(f"infographic quality < 85: {infographic_quality_score}.")

    if visual_aesthetic.get("primitive_mascot_risk") == "high" or visual_aesthetic.get("placeholder_visual_risk") == "high":
        viral_readiness_score = min(viral_readiness_score, 40)
    elif visual_aesthetic.get("powerpoint_chart_risk") == "high" or visual_asset_quality_score < 75:
        viral_readiness_score = min(viral_readiness_score, 50)

    warnings: list[str] = []
    if mascot_consistency_score < 85:
        warnings.append("mascot consistency under 85.")
    if fallback.get("missing_api_keys"):
        warnings.append("no real external media from missing API keys: " + ", ".join(fallback.get("missing_api_keys", [])))
    if sum(1 for scene in media_plan.get("scenes", []) if isinstance(scene, dict) and scene.get("generated_ai_prompt")) > 4:
        warnings.append("too much AI imagery.")
    if infographic_quality_score < 88:
        warnings.append("chart feels static.")
    if media_quality.get("ai_generation_required_scene_numbers"):
        warnings.append("AI visual generation was required for scenes: " + ", ".join(str(item) for item in media_quality.get("ai_generation_required_scene_numbers", [])))

    report = {
        "human_review_required": True,
        "automatic_posting_ready": False,
        "publish_ready": False,
        "quality_gate_passed": not blockers,
        "mascot_presence_score": mascot_presence_score,
        "mascot_consistency_score": mascot_consistency_score,
        "story_clarity_score": story_clarity_score,
        "explanation_value_score": explanation_value_score,
        "scene_visual_completeness_score": scene_visual_completeness_score,
        "blank_scene_count": blank_scene_count,
        "prompt_text_visible_count": prompt_text_visible_count,
        "flat_shape_scene_risk": visual_aesthetic.get("flat_shape_scene_risk", "low"),
        "primitive_mascot_risk": visual_aesthetic.get("primitive_mascot_risk", "low"),
        "empty_scene_ratio": visual_aesthetic.get("empty_scene_ratio", 0),
        "dark_empty_area_ratio": visual_aesthetic.get("dark_empty_area_ratio", 0),
        "cropped_text_risk": visual_aesthetic.get("cropped_text_risk", "low"),
        "prompt_text_risk": visual_aesthetic.get("prompt_text_risk", "low"),
        "placeholder_visual_risk": visual_aesthetic.get("placeholder_visual_risk", "low"),
        "powerpoint_chart_risk": visual_aesthetic.get("powerpoint_chart_risk", "low"),
        "caption_box_dominance_ratio": visual_aesthetic.get("caption_box_dominance_ratio", 0),
        "subject_visibility_score": visual_aesthetic.get("subject_visibility_score", 0),
        "visual_asset_quality_score": visual_asset_quality_score,
        "broll_or_ai_scene_quality_score": broll_or_ai_scene_quality_score,
        "media_relevance_score": media_relevance_score,
        "broll_quality_score": broll_quality_score,
        "infographic_quality_score": infographic_quality_score,
        "caption_sync_score": caption_sync_score,
        "caption_layout_score": caption_layout_score,
        "text_crop_count": text_crop_count,
        "caption_collision_count": caption_collision_count,
        "professional_edit_score": professional_edit_score,
        "viral_readiness_score": viral_readiness_score,
        "financial_safety_score": financial_safety_score,
        "attribution_score": attribution_score,
        "blocking_issues": blockers,
        "warnings": warnings,
        "primary_video_path": str(output_dir / "final_reel" / "reel_with_voice_kinetic_subtitles.mp4"),
        "cover_path": str(output_dir / "final_reel" / "cover.jpg"),
        "qa_contact_sheet": str(output_dir / "qa_contact_sheet.jpg"),
        "media_sources_used": media_plan.get("media_sources_used", []),
        "external_media_used": bool(media_plan.get("external_media_used", False)),
        "external_media_files_used": media_quality.get("external_media_files_used", []),
        "missing_api_keys": fallback.get("missing_api_keys", []),
        "visual_aesthetic_report_path": str(output_dir / "visual_aesthetic_report.json"),
        "media_quality_report_path": str(output_dir / "media_quality_report.json"),
    }
    write_mascot_story_quality_report(output_dir, report)
    write_mascot_story_review_reports(output_dir, plan, report)
    return report


def write_mascot_story_quality_report(output_dir: Path, report: dict[str, Any]) -> None:
    (output_dir / "mascot_story_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Mascot Story Quality Report", ""]
    for key in (
        "quality_gate_passed",
        "mascot_presence_score",
        "mascot_consistency_score",
        "story_clarity_score",
        "explanation_value_score",
        "scene_visual_completeness_score",
        "blank_scene_count",
        "prompt_text_visible_count",
        "primitive_mascot_risk",
        "placeholder_visual_risk",
        "powerpoint_chart_risk",
        "caption_box_dominance_ratio",
        "visual_asset_quality_score",
        "broll_or_ai_scene_quality_score",
        "media_relevance_score",
        "broll_quality_score",
        "infographic_quality_score",
        "caption_sync_score",
        "caption_layout_score",
        "text_crop_count",
        "caption_collision_count",
        "professional_edit_score",
        "viral_readiness_score",
        "financial_safety_score",
        "attribution_score",
    ):
        value = report.get(key)
        if isinstance(value, bool):
            value = str(value).lower()
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Blocking Issues"])
    blockers = report.get("blocking_issues", [])
    lines.extend(f"- {issue}" for issue in blockers) if blockers else lines.append("- None")
    lines.extend(["", "## Warnings"])
    warnings = report.get("warnings", [])
    lines.extend(f"- {warning}" for warning in warnings) if warnings else lines.append("- None")
    (output_dir / "mascot_story_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_mascot_story_review_reports(output_dir: Path, plan: MascotStoryPlan, report: dict[str, Any]) -> None:
    qa_dir = output_dir.parents[1] / "qa" if len(output_dir.parents) >= 2 else output_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    media_plan = _read_json(output_dir / "media_plan.json")
    payload = {
        "primary_video_path": report.get("primary_video_path", ""),
        "cover_path": report.get("cover_path", ""),
        "qa_contact_sheet_path": str(output_dir / "qa_contact_sheet.jpg"),
        "visual_aesthetic_report_path": report.get("visual_aesthetic_report_path", ""),
        "media_quality_report_path": report.get("media_quality_report_path", ""),
        "production_visual_minimums_passed": bool(report.get("quality_gate_passed", False)),
        "visual_failure_checks": {
            "primitive_mascot_risk": report.get("primitive_mascot_risk", "low"),
            "placeholder_visual_risk": report.get("placeholder_visual_risk", "low"),
            "powerpoint_chart_risk": report.get("powerpoint_chart_risk", "low"),
            "text_crop_count": report.get("text_crop_count", 0),
            "prompt_text_visible_count": report.get("prompt_text_visible_count", 0),
            "blank_scene_count": report.get("blank_scene_count", 0),
        },
        "mascot_notes": "Miko must be a production bitmap/AI character, never a primitive shape drawing.",
        "media_sources_actually_used": media_plan.get("media_sources_used", []),
        "external_media_files_used": report.get("external_media_files_used", []),
        "missing_api_key_warnings": report.get("missing_api_keys", []),
        "story_summary": plan.story_angle,
        "known_weak_points": report.get("warnings", []),
        "human_checklist": [
            "Is Miko actually high-quality and brandable?",
            "Are there any primitive shape scenes?",
            "Any empty/dark slides?",
            "Any PowerPoint-like charts?",
            "Any cropped text?",
            "Does it feel like a premium Reel?",
            "Is the explanation useful?",
            "Would this be worth saving/sharing?",
        ],
    }
    review_json = json.dumps(payload, ensure_ascii=False, indent=2)
    (qa_dir / "mascot_story_review_report.json").write_text(review_json, encoding="utf-8")
    (qa_dir / "mascot_story_v2_review_report.json").write_text(review_json, encoding="utf-8")
    lines = [
        "# Mascot Story Review Report",
        "",
        f"- primary video path: {payload['primary_video_path']}",
        f"- cover path: {payload['cover_path']}",
        f"- qa contact sheet path: {payload['qa_contact_sheet_path']}",
        f"- visual aesthetic report path: {payload['visual_aesthetic_report_path']}",
        f"- media quality report path: {payload['media_quality_report_path']}",
        f"- production visual minimums passed: {str(payload['production_visual_minimums_passed']).lower()}",
        f"- mascot notes: {payload['mascot_notes']}",
        f"- media sources actually used: {', '.join(str(item) for item in payload['media_sources_actually_used'])}",
        f"- external media files used: {', '.join(str(item) for item in payload['external_media_files_used']) or 'none'}",
        f"- missing API key warnings: {', '.join(str(item) for item in payload['missing_api_key_warnings']) or 'none'}",
        f"- story summary: {payload['story_summary']}",
        "",
        "## Known Weak Points",
    ]
    weak = payload["known_weak_points"]
    lines.extend(f"- {item}" for item in weak) if weak else lines.append("- None")
    lines.extend(["", "## Human Checklist"])
    lines.extend(f"- {item}" for item in payload["human_checklist"])
    review_md = "\n".join(lines) + "\n"
    (qa_dir / "mascot_story_review_report.md").write_text(review_md, encoding="utf-8")
    (qa_dir / "mascot_story_v2_review_report.md").write_text(review_md, encoding="utf-8")


def write_mascot_story_technical_report(output_dir: Path, technical: dict[str, Any]) -> None:
    qa_dir = output_dir.parents[1] / "qa" if len(output_dir.parents) >= 2 else output_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    technical_json = json.dumps(technical, ensure_ascii=False, indent=2)
    (qa_dir / "mascot_story_technical_report.json").write_text(technical_json, encoding="utf-8")
    (qa_dir / "mascot_story_v2_technical_report.json").write_text(technical_json, encoding="utf-8")
    lines = ["# Mascot Story Technical Report", ""]
    for key, value in technical.items():
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        elif isinstance(value, bool):
            value = str(value).lower()
        lines.append(f"- {key}: {value}")
    technical_md = "\n".join(lines) + "\n"
    (qa_dir / "mascot_story_technical_report.md").write_text(technical_md, encoding="utf-8")
    (qa_dir / "mascot_story_v2_technical_report.md").write_text(technical_md, encoding="utf-8")


def _story_clarity_score(plan: MascotStoryPlan) -> int:
    roles = [scene.role for scene in plan.scenes]
    required = ["hook", "question", "analogy", "mechanism", "example", "twist", "takeaway"]
    score = 72 + sum(4 for role in required if role in roles)
    if "not financial advice" in (plan.caption + " " + plan.caveat).lower():
        score += 4
    return min(100, score)


def _financial_safety_score(plan: MascotStoryPlan) -> int:
    text = " ".join([plan.caption, plan.caveat, plan.voiceover_script]).lower()
    score = 82
    if "not financial advice" in text:
        score += 8
    if "indirect" in text and ("context" in text or "depends" in text):
        score += 8
    if "importer" in text and "exporter" in text:
        score += 5
    if "buy" in text and ("stock" in text or "trade" in text):
        score -= 18
    return max(0, min(100, score))


def _media_relevance_score(media_plan: dict[str, Any]) -> int:
    scenes = media_plan.get("scenes", []) if isinstance(media_plan, dict) else []
    scores = []
    if isinstance(scenes, list):
        for scene in scenes:
            selected = scene.get("selected", {}) if isinstance(scene, dict) else {}
            if isinstance(selected, dict):
                scores.append(int(selected.get("relevance_score", 80) or 80))
    return round(sum(scores) / len(scores)) if scores else 60


def _broll_quality_score(media_plan: dict[str, Any]) -> int:
    scenes = media_plan.get("scenes", []) if isinstance(media_plan, dict) else []
    scores = []
    if isinstance(scenes, list):
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            selected = scene.get("selected", {})
            if isinstance(selected, dict) and scene.get("requested_visual_type") in {"broll_photo", "broll_video"}:
                scores.append(int(selected.get("visual_clarity_score", 78) or 78))
    return round(sum(scores) / len(scores)) if scores else 82


def _attribution_score(attribution: dict[str, Any]) -> int:
    if not attribution.get("external_media_used"):
        return 90
    missing = int(attribution.get("missing_attribution_count", 0) or 0)
    return 100 if missing == 0 else max(0, 80 - missing * 25)


def _all_scene_visuals_exist(output_dir: Path, count: int) -> bool:
    return all((output_dir / "raw_images" / f"slide_{index:02d}.jpg").exists() for index in range(1, count + 1))


def _blank_scene_count(output_dir: Path, count: int) -> int:
    blanks = 0
    for index in range(1, count + 1):
        path = output_dir / "final_reel" / "frames" / f"frame_{index:02d}.jpg"
        if not _image_is_size(path, REEL_SIZE):
            blanks += 1
            continue
        with Image.open(path).convert("RGB") as image:
            stat = ImageStat.Stat(image)
            brightness = sum(stat.mean) / 3
            variance = sum(stat.var) / 3
            if brightness < 8 or variance < 6:
                blanks += 1
    return blanks


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _image_is_size(path: Path, expected: tuple[int, int]) -> bool:
    try:
        with Image.open(path) as image:
            return image.size == expected
    except Exception:
        return False
