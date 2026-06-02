"""Create per-scene media plans for explainer Reels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.content.explainer_schemas import ExplainerPlan
from app.media.ai_provider_adapter import ai_media_item
from app.media.media_downloader import create_fallback_visual, download_media_item
from app.media.media_item import MediaItem
from app.media.media_license import attribution_payload
from app.media.media_ranker import rank_media_items
from app.media.pexels_provider import PexelsProvider
from app.media.unsplash_provider import UnsplashProvider
from app.media.visual_fallbacks import (
    EXTERNAL_PROVIDERS,
    create_scene_fallback,
    missing_media_api_keys,
    scene_has_real_visual,
    visual_quality_warnings,
    write_media_fallback_report,
)
from app.media.wikimedia_provider import WikimediaProvider
from app.render.simple_charts import create_chart_for_scene


def create_media_plan(
    plan: Any,
    output_dir: Path,
    raw_dir: Path,
    template: str = "explainer_host_reel",
    mascot: Any | None = None,
    media_sources: str = "mixed",
    prefer_video_media: bool = False,
    relevance_threshold: int = 80,
) -> dict[str, object]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    providers = [PexelsProvider(), UnsplashProvider(), WikimediaProvider()]
    scene_reports: list[dict[str, object]] = []
    selected_items: list[MediaItem] = []
    sources_used: list[str] = []
    fallback_events: list[dict[str, object]] = []
    allowed_sources = _parse_media_sources(media_sources)
    missing_keys = missing_media_api_keys()

    for scene in plan.scenes:
        raw_path = raw_dir / f"slide_{scene.scene_number:02d}.jpg"
        candidates: list[MediaItem] = []
        selected: MediaItem
        if scene.visual_type == "generated_chart":
            create_chart_for_scene(scene, raw_path)
            selected = MediaItem(
                provider="chart",
                media_type="generated_chart_spec",
                title=scene.visual_goal,
                local_path=str(raw_path),
                license="Generated chart",
                attribution="Generated in-app chart",
                relevance_score=96,
                vertical_usability_score=100,
                license_safety_score=100,
                visual_clarity_score=94,
                source_trust_score=86,
            )
        elif scene.visual_type == "chart_motion":
            selected = create_scene_fallback(scene, raw_path, mascot=mascot)
        elif scene.visual_type in {"mascot_ai", "object_scene_ai", "mixed"}:
            selected = create_scene_fallback(scene, raw_path, mascot=mascot)
            fallback_events.append(_fallback_event(scene, "generated local AI-style fallback visual", selected))
        elif scene.visual_type in {"host_ai", "ai_image", "simple_motion_graphic"} and template != "mascot_story_explainer":
            selected = ai_media_item(scene.visual_goal)
        else:
            for provider in providers:
                if provider.name not in allowed_sources:
                    continue
                if provider.name == "pexels" and prefer_video_media:
                    candidates.extend(provider.search(scene.media_query, media_type="video", limit=4))
                candidates.extend(provider.search(scene.media_query, limit=4))
            if not candidates and "oil" in scene.media_query.lower():
                wikimedia = WikimediaProvider()
                for fallback_query in ("oil tanker", "oil barrels", "crude oil tanker"):
                    if "wikimedia" in allowed_sources:
                        candidates.extend(wikimedia.search(fallback_query, limit=4))
                    if candidates:
                        break
            ranked = rank_media_items(candidates, scene.media_query)
            if ranked:
                selected = download_media_item(ranked[0], raw_path)
                warnings = (
                    visual_quality_warnings(selected, relevance_threshold=relevance_threshold)
                    if template == "mascot_story_explainer"
                    else (["Scene visual file is missing; fallback required."] if not scene_has_real_visual(selected) else [])
                )
                if warnings:
                    fallback = create_scene_fallback(scene, raw_path, mascot=mascot)
                    fallback_events.append(_fallback_event(scene, "; ".join(warnings), fallback, original=selected))
                    selected = fallback
            else:
                if template == "mascot_story_explainer":
                    selected = create_scene_fallback(scene, raw_path, mascot=mascot)
                    fallback_events.append(_fallback_event(scene, "no suitable external media found", selected))
                else:
                    create_fallback_visual(raw_path, scene.visual_goal, scene.role)
                    selected = MediaItem(
                        provider="fallback",
                        media_type=scene.visual_type,
                        title=scene.visual_goal,
                        local_path=str(raw_path),
                        license="Generated fallback visual",
                        attribution="Generated fallback because external provider was unavailable",
                        relevance_score=62,
                        vertical_usability_score=100,
                        license_safety_score=70,
                        visual_clarity_score=58,
                        source_trust_score=45,
                    )
        if template == "mascot_story_explainer" and not scene_has_real_visual(selected):
            fallback = create_scene_fallback(scene, raw_path, mascot=mascot)
            fallback_events.append(_fallback_event(scene, "selected media had no local visual file", fallback, original=selected))
            selected = fallback
        selected_items.append(selected)
        if selected.provider not in sources_used:
            sources_used.append(selected.provider)
        scene_reports.append(
            {
                "scene_number": scene.scene_number,
                "requested_visual_type": scene.visual_type,
                "media_query": scene.media_query,
                "selected": selected.model_dump(),
                "candidate_count": len(candidates),
                "selected_media": selected.model_dump() if scene_has_real_visual(selected) and selected.provider in EXTERNAL_PROVIDERS else None,
                "generated_ai_prompt": getattr(scene, "visual_goal", "") if selected.media_type == "generated_ai_prompt" else "",
                "generated_chart_spec": getattr(scene, "visual_goal", "") if selected.media_type == "generated_chart_spec" else "",
                "external_media_used": selected.provider in EXTERNAL_PROVIDERS and scene_has_real_visual(selected),
                "warnings": _scene_warnings(selected),
            }
        )

    media_plan = {
        "template": template,
        "topic": plan.topic,
        "scenes": scene_reports,
        "media_sources_used": sources_used,
        "external_media_used": any(
            source in EXTERNAL_PROVIDERS and any(
                isinstance(scene.get("selected"), dict) and scene["selected"].get("provider") == source and scene["selected"].get("local_path")
                for scene in scene_reports
            )
            for source in sources_used
        ),
        "missing_api_keys": missing_keys,
        "prefer_video_media": bool(prefer_video_media),
    }
    output_dir.joinpath("media_plan.json").write_text(json.dumps(media_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    selection_report = {
        "ranker": "deterministic_weighted_relevance_license_vertical_clarity",
        "scenes": scene_reports,
        "warnings": [warning for scene in scene_reports for warning in scene.get("warnings", []) if isinstance(warning, str)],
    }
    output_dir.joinpath("media_selection_report.json").write_text(
        json.dumps(selection_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    output_dir.joinpath("media_attribution.json").write_text(
        json.dumps(attribution_payload(selected_items), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if template == "mascot_story_explainer":
        write_media_fallback_report(
            output_dir,
            {
                "blank_scene_forbidden": True,
                "placeholder_prompt_text_forbidden": True,
                "missing_api_keys": missing_keys,
                "fallback_events": fallback_events,
                "fallback_count": len(fallback_events),
            },
        )
    return media_plan


def _scene_warnings(item: MediaItem) -> list[str]:
    warnings: list[str] = []
    if item.provider in {"pexels", "unsplash", "wikimedia"} and not (item.attribution or item.author):
        warnings.append("External media is missing attribution metadata.")
    if item.local_path and item.visual_clarity_score < 60:
        warnings.append("Selected media may be low clarity or fallback quality.")
    if item.license_safety_score < 70:
        warnings.append("Selected media license metadata is weak.")
    return warnings


def _parse_media_sources(value: str) -> set[str]:
    normalized = {item.strip().lower() for item in str(value or "mixed").split(",") if item.strip()}
    if not normalized or "auto" in normalized or "mixed" in normalized:
        return {"pexels", "unsplash", "wikimedia"}
    if "ai" in normalized:
        return set()
    return normalized & {"pexels", "unsplash", "wikimedia"}


def _fallback_event(scene: Any, reason: str, fallback: MediaItem, original: MediaItem | None = None) -> dict[str, object]:
    return {
        "scene_number": int(getattr(scene, "scene_number", 0) or 0),
        "reason": reason,
        "fallback_provider": fallback.provider,
        "fallback_media_type": fallback.media_type,
        "fallback_path": fallback.local_path,
        "original_provider": original.provider if original else "",
        "original_media_type": original.media_type if original else "",
        "original_path": original.local_path if original else "",
    }
