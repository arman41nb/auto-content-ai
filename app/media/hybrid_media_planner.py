"""Media planning for hybrid story explainer Reels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.content.hybrid_story_schemas import HybridStoryPlan
from app.media.hybrid_media_ranker import rank_hybrid_media_items, rejection_reason
from app.media.media_downloader import download_media_item
from app.media.media_item import MediaItem
from app.media.media_license import attribution_payload
from app.media.pexels_provider import PexelsProvider
from app.media.unsplash_provider import UnsplashProvider
from app.media.visual_fallbacks import (
    AI_GENERATED_PROVIDER,
    EXTERNAL_PROVIDERS,
    PREMIUM_INFOGRAPHIC_PROVIDER,
    missing_media_api_keys,
    scene_has_real_visual,
    scene_needs_ai_generation,
)
from app.media.wikimedia_provider import WikimediaProvider
from app.render.motion_infographics import create_motion_infographic_still
from app.render.native_reel_renderer import REEL_SIZE


def create_hybrid_media_plan(
    plan: HybridStoryPlan,
    output_dir: Path,
    raw_dir: Path,
    media_sources: str = "mixed",
    prefer_video_media: bool = True,
    relevance_threshold: int = 80,
    production_visual_minimums: bool = True,
) -> dict[str, object]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    providers = [PexelsProvider(), UnsplashProvider(), WikimediaProvider()]
    allowed_sources = _parse_media_sources(media_sources)
    selected_items: list[MediaItem] = []
    scene_reports: list[dict[str, object]] = []
    candidate_payloads: list[dict[str, object]] = []
    decision_payloads: list[dict[str, object]] = []
    sources_used: list[str] = []

    for scene in plan.scenes:
        raw_path = raw_dir / f"slide_{scene.scene_number:02d}.jpg"
        candidates = _collect_candidates(scene, providers, allowed_sources, bool(prefer_video_media))
        ranked = rank_hybrid_media_items(candidates, scene)
        selected, winning_reason = _choose_media(scene, raw_path, ranked, relevance_threshold, production_visual_minimums)
        selected_items.append(selected)
        if selected.provider not in sources_used:
            sources_used.append(selected.provider)
        rejected = [
            {
                "provider": item.provider,
                "media_type": item.media_type,
                "title": item.title,
                "url": item.url,
                "reason": rejection_reason(item, selected),
                "quality_score": _quality_score(item),
                "scene_relevance_score": item.relevance_score,
                "composition_score": item.vertical_usability_score,
            }
            for item in ranked[:8]
            if item != selected
        ]
        production_ready = _production_ready(scene, selected, relevance_threshold, production_visual_minimums)
        scene_report = {
            "scene_number": scene.scene_number,
            "role": scene.role,
            "requested_visual_type": scene.visual_type,
            "visual_type": scene.visual_type,
            "media_query": scene.media_query,
            "candidates_considered": len(ranked),
            "chosen_source": selected.provider,
            "winning_reason": winning_reason,
            "rejected_reasons": rejected,
            "quality_score": _quality_score(selected),
            "scene_relevance_score": selected.relevance_score,
            "composition_score": selected.vertical_usability_score,
            "production_ready": production_ready,
            "selected": selected.model_dump(),
            "selected_media": selected.model_dump() if selected.provider in EXTERNAL_PROVIDERS and scene_has_real_visual(selected) else None,
            "generated_ai_prompt": scene.ai_scene_prompt if scene_needs_ai_generation(selected) else "",
            "generated_chart_spec": scene.ai_scene_prompt if selected.provider == PREMIUM_INFOGRAPHIC_PROVIDER else "",
            "external_media_used": selected.provider in EXTERNAL_PROVIDERS and scene_has_real_visual(selected),
            "ai_generation_required": scene_needs_ai_generation(selected),
            "mascot_presence": scene.mascot_presence,
            "mascot_frame_share_target": scene.mascot_frame_share_target,
            "required_context_objects": scene.required_context_objects,
            "warnings": _scene_warnings(scene, selected, production_ready),
        }
        scene_reports.append(scene_report)
        candidate_payloads.append(
            {
                "scene_number": scene.scene_number,
                "media_query": scene.media_query,
                "candidates": [item.model_dump() for item in ranked[:12]],
            }
        )
        decision_payloads.append(
            {
                "scene_number": scene.scene_number,
                "chosen_source": selected.provider,
                "winning_reason": winning_reason,
                "production_ready": production_ready,
                "rejected_reasons": rejected,
            }
        )

    media_plan = {
        "template": "hybrid_story_explainer",
        "topic": plan.topic,
        "scenes": scene_reports,
        "media_sources_used": sources_used,
        "external_media_used": _external_media_used(scene_reports),
        "prefer_video_media": bool(prefer_video_media),
        "production_visual_minimums": bool(production_visual_minimums),
        "missing_api_keys": missing_media_api_keys(),
    }
    _write_reports(output_dir, media_plan, candidate_payloads, decision_payloads, selected_items)
    return media_plan


def _collect_candidates(
    scene: Any,
    providers: list[Any],
    allowed_sources: set[str],
    prefer_video_media: bool,
) -> list[MediaItem]:
    if scene.visual_type not in {"real_world_broll", "hybrid_broll_overlay"}:
        return []
    candidates: list[MediaItem] = []
    for query in _expanded_queries(scene.media_query):
        for provider in providers:
            if provider.name not in allowed_sources:
                continue
            if provider.name == "pexels" and prefer_video_media:
                candidates.extend(provider.search(query, media_type="video", limit=4))
            candidates.extend(provider.search(query, limit=4))
    return candidates


def _choose_media(
    scene: Any,
    raw_path: Path,
    ranked: list[MediaItem],
    relevance_threshold: int,
    production_visual_minimums: bool,
) -> tuple[MediaItem, str]:
    if scene.visual_type == "premium_infographic":
        create_motion_infographic_still(scene, raw_path)
        return (
            MediaItem(
                provider=PREMIUM_INFOGRAPHIC_PROVIDER,
                media_type="generated_chart_spec",
                title=scene.visual_objective,
                local_path=str(raw_path),
                width=REEL_SIZE[0],
                height=REEL_SIZE[1],
                license="Generated production infographic",
                attribution="Generated in-app premium motion infographic",
                relevance_score=97,
                vertical_usability_score=100,
                license_safety_score=94,
                visual_clarity_score=92,
                source_trust_score=84,
            ),
            "premium infographic is the best visual for mechanism scene",
        )
    if scene.visual_type in {"real_world_broll", "hybrid_broll_overlay"} and ranked:
        best = ranked[0]
        downloaded = download_media_item(best, raw_path)
        if (
            scene_has_real_visual(downloaded)
            and downloaded.relevance_score >= relevance_threshold
            and downloaded.vertical_usability_score >= 75
            and downloaded.visual_clarity_score >= 75
        ):
            return downloaded, "best ranked external media with strong relevance and vertical composition"
    return _ai_generated_media_item(scene, raw_path, production_visual_minimums), _fallback_reason(scene, bool(ranked))


def _ai_generated_media_item(scene: Any, raw_path: Path, production_visual_minimums: bool) -> MediaItem:
    return MediaItem(
        provider=AI_GENERATED_PROVIDER if production_visual_minimums else "primitive_debug",
        media_type="generated_ai_prompt" if production_visual_minimums else "debug_primitive_visual",
        title=scene.ai_scene_prompt,
        local_path=str(raw_path),
        width=REEL_SIZE[0],
        height=REEL_SIZE[1],
        license="AI-generated image",
        attribution="Generated with configured AI image provider",
        relevance_score=92 if scene.mascot_presence != "none" else 88,
        vertical_usability_score=100,
        license_safety_score=84,
        visual_clarity_score=86,
        source_trust_score=74,
    )


def _production_ready(scene: Any, item: MediaItem, relevance_threshold: int, production_visual_minimums: bool) -> bool:
    if item.provider == PREMIUM_INFOGRAPHIC_PROVIDER:
        return scene_has_real_visual(item)
    if scene_needs_ai_generation(item):
        return bool(production_visual_minimums and item.relevance_score >= relevance_threshold)
    if item.provider in EXTERNAL_PROVIDERS:
        return (
            scene_has_real_visual(item)
            and item.relevance_score >= relevance_threshold
            and item.vertical_usability_score >= 75
            and item.visual_clarity_score >= 75
            and item.license_safety_score >= 70
        )
    return False


def _scene_warnings(scene: Any, item: MediaItem, production_ready: bool) -> list[str]:
    warnings: list[str] = []
    if not production_ready:
        warnings.append("scene is not production-ready")
    if scene_needs_ai_generation(item):
        warnings.append("AI image generation is required before final render")
    if item.provider in EXTERNAL_PROVIDERS and not scene_has_real_visual(item):
        warnings.append("external candidate was selected but file is missing")
    if scene.mascot_presence != "none" and scene.mascot_frame_share_target > 0.35:
        warnings.append("mascot frame share is high")
    return warnings


def _fallback_reason(scene: Any, had_candidates: bool) -> str:
    if scene.visual_type in {"mascot_context_scene", "mascot_small_overlay", "takeaway_scene", "ai_realistic_scene"}:
        return "AI realistic/contextual scene is the preferred visual for this scene"
    if had_candidates:
        return "external media candidates were weaker than production threshold, AI scene scheduled"
    return "no suitable external media found, AI scene scheduled"


def _quality_score(item: MediaItem) -> int:
    return round(
        item.relevance_score * 0.34
        + item.vertical_usability_score * 0.22
        + item.visual_clarity_score * 0.22
        + item.license_safety_score * 0.12
        + item.source_trust_score * 0.10
    )


def _external_media_used(scene_reports: list[dict[str, object]]) -> bool:
    for scene in scene_reports:
        selected = scene.get("selected", {})
        if not isinstance(selected, dict):
            continue
        path = Path(str(selected.get("local_path", "")))
        if selected.get("provider") in EXTERNAL_PROVIDERS and path.exists() and path.stat().st_size > 0:
            return True
    return False


def _parse_media_sources(value: str) -> set[str]:
    normalized = {item.strip().lower() for item in str(value or "mixed").split(",") if item.strip()}
    if not normalized or "auto" in normalized or "mixed" in normalized:
        return {"pexels", "unsplash", "wikimedia"}
    if "ai" in normalized:
        return set()
    return normalized & {"pexels", "unsplash", "wikimedia"}


def _expanded_queries(query: str) -> list[str]:
    base = [query]
    lower = query.lower()
    if any(term in lower for term in ("oil", "fuel", "dollar", "currency", "trade", "import", "export")):
        base.extend(
            [
                "fuel tanker gas station vertical",
                "oil tanker export terminal vertical",
                "shipping port oil trade vertical",
                "currency exchange market vertical",
                "logistics fuel cost vertical",
            ]
        )
    result: list[str] = []
    seen: set[str] = set()
    for item in base:
        clean = " ".join(str(item).split())
        key = clean.lower()
        if clean and key not in seen:
            result.append(clean)
            seen.add(key)
    return result


def _write_reports(
    output_dir: Path,
    media_plan: dict[str, object],
    candidate_payloads: list[dict[str, object]],
    decision_payloads: list[dict[str, object]],
    selected_items: list[MediaItem],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "media_plan.json").write_text(json.dumps(media_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "media_candidates.json").write_text(
        json.dumps({"template": "hybrid_story_explainer", "scenes": candidate_payloads}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "media_decision_report.json").write_text(
        json.dumps({"template": "hybrid_story_explainer", "scenes": decision_payloads}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "media_selection_report.json").write_text(
        json.dumps(
            {
                "ranker": "hybrid_weighted_relevance_composition_license_quality",
                "scenes": media_plan.get("scenes", []),
                "warnings": [
                    warning
                    for scene in media_plan.get("scenes", [])
                    if isinstance(scene, dict)
                    for warning in scene.get("warnings", [])
                    if isinstance(warning, str)
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "media_attribution.json").write_text(
        json.dumps(attribution_payload(selected_items), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    external_files = []
    for item in selected_items:
        path = Path(item.local_path) if item.local_path else Path()
        if item.provider in EXTERNAL_PROVIDERS and path.exists():
            external_files.append(str(path))
    (output_dir / "media_quality_report.json").write_text(
        json.dumps(
            {
                "production_visual_minimums": bool(media_plan.get("production_visual_minimums", False)),
                "external_media_used": bool(media_plan.get("external_media_used", False)),
                "external_media_files_used": external_files,
                "external_media_used_flag_truthful": bool(media_plan.get("external_media_used", False)) == bool(external_files),
                "ai_generation_required_scene_numbers": [
                    int(scene.get("scene_number", 0) or 0)
                    for scene in media_plan.get("scenes", [])
                    if isinstance(scene, dict) and bool(scene.get("ai_generation_required", False))
                ],
                "not_production_ready_scene_numbers": [
                    int(scene.get("scene_number", 0) or 0)
                    for scene in media_plan.get("scenes", [])
                    if isinstance(scene, dict) and not bool(scene.get("production_ready", False))
                ],
                "all_scenes_have_visual_plan": True,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
