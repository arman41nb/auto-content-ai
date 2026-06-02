"""Composition heuristics for hybrid story Reels."""

from __future__ import annotations

from statistics import mean
from typing import Any

from app.content.hybrid_story_schemas import HybridStoryPlan, HybridStoryScene


REAL_CONTEXT_TYPES = {"real_world_broll", "ai_realistic_scene", "hybrid_broll_overlay", "mascot_context_scene"}
MASCOT_CONTEXT_TYPES = {"mascot_context_scene", "mascot_small_overlay", "takeaway_scene"}


def evaluate_scene_composition(
    scene: HybridStoryScene,
    media_scene: dict[str, Any] | None = None,
    caption_box_dominance_ratio: float = 0.08,
) -> dict[str, Any]:
    media_scene = media_scene or {}
    provider = ""
    selected = media_scene.get("selected", {})
    if isinstance(selected, dict):
        provider = str(selected.get("provider", ""))

    context_count = len(scene.required_context_objects)
    mascot_share = float(scene.mascot_frame_share_target or 0.0)
    context_bonus = min(18, context_count * 4)
    real_context_bonus = 8 if scene.visual_type in REAL_CONTEXT_TYPES else 0
    subject_balance_score = _clamp(94 - max(0, mascot_share - 0.28) * 120 + real_context_bonus)
    context_density_score = _clamp(62 + context_bonus + real_context_bonus)
    semantic_relevance_score = _clamp(74 + context_bonus + (8 if provider in {"pexels", "unsplash", "wikimedia", "ai_generated", "premium_infographic"} else 0))
    mascot_dominance_score = _clamp(100 - mascot_share * 140)
    empty_space_score = _clamp(88 if context_count >= 3 else 66)
    title_card_risk = _risk_score(
        scene.visual_type == "premium_infographic" and context_count < 3,
        count_words(scene.caption_text) <= 2 and scene.visual_type not in {"real_world_broll", "hybrid_broll_overlay"},
        "title" in scene.visual_objective.lower(),
    )
    template_cheapness_risk = _risk_score(
        scene.mascot_presence == "central_only_if_justified",
        scene.mascot_frame_share_target > 0.35,
        scene.visual_type in MASCOT_CONTEXT_TYPES and context_count < 4,
        title_card_risk >= 60,
    )
    caption_dominance_score = _clamp(100 - caption_box_dominance_ratio * 420)
    text_visual_hierarchy_score = _clamp(92 - max(0.0, caption_box_dominance_ratio - 0.12) * 260)
    editorial_polish_score = _clamp(
        subject_balance_score * 0.25
        + context_density_score * 0.2
        + semantic_relevance_score * 0.25
        + caption_dominance_score * 0.1
        + (100 - template_cheapness_risk) * 0.2
    )
    style_coherence_score = _clamp(88 if scene.visual_type in REAL_CONTEXT_TYPES | {"premium_infographic", "takeaway_scene"} else 80)
    blockers: list[str] = []
    if scene.mascot_frame_share_target > 0.45 and scene.mascot_presence != "central_only_if_justified":
        blockers.append("mascot overdominance above 45% without central justification")
    if scene.mascot_frame_share_target > 0.35 and scene.role not in {"hook", "takeaway"}:
        blockers.append("mascot frame share above 35% outside a justified hook/takeaway")
    if context_density_score < 75:
        blockers.append("context density below production threshold")
    if title_card_risk >= 75:
        blockers.append("title-card risk is high")
    if caption_box_dominance_ratio > 0.18:
        blockers.append("caption box dominance is above hook/takeaway threshold")
    return {
        "scene_number": scene.scene_number,
        "role": scene.role,
        "visual_type": scene.visual_type,
        "subject_balance_score": round(subject_balance_score),
        "context_density_score": round(context_density_score),
        "semantic_relevance_score": round(semantic_relevance_score),
        "mascot_dominance_score": round(mascot_dominance_score),
        "empty_space_score": round(empty_space_score),
        "title_card_risk": round(title_card_risk),
        "template_cheapness_risk": round(template_cheapness_risk),
        "caption_dominance_score": round(caption_dominance_score),
        "text_visual_hierarchy_score": round(text_visual_hierarchy_score),
        "editorial_polish_score": round(editorial_polish_score),
        "style_coherence_score": round(style_coherence_score),
        "mascot_frame_share_estimate": round(mascot_share, 3),
        "blocking_issues": blockers,
    }


def evaluate_hybrid_composition(
    plan: HybridStoryPlan,
    media_plan: dict[str, Any],
    render_metadata: dict[str, Any] | None = None,
    voiceover_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    render_metadata = render_metadata or {}
    voiceover_metadata = voiceover_metadata or {}
    caption_ratio = float(
        voiceover_metadata.get(
            "caption_box_dominance_ratio",
            render_metadata.get("caption_box_dominance_ratio", 0.08),
        )
        or 0.08
    )
    media_by_scene = {
        int(scene.get("scene_number", 0) or 0): scene
        for scene in media_plan.get("scenes", [])
        if isinstance(scene, dict)
    }
    scene_metrics = [
        evaluate_scene_composition(scene, media_by_scene.get(scene.scene_number, {}), caption_ratio)
        for scene in plan.scenes
    ]
    blockers = [
        issue
        for scene in scene_metrics
        for issue in scene.get("blocking_issues", [])
        if isinstance(issue, str)
    ]
    visual_coherence_score = round(mean(int(scene["style_coherence_score"]) for scene in scene_metrics))
    scene_relevance_score = round(mean(int(scene["semantic_relevance_score"]) for scene in scene_metrics))
    mascot_usefulness_score = _mascot_usefulness_score(plan)
    editorial_polish_score = round(mean(int(scene["editorial_polish_score"]) for scene in scene_metrics))
    composition_quality_score = round(
        mean(
            [
                mean(int(scene[key]) for key in ("subject_balance_score", "context_density_score", "text_visual_hierarchy_score"))
                for scene in scene_metrics
            ]
        )
    )
    abstraction_to_concrete_score = _abstraction_to_concrete_score(plan)
    virality_trigger_score = _clamp(
        plan.scenes[0].visual_type in REAL_CONTEXT_TYPES,
        100,
        78,
    )
    cheapness_risk_score = round(mean(int(scene["template_cheapness_risk"]) for scene in scene_metrics))
    if _generic_title_card_sequence(plan):
        cheapness_risk_score = max(cheapness_risk_score, 82)
        blockers.append("generic title-card sequence detected")
    if caption_ratio > 0.18:
        cheapness_risk_score = max(cheapness_risk_score, 76)
    return {
        "scene_metrics": scene_metrics,
        "visual_coherence_score": visual_coherence_score,
        "scene_relevance_score": scene_relevance_score,
        "mascot_usefulness_score": mascot_usefulness_score,
        "editorial_polish_score": editorial_polish_score,
        "composition_quality_score": composition_quality_score,
        "abstraction_to_concrete_score": abstraction_to_concrete_score,
        "virality_trigger_score": round(virality_trigger_score),
        "cheapness_risk_score": cheapness_risk_score,
        "caption_box_dominance_ratio": caption_ratio,
        "blocking_issues": sorted(set(blockers)),
    }


def _mascot_usefulness_score(plan: HybridStoryPlan) -> int:
    mascot_scenes = [scene for scene in plan.scenes if scene.mascot_presence != "none"]
    if not mascot_scenes:
        return 0
    useful = 0
    for scene in mascot_scenes:
        text = " ".join([scene.visual_objective, scene.composition_notes, " ".join(scene.required_context_objects)]).lower()
        if any(term in text for term in ("point", "guide", "invoice", "object", "context", "bill", "flow", "map")):
            useful += 1
    score = 70 + round(30 * useful / len(mascot_scenes))
    if any(scene.mascot_frame_share_target > 0.35 for scene in mascot_scenes):
        score -= 25
    return max(0, min(100, score))


def _abstraction_to_concrete_score(plan: HybridStoryPlan) -> int:
    concrete_terms = {"invoice", "bill", "wallet", "tanker", "station", "port", "barrel", "map", "desk", "shipping"}
    hits = 0
    for scene in plan.scenes:
        text = " ".join([scene.media_query, scene.visual_objective, " ".join(scene.required_context_objects)]).lower()
        if any(term in text for term in concrete_terms):
            hits += 1
    return round(62 + min(38, hits * 5))


def _generic_title_card_sequence(plan: HybridStoryPlan) -> bool:
    short_abstract = 0
    for scene in plan.scenes:
        if count_words(scene.caption_text) <= 2 and len(scene.required_context_objects) <= 2:
            short_abstract += 1
    return short_abstract >= 4


def _risk_score(*signals: bool) -> int:
    return min(100, sum(24 for signal in signals if signal))


def _clamp(value: float | bool, when_true: int | None = None, when_false: int | None = None) -> float:
    if isinstance(value, bool):
        return float(when_true if value else when_false if when_false is not None else 0)
    return max(0.0, min(100.0, float(value)))


def count_words(value: str) -> int:
    return len([item for item in value.split() if item.strip()])
