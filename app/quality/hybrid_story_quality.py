"""Quality gate and reports for hybrid story explainer Reels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat

from app.content.hybrid_story_schemas import HybridStoryPlan
from app.quality.composition_quality import evaluate_hybrid_composition
from app.render.native_reel_renderer import REEL_SIZE


def run_hybrid_story_quality_gate(
    output_dir: Path,
    plan: HybridStoryPlan,
    metadata: dict[str, Any],
    voiceover_requested: bool,
) -> dict[str, Any]:
    media_plan = _read_json(output_dir / "media_plan.json")
    media_quality = _read_json(output_dir / "media_quality_report.json")
    attribution = _read_json(output_dir / "media_attribution.json")
    voiceover = metadata.get("voiceover", {}) if isinstance(metadata.get("voiceover", {}), dict) else {}
    render = metadata.get("hybrid_story_render", {}) if isinstance(metadata.get("hybrid_story_render", {}), dict) else {}
    composition = evaluate_hybrid_composition(plan, media_plan, render, voiceover)

    blank_scene_count = _blank_scene_count(output_dir, len(plan.scenes))
    prompt_text_visible_count = int(render.get("prompt_text_visible_count", 0) or 0)
    text_crop_count = int(render.get("text_crop_count", 0) or 0)
    caption_collision_count = int(voiceover.get("caption_collision_count", render.get("caption_collision_count", 0)) or 0)
    caption_sync_score = int(voiceover.get("caption_sync_score", 100 if not voiceover_requested else 0) or 0)
    caption_layout_score = int(voiceover.get("caption_layout_score", render.get("caption_layout_score", 92 if not voiceover_requested else 0)) or 0)
    caption_box_dominance_ratio = float(
        voiceover.get("caption_box_dominance_ratio", render.get("caption_box_dominance_ratio", composition.get("caption_box_dominance_ratio", 0.08)))
        or 0.08
    )

    real_world_context_scenes = sum(1 for scene in plan.scenes if scene.visual_type in {"real_world_broll", "ai_realistic_scene", "hybrid_broll_overlay", "mascot_context_scene"})
    mascot_scenes = sum(1 for scene in plan.scenes if scene.mascot_presence != "none")
    mascot_dominant_scenes = sum(1 for scene in plan.scenes if scene.mascot_frame_share_target > 0.35 or scene.mascot_presence == "central_only_if_justified")
    max_mascot_frame_share = max((scene.mascot_frame_share_target for scene in plan.scenes), default=0.0)
    questioner_or_proxy_present = any(scene.proxy_role_optional != "none" or scene.questioner_line_optional for scene in plan.scenes)
    infographic_scenes_used = sum(1 for scene in plan.scenes if scene.visual_type == "premium_infographic")
    ai_generated_scenes_used = sum(
        1
        for scene in media_plan.get("scenes", [])
        if isinstance(scene, dict) and bool(scene.get("ai_generation_required", False))
    )
    media_sources_used = media_plan.get("media_sources_used", [])
    external_media_files_used = _external_files(media_plan)
    external_media_used_truthful = bool(media_plan.get("external_media_used", False)) == bool(external_media_files_used)

    hook_strength_score = 90 if plan.scenes[0].visual_type in {"real_world_broll", "hybrid_broll_overlay"} else 70
    story_clarity_score = _story_clarity_score(plan)
    scenario_concreteness_score = _scenario_concreteness_score(plan)
    contrast_or_twist_score = 96 if any(scene.role in {"contrast", "nuance"} for scene in plan.scenes) else 55
    explanation_value_score = 94 if plan.simple_answer and plan.caveat else 72
    media_relevance_score = _average_scene_value(media_plan, "scene_relevance_score", 84)
    media_quality_score = _average_scene_value(media_plan, "quality_score", 84)
    visual_coherence_score = int(composition.get("visual_coherence_score", 0) or 0)
    composition_quality_score = int(composition.get("composition_quality_score", 0) or 0)
    mascot_usefulness_score = int(composition.get("mascot_usefulness_score", 0) or 0)
    mascot_dominance_risk = _risk_label(88 if mascot_dominant_scenes > 1 or max_mascot_frame_share > 0.45 else 28 if max_mascot_frame_share > 0.35 else 10)
    mascot_context_relevance_score = _mascot_context_relevance_score(plan)
    infographic_quality_score = int(render.get("infographic_quality_score", 90) or 90)
    editorial_polish_score = int(composition.get("editorial_polish_score", 0) or 0)
    cheapness_risk_score = int(composition.get("cheapness_risk_score", 0) or 0)
    stock_montage_risk = _stock_montage_risk(media_plan, plan)
    originality_transform_score = 92 if infographic_scenes_used and ai_generated_scenes_used else 84
    professional_edit_score = int(render.get("professional_edit_score", 88) or 88)
    abstraction_to_concrete_score = int(composition.get("abstraction_to_concrete_score", 0) or 0)
    financial_safety_score = _financial_safety_score(plan)
    virality_trigger_score = int(composition.get("virality_trigger_score", 82) or 82)
    viral_readiness_score = round(
        hook_strength_score * 0.10
        + story_clarity_score * 0.12
        + scenario_concreteness_score * 0.12
        + explanation_value_score * 0.12
        + media_relevance_score * 0.10
        + visual_coherence_score * 0.09
        + composition_quality_score * 0.09
        + mascot_usefulness_score * 0.06
        + editorial_polish_score * 0.08
        + professional_edit_score * 0.06
        + financial_safety_score * 0.06
    )
    if cheapness_risk_score >= 70:
        viral_readiness_score = min(viral_readiness_score, 55)
    elif cheapness_risk_score >= 45:
        viral_readiness_score = min(viral_readiness_score, 85)
    if mascot_usefulness_score < 70 or visual_coherence_score < 80:
        viral_readiness_score = min(viral_readiness_score, 85)

    blockers: list[str] = []
    blockers.extend(str(issue) for issue in composition.get("blocking_issues", []) if str(issue).strip())
    if blank_scene_count > 0:
        blockers.append(f"blank_scene_count > 0: {blank_scene_count}.")
    if prompt_text_visible_count > 0:
        blockers.append(f"prompt_text_visible_count > 0: {prompt_text_visible_count}.")
    if text_crop_count > 0:
        blockers.append(f"text_crop_count > 0: {text_crop_count}.")
    if caption_collision_count > 0:
        blockers.append(f"caption_collision_count > 0: {caption_collision_count}.")
    if real_world_context_scenes < 3:
        blockers.append(f"real-world/realistic context scenes < 3: {real_world_context_scenes}.")
    if mascot_scenes < 2:
        blockers.append(f"mascot scenes < 2: {mascot_scenes}.")
    if mascot_dominant_scenes > 1:
        blockers.append(f"mascot dominant scenes > 1: {mascot_dominant_scenes}.")
    if max_mascot_frame_share > 0.35 and not any(scene.mascot_presence == "central_only_if_justified" for scene in plan.scenes):
        blockers.append(f"max mascot frame share > 0.35: {max_mascot_frame_share:.2f}.")
    if not questioner_or_proxy_present:
        blockers.append("questioner_or_proxy_present is false.")
    if infographic_quality_score < 85:
        blockers.append(f"infographic quality < 85: {infographic_quality_score}.")
    if composition_quality_score < 80:
        blockers.append(f"composition quality < 80: {composition_quality_score}.")
    if visual_coherence_score < 80:
        blockers.append(f"visual coherence < 80: {visual_coherence_score}.")
    if media_relevance_score < 80:
        blockers.append(f"media relevance < 80: {media_relevance_score}.")
    if story_clarity_score < 85:
        blockers.append(f"story clarity < 85: {story_clarity_score}.")
    if scenario_concreteness_score < 80:
        blockers.append(f"scenario concreteness < 80: {scenario_concreteness_score}.")
    if explanation_value_score < 85:
        blockers.append(f"explanation value < 85: {explanation_value_score}.")
    if financial_safety_score < 90:
        blockers.append(f"financial safety < 90: {financial_safety_score}.")
    if cheapness_risk_score >= 70:
        blockers.append(f"cheapness risk is high: {cheapness_risk_score}.")
    if stock_montage_risk >= 70:
        blockers.append(f"stock montage risk is high: {stock_montage_risk}.")
    if media_quality.get("not_production_ready_scene_numbers"):
        blockers.append("one or more scenes are production_ready=false.")
    if not external_media_used_truthful:
        blockers.append("external_media_used flag does not match actual external files.")

    report = {
        "human_review_required": True,
        "review_required": True,
        "automatic_posting_ready": False,
        "publish_ready": False,
        "quality_gate_passed": not blockers,
        "hook_strength_score": hook_strength_score,
        "story_clarity_score": story_clarity_score,
        "scenario_concreteness_score": scenario_concreteness_score,
        "questioner_or_proxy_score": 96 if questioner_or_proxy_present else 0,
        "abstraction_to_concrete_score": abstraction_to_concrete_score,
        "contrast_or_twist_score": contrast_or_twist_score,
        "explanation_value_score": explanation_value_score,
        "media_relevance_score": media_relevance_score,
        "media_quality_score": media_quality_score,
        "visual_coherence_score": visual_coherence_score,
        "composition_quality_score": composition_quality_score,
        "mascot_usefulness_score": mascot_usefulness_score,
        "mascot_dominance_risk": mascot_dominance_risk,
        "mascot_context_relevance_score": mascot_context_relevance_score,
        "infographic_quality_score": infographic_quality_score,
        "caption_sync_score": caption_sync_score,
        "caption_layout_score": caption_layout_score,
        "caption_dominance_score": max(0, round(100 - caption_box_dominance_ratio * 420)),
        "caption_box_dominance_ratio": round(caption_box_dominance_ratio, 3),
        "editorial_polish_score": editorial_polish_score,
        "cheapness_risk_score": cheapness_risk_score,
        "cheapness_risk_label": _risk_label(cheapness_risk_score),
        "stock_montage_risk": stock_montage_risk,
        "originality_transform_score": originality_transform_score,
        "professional_edit_score": professional_edit_score,
        "viral_readiness_score": viral_readiness_score,
        "financial_safety_score": financial_safety_score,
        "real_world_context_scenes": real_world_context_scenes,
        "mascot_scenes": mascot_scenes,
        "mascot_dominant_scenes": mascot_dominant_scenes,
        "max_mascot_frame_share": round(max_mascot_frame_share, 3),
        "questioner_or_proxy_present": questioner_or_proxy_present,
        "infographic_scenes_used": infographic_scenes_used,
        "ai_generated_scenes_used": ai_generated_scenes_used,
        "media_sources_used": media_sources_used,
        "external_media_used": bool(external_media_files_used),
        "external_media_files_used": external_media_files_used,
        "external_media_used_requires_actual_file": external_media_used_truthful,
        "production_visual_minimums_passed": not blockers,
        "blank_scene_count": blank_scene_count,
        "prompt_text_visible_count": prompt_text_visible_count,
        "text_crop_count": text_crop_count,
        "caption_collision_count": caption_collision_count,
        "composition_scene_metrics": composition.get("scene_metrics", []),
        "blocking_issues": sorted(set(blockers)),
        "warnings": _warnings(media_quality, cheapness_risk_score, ai_generated_scenes_used),
        "primary_video_path": str(output_dir / "final_reel" / "reel_with_voice_kinetic_subtitles.mp4"),
        "cover_path": str(output_dir / "final_reel" / "cover.jpg"),
        "qa_contact_sheet": str(output_dir / "qa_contact_sheet.jpg"),
        "media_decision_report_path": str(output_dir / "media_decision_report.json"),
        "media_attribution_path": str(output_dir / "media_attribution.json"),
        "hybrid_story_quality_report_path": str(output_dir / "hybrid_story_quality_report.json"),
        "attribution": attribution,
    }
    write_hybrid_story_quality_report(output_dir, report)
    return report


def write_hybrid_story_quality_report(output_dir: Path, report: dict[str, Any]) -> None:
    (output_dir / "hybrid_story_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    keys = [
        "quality_gate_passed",
        "story_clarity_score",
        "scenario_concreteness_score",
        "media_relevance_score",
        "visual_coherence_score",
        "composition_quality_score",
        "mascot_usefulness_score",
        "mascot_dominance_risk",
        "infographic_quality_score",
        "caption_layout_score",
        "caption_box_dominance_ratio",
        "cheapness_risk_score",
        "editorial_polish_score",
        "professional_edit_score",
        "viral_readiness_score",
        "financial_safety_score",
        "publish_ready",
        "review_required",
    ]
    lines = ["# Hybrid Story Quality Report", ""]
    for key in keys:
        value = report.get(key)
        if isinstance(value, bool):
            value = str(value).lower()
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Blocking Issues"])
    blockers = report.get("blocking_issues", [])
    lines.extend(f"- {item}" for item in blockers) if blockers else lines.append("- None")
    lines.extend(["", "## Warnings"])
    warnings = report.get("warnings", [])
    lines.extend(f"- {item}" for item in warnings) if warnings else lines.append("- None")
    (output_dir / "hybrid_story_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _story_clarity_score(plan: HybridStoryPlan) -> int:
    roles = {scene.role for scene in plan.scenes}
    score = 70 + sum(3 for role in ("hook", "question", "setup", "mechanism", "consequence", "contrast", "nuance", "takeaway") if role in roles)
    if "indirect" in (plan.caveat + " " + plan.caption).lower():
        score += 4
    return min(100, score)


def _scenario_concreteness_score(plan: HybridStoryPlan) -> int:
    concrete_terms = ("invoice", "bill", "importer", "tanker", "station", "port", "wallet", "barrel", "desk", "shipping")
    hits = 0
    for scene in plan.scenes:
        text = " ".join([scene.voiceover_line, scene.media_query, " ".join(scene.required_context_objects)]).lower()
        if any(term in text for term in concrete_terms):
            hits += 1
    return min(100, 58 + hits * 6)


def _mascot_context_relevance_score(plan: HybridStoryPlan) -> int:
    mascot_scenes = [scene for scene in plan.scenes if scene.mascot_presence != "none"]
    if not mascot_scenes:
        return 0
    relevant = 0
    for scene in mascot_scenes:
        text = " ".join(scene.required_context_objects + [scene.visual_objective, scene.composition_notes]).lower()
        if any(term in text for term in ("invoice", "bill", "oil", "dollar", "map", "flow", "context", "chart")):
            relevant += 1
    return round(70 + 30 * relevant / len(mascot_scenes))


def _financial_safety_score(plan: HybridStoryPlan) -> int:
    text = " ".join([plan.caption, plan.caveat, plan.voiceover_script]).lower()
    score = 82
    if "not financial advice" in text:
        score += 10
    if "indirect" in text and ("context" in text or "context-dependent" in text):
        score += 8
    if "importer" in text and "exporter" in text:
        score += 4
    if "buy" in text and ("stock" in text or "trade signal" in text):
        score -= 20
    return max(0, min(100, score))


def _average_scene_value(media_plan: dict[str, Any], key: str, default: int) -> int:
    values = []
    for scene in media_plan.get("scenes", []):
        if isinstance(scene, dict):
            values.append(int(scene.get(key, default) or default))
    return round(sum(values) / len(values)) if values else default


def _stock_montage_risk(media_plan: dict[str, Any], plan: HybridStoryPlan) -> int:
    external_count = sum(
        1
        for scene in media_plan.get("scenes", [])
        if isinstance(scene, dict) and bool(scene.get("external_media_used", False))
    )
    if external_count <= 3:
        return 18
    if any(scene.visual_type == "premium_infographic" for scene in plan.scenes) and any(scene.mascot_presence != "none" for scene in plan.scenes):
        return 36
    return 76


def _external_files(media_plan: dict[str, Any]) -> list[str]:
    files: list[str] = []
    for scene in media_plan.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        selected = scene.get("selected", {})
        if not isinstance(selected, dict):
            continue
        path = Path(str(selected.get("local_path", "")))
        if selected.get("provider") in {"pexels", "unsplash", "wikimedia"} and path.exists() and path.stat().st_size > 0:
            files.append(str(path))
    return files


def _warnings(media_quality: dict[str, Any], cheapness_risk_score: int, ai_generated_scenes_used: int) -> list[str]:
    warnings: list[str] = []
    if ai_generated_scenes_used > 4:
        warnings.append("many scenes require AI generation; human review should inspect realism and composition")
    if cheapness_risk_score >= 45:
        warnings.append("cheapness risk is not low")
    if media_quality.get("ai_generation_required_scene_numbers"):
        warnings.append(
            "AI visual generation required for scenes: "
            + ", ".join(str(item) for item in media_quality.get("ai_generation_required_scene_numbers", []))
        )
    return warnings


def _risk_label(score: int | float) -> str:
    score = float(score)
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


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


def _image_is_size(path: Path, expected: tuple[int, int]) -> bool:
    try:
        with Image.open(path) as image:
            return image.size == expected
    except Exception:
        return False


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
