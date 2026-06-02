"""Quality gate for hosted explainer Reel packages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image

from app.content.explainer_schemas import ExplainerPlan
from app.render.native_reel_renderer import REEL_SIZE


def run_explainer_quality_gate(output_dir: Path, plan: ExplainerPlan, metadata: dict[str, Any], voiceover_requested: bool) -> dict[str, Any]:
    media_plan = _read_json(output_dir / "media_plan.json")
    attribution = _read_json(output_dir / "media_attribution.json")
    voiceover = metadata.get("voiceover", {}) if isinstance(metadata.get("voiceover", {}), dict) else {}
    render = metadata.get("explainer_reel_render", {}) if isinstance(metadata.get("explainer_reel_render", {}), dict) else {}

    hook_clarity_score = 92 if "?" in plan.core_question or any(word in plan.hook.lower() for word in ("connected", "simple", "why")) else 76
    explanation_value_score = 94 if plan.simple_answer and len(plan.caveats) >= 2 else 72
    media_relevance_score = _media_relevance_score(media_plan)
    host_consistency_score = int(metadata.get("host_consistency", {}).get("host_consistency_score", 82) if isinstance(metadata.get("host_consistency", {}), dict) else 82)
    caption_sync_score = int(voiceover.get("caption_sync_score", 100 if not voiceover_requested else 0) or 0)
    caption_layout_score = int(voiceover.get("caption_layout_score", render.get("caption_layout_score", 100 if not voiceover_requested else 0)) or 0)
    caption_collision_count = int(voiceover.get("caption_collision_count", render.get("caption_collision_count", 0)) or 0)
    visual_variety_score = min(100, 58 + len({scene.visual_type for scene in plan.scenes}) * 10)
    chart_clarity_score = 92 if any(scene.visual_type == "generated_chart" for scene in plan.scenes) else 70
    factual_safety_score = _factual_safety_score(plan)
    financial_advice_risk = "low" if _has_financial_caveat(plan) else "high"
    source_attribution_score = _source_attribution_score(attribution)
    professional_edit_score = int(render.get("professional_edit_score", 88) or 88)
    viral_readiness_score = round(
        hook_clarity_score * 0.16
        + explanation_value_score * 0.18
        + media_relevance_score * 0.12
        + visual_variety_score * 0.12
        + caption_sync_score * 0.10
        + caption_layout_score * 0.10
        + factual_safety_score * 0.12
        + professional_edit_score * 0.10
    )

    blockers: list[str] = []
    if caption_collision_count > 0:
        blockers.append(f"caption collision > 0: {caption_collision_count}.")
    if media_relevance_score < 70:
        blockers.append(f"media_relevance_score is below 70: {media_relevance_score}.")
    if not any(scene.visual_type == "host_ai" for scene in plan.scenes):
        blockers.append("host missing from all scenes.")
    if len({scene.visual_type for scene in plan.scenes}) < 3:
        blockers.append("no B-roll/media variety.")
    if not plan.simple_answer:
        blockers.append("no clear answer.")
    if financial_advice_risk == "high":
        blockers.append("financial_advice_risk high.")
    if factual_safety_score < 80:
        blockers.append(f"factual_safety_score is below 80: {factual_safety_score}.")
    if professional_edit_score < 80:
        blockers.append(f"professional_edit_score is below 80: {professional_edit_score}.")
    if viral_readiness_score < 75:
        blockers.append(f"viral_readiness_score is below 75: {viral_readiness_score}.")
    if voiceover_requested and caption_sync_score < 80:
        blockers.append(f"caption_sync_score is below 80: {caption_sync_score}.")
    if voiceover_requested and caption_layout_score < 85:
        blockers.append(f"caption_layout_score is below 85: {caption_layout_score}.")
    if attribution.get("missing_attribution_count", 0):
        blockers.append("External media attribution metadata is incomplete.")
    for index in range(1, 6):
        path = output_dir / "final_reel" / "frames" / f"frame_{index:02d}.jpg"
        if not _image_is_size(path, REEL_SIZE):
            blockers.append(f"frame_{index:02d} is missing or not 1080x1920.")

    report = {
        "human_review_required": True,
        "automatic_posting_ready": False,
        "publish_ready": False,
        "quality_gate_passed": not blockers,
        "hook_clarity_score": hook_clarity_score,
        "explanation_value_score": explanation_value_score,
        "media_relevance_score": media_relevance_score,
        "host_consistency_score": host_consistency_score,
        "caption_sync_score": caption_sync_score,
        "caption_layout_score": caption_layout_score,
        "caption_collision_count": caption_collision_count,
        "visual_variety_score": visual_variety_score,
        "chart_clarity_score": chart_clarity_score,
        "factual_safety_score": factual_safety_score,
        "financial_advice_risk": financial_advice_risk,
        "source_attribution_score": source_attribution_score,
        "professional_edit_score": professional_edit_score,
        "viral_readiness_score": viral_readiness_score,
        "blocking_issues": blockers,
        "primary_video_path": str(output_dir / "final_reel" / "reel_with_voice_kinetic_subtitles.mp4"),
        "cover_path": str(output_dir / "final_reel" / "cover.jpg"),
        "qa_contact_sheet": str(output_dir / "qa_contact_sheet.jpg"),
        "attribution_file": str(output_dir / "media_attribution.json"),
    }
    write_explainer_quality_report(output_dir, report)
    return report


def write_explainer_quality_report(output_dir: Path, report: dict[str, Any]) -> None:
    (output_dir / "explainer_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Explainer Host Quality Report",
        "",
        f"- human_review_required: {str(report['human_review_required']).lower()}",
        f"- quality_gate_passed: {str(report['quality_gate_passed']).lower()}",
        f"- automatic_posting_ready: {str(report['automatic_posting_ready']).lower()}",
        f"- hook_clarity_score: {report['hook_clarity_score']}",
        f"- explanation_value_score: {report['explanation_value_score']}",
        f"- media_relevance_score: {report['media_relevance_score']}",
        f"- host_consistency_score: {report['host_consistency_score']}",
        f"- caption_sync_score: {report['caption_sync_score']}",
        f"- caption_layout_score: {report['caption_layout_score']}",
        f"- visual_variety_score: {report['visual_variety_score']}",
        f"- chart_clarity_score: {report['chart_clarity_score']}",
        f"- factual_safety_score: {report['factual_safety_score']}",
        f"- financial_advice_risk: {report['financial_advice_risk']}",
        f"- source_attribution_score: {report['source_attribution_score']}",
        f"- professional_edit_score: {report['professional_edit_score']}",
        f"- viral_readiness_score: {report['viral_readiness_score']}",
        "",
        "## Blocking Issues",
    ]
    blockers = report.get("blocking_issues", [])
    lines.extend(f"- {issue}" for issue in blockers) if blockers else lines.append("- None")
    (output_dir / "explainer_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _media_relevance_score(media_plan: dict[str, Any]) -> int:
    scenes = media_plan.get("scenes", []) if isinstance(media_plan, dict) else []
    scores: list[int] = []
    if isinstance(scenes, list):
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            selected = scene.get("selected", {})
            if isinstance(selected, dict):
                scores.append(int(selected.get("relevance_score", 70) or 70))
    return round(sum(scores) / len(scores)) if scores else 60


def _factual_safety_score(plan: ExplainerPlan) -> int:
    score = 86
    if all(scene.source_needed for scene in plan.scenes if scene.needs_fact_check):
        score += 6
    if _has_financial_caveat(plan):
        score += 8
    if any("always" in scene.voiceover_line.lower() for scene in plan.scenes):
        score -= 20
    return max(0, min(100, score))


def _has_financial_caveat(plan: ExplainerPlan) -> bool:
    text = " ".join([plan.caption, *plan.caveats, plan.voiceover_script]).lower()
    return "not financial advice" in text and ("indirect" in text or "context" in text)


def _source_attribution_score(attribution: dict[str, Any]) -> int:
    if not attribution.get("external_media_used"):
        return 90
    missing = int(attribution.get("missing_attribution_count", 0) or 0)
    return 100 if missing == 0 else max(0, 80 - missing * 25)


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
