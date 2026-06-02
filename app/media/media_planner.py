"""Create per-scene media plans for explainer Reels."""

from __future__ import annotations

import json
from pathlib import Path

from app.content.explainer_schemas import ExplainerPlan
from app.media.ai_provider_adapter import ai_media_item
from app.media.media_downloader import create_fallback_visual, download_media_item
from app.media.media_item import MediaItem
from app.media.media_license import attribution_payload
from app.media.media_ranker import rank_media_items
from app.media.pexels_provider import PexelsProvider
from app.media.unsplash_provider import UnsplashProvider
from app.media.wikimedia_provider import WikimediaProvider
from app.render.simple_charts import create_chart_for_scene


def create_media_plan(plan: ExplainerPlan, output_dir: Path, raw_dir: Path) -> dict[str, object]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    providers = [PexelsProvider(), UnsplashProvider(), WikimediaProvider()]
    scene_reports: list[dict[str, object]] = []
    selected_items: list[MediaItem] = []
    sources_used: list[str] = []

    for scene in plan.scenes:
        raw_path = raw_dir / f"slide_{scene.scene_number:02d}.jpg"
        candidates: list[MediaItem] = []
        selected: MediaItem
        if scene.visual_type == "generated_chart":
            create_chart_for_scene(scene, raw_path)
            selected = MediaItem(
                provider="chart",
                media_type="generated_chart",
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
        elif scene.visual_type in {"host_ai", "ai_image", "simple_motion_graphic"}:
            selected = ai_media_item(scene.visual_goal)
        else:
            for provider in providers:
                candidates.extend(provider.search(scene.media_query, limit=4))
            if not candidates and "oil" in scene.media_query.lower():
                wikimedia = WikimediaProvider()
                for fallback_query in ("oil tanker", "oil barrels", "crude oil tanker"):
                    candidates.extend(wikimedia.search(fallback_query, limit=4))
                    if candidates:
                        break
            ranked = rank_media_items(candidates, scene.media_query)
            if ranked:
                selected = download_media_item(ranked[0], raw_path)
                if not selected.local_path:
                    create_fallback_visual(raw_path, scene.visual_goal, scene.role)
                    selected = selected.model_copy(update={"local_path": str(raw_path), "visual_clarity_score": 55})
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
                "external_media_used": selected.provider in {"pexels", "unsplash", "wikimedia"},
                "warnings": _scene_warnings(selected),
            }
        )

    media_plan = {
        "template": "explainer_host_reel",
        "topic": plan.topic,
        "scenes": scene_reports,
        "media_sources_used": sources_used,
        "external_media_used": any(source in {"pexels", "unsplash", "wikimedia"} for source in sources_used),
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
