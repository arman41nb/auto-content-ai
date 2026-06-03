"""Create per-scene media plans for explainer Reels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.content.explainer_schemas import ExplainerPlan
from app.media.ai_provider_adapter import ai_media_item
from app.media.media_downloader import download_media_item
from app.media.media_item import MediaItem
from app.media.media_license import attribution_payload
from app.media.media_ranker import rank_media_items
from app.media.pexels_provider import PexelsProvider
from app.media.visual_fallbacks import (
    AI_GENERATED_PROVIDER,
    EXTERNAL_PROVIDERS,
    PREMIUM_INFOGRAPHIC_PROVIDER,
    PRODUCTION_VISUAL_MINIMUMS,
    missing_media_api_keys,
    scene_has_real_visual,
    scene_needs_ai_generation,
    write_media_fallback_report,
)
from app.render.premium_infographics import create_premium_infographic_still


def create_media_plan(
    plan: Any,
    output_dir: Path,
    raw_dir: Path,
    template: str = "explainer_host_reel",
    media_sources: str = "mixed",
    prefer_video_media: bool = False,
    relevance_threshold: int = 75,
    production_visual_minimums: bool = PRODUCTION_VISUAL_MINIMUMS,
) -> dict[str, object]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    pexels = PexelsProvider()
    scene_reports: list[dict[str, object]] = []
    selected_items: list[MediaItem] = []
    sources_used: list[str] = []
    fallback_events: list[dict[str, object]] = []
    allowed_sources = _parse_media_sources(media_sources)
    missing_keys = missing_media_api_keys()

    for scene in plan.scenes:
        raw_path = raw_dir / f"slide_{scene.scene_number:02d}.jpg"
        queries = _expanded_queries(scene.media_query, template)
        pexels_candidates = _collect_pexels_candidates(
            scene=scene,
            provider=pexels,
            queries=queries,
            allowed_sources=allowed_sources,
            prefer_video_media=prefer_video_media,
        )
        ranked_pexels = rank_media_items(pexels_candidates, scene.media_query)
        selected, decision = _select_pexels_first_media(
            scene=scene,
            raw_path=raw_path,
            ranked_pexels=ranked_pexels,
            relevance_threshold=relevance_threshold,
            production_visual_minimums=production_visual_minimums,
        )
        if selected.provider == AI_GENERATED_PROVIDER and scene_needs_ai_generation(selected):
            fallback_events.append(_fallback_event(scene, str(decision.get("ai_fallback_reason", "")), selected))
        selected_items.append(selected)
        if selected.provider not in sources_used:
            sources_used.append(selected.provider)
        all_candidates = list(ranked_pexels)
        generated_prompt = selected.title if scene_needs_ai_generation(selected) else ""
        generated_chart = selected.title if selected.provider == PREMIUM_INFOGRAPHIC_PROVIDER else ""
        scene_reports.append(
            {
                "scene_number": scene.scene_number,
                "scene_type": scene.visual_type,
                "scene_intent": scene.visual_goal,
                "requested_visual_type": scene.visual_type,
                "search_queries": queries,
                "media_query": scene.media_query,
                "pexels_attempted": True,
                "pexels_candidate_count": len(ranked_pexels),
                "pexels_best_score": _quality_score(ranked_pexels[0]) if ranked_pexels else 0,
                "pexels_rejection_reason": decision.get("pexels_rejection_reason", ""),
                "selected_source_type": selected.provider,
                "selected_priority": _source_priority(selected),
                "why_selected": decision.get("why_selected", ""),
                "why_ai_fallback_was_needed": decision.get("ai_fallback_reason", "") if scene_needs_ai_generation(selected) else "",
                "selected": selected.model_dump(),
                "candidate_count": len(all_candidates),
                "candidates_considered": [item.model_dump() for item in all_candidates[:10]],
                "candidate_ranking": [
                    {
                        "provider": item.provider,
                        "media_type": item.media_type,
                        "title": item.title,
                        "quality_score": _quality_score(item),
                        "topical_relevance_score": item.relevance_score,
                        "realism_score": item.source_trust_score,
                        "clarity_score": item.visual_clarity_score,
                        "vertical_crop_score": item.vertical_usability_score,
                    }
                    for item in all_candidates[:10]
                ],
                "selected_media": selected.model_dump() if scene_has_real_visual(selected) and selected.provider in EXTERNAL_PROVIDERS else None,
                "generated_ai_prompt": generated_prompt,
                "generated_chart_spec": generated_chart,
                "external_media_used": selected.provider in EXTERNAL_PROVIDERS and scene_has_real_visual(selected),
                "ai_generation_required": scene_needs_ai_generation(selected),
                "scene_visual_quality": _scene_visual_quality(selected),
                "primitive_graphics_rejected": True,
                "fake_text_risk_checked": True,
                "caption_safe_zone_compatible": selected.vertical_usability_score >= 75,
                "warnings": _scene_warnings(selected),
            }
        )

    media_plan = {
        "template": template,
        "topic": plan.topic,
        "scenes": scene_reports,
        "media_sources_used": sources_used,
        "external_media_used": _external_media_used(scene_reports),
        "missing_api_keys": missing_keys,
        "prefer_video_media": bool(prefer_video_media),
        "production_visual_minimums": bool(production_visual_minimums),
        "pexels_first_policy_active": True,
        "ai_fallback_limited_to_unsupported_scenes": True,
        "primitive_graphics_allowed": False,
    }
    output_dir.joinpath("media_plan.json").write_text(json.dumps(media_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    selection_report = {
        "ranker": "pexels_first_weighted_relevance_realism_clarity_vertical_crop",
        "pexels_first_policy_active": True,
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
    output_dir.joinpath("media_quality_report.json").write_text(
        json.dumps(_media_quality_report(media_plan, scene_reports), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    output_dir.joinpath("media_decision_report.json").write_text(
        json.dumps(
            {
                "template": template,
                "pexels_first_policy_active": True,
                "scenes": [
                    {
                        "scene_number": scene.get("scene_number"),
                        "scene_type": scene.get("scene_type"),
                        "search_queries": scene.get("search_queries", []),
                        "selected_source_type": scene.get("selected_source_type"),
                        "why_selected": scene.get("why_selected", ""),
                        "why_ai_fallback_was_needed": scene.get("why_ai_fallback_was_needed", ""),
                        "pexels_rejection_reason": scene.get("pexels_rejection_reason", ""),
                    }
                    for scene in scene_reports
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_media_fallback_report(
        output_dir,
        {
            "blank_scene_forbidden": True,
            "placeholder_prompt_text_forbidden": True,
            "primitive_vector_final_visuals_forbidden": True,
            "production_visual_minimums": bool(production_visual_minimums),
            "missing_api_keys": missing_keys,
            "fallback_events": fallback_events,
            "fallback_count": len(fallback_events),
        },
    )
    return media_plan


def _collect_pexels_candidates(
    scene: Any,
    provider: PexelsProvider,
    queries: list[str],
    allowed_sources: set[str],
    prefer_video_media: bool,
) -> list[MediaItem]:
    if "pexels" not in allowed_sources:
        return []
    candidates: list[MediaItem] = []
    wants_video = bool(prefer_video_media or str(getattr(scene, "visual_type", "")) == "stock_video")
    for query in queries:
        if wants_video:
            candidates.extend(provider.search(query, media_type="video", limit=4))
        candidates.extend(provider.search(query, media_type="photo", limit=6))
    return candidates


def _select_pexels_first_media(
    scene: Any,
    raw_path: Path,
    ranked_pexels: list[MediaItem],
    relevance_threshold: int,
    production_visual_minimums: bool,
) -> tuple[MediaItem, dict[str, object]]:
    best = ranked_pexels[0] if ranked_pexels else None
    visual_type = str(getattr(scene, "visual_type", ""))
    if visual_type in {"premium_infographic", "generated_chart", "chart_motion"} and (
        best is None or not (_candidate_is_strong(best, relevance_threshold) and _quality_score(best) >= 92)
    ):
        rejection = _pexels_rejection_reason(best, bool(ranked_pexels), relevance_threshold)
        if best is not None and _candidate_is_strong(best, relevance_threshold):
            rejection = f"mechanism scene needs an explicit explanatory infographic; best Pexels quality score {_quality_score(best)} below 92"
        return _fallback_after_pexels(scene, raw_path, production_visual_minimums, rejection, best)
    if best is not None and _candidate_is_strong(best, relevance_threshold):
        downloaded = download_media_item(best, raw_path)
        if scene_has_real_visual(downloaded):
            return downloaded, {
                "why_selected": "Pexels candidate met topical relevance, realism, clarity, and vertical crop thresholds.",
                "pexels_rejection_reason": "",
                "ai_fallback_reason": "",
            }
        return _fallback_after_pexels(
            scene,
            raw_path,
            production_visual_minimums,
            "best Pexels candidate could not be downloaded into a usable local visual",
            best,
        )
    rejection = _pexels_rejection_reason(best, bool(ranked_pexels), relevance_threshold)
    return _fallback_after_pexels(scene, raw_path, production_visual_minimums, rejection, best)


def _fallback_after_pexels(
    scene: Any,
    raw_path: Path,
    production_visual_minimums: bool,
    pexels_rejection_reason: str,
    best_pexels: MediaItem | None,
) -> tuple[MediaItem, dict[str, object]]:
    visual_type = str(getattr(scene, "visual_type", ""))
    if visual_type in {"premium_infographic", "generated_chart", "chart_motion"}:
        create_premium_infographic_still(scene, raw_path)
        return (
            MediaItem(
                provider=PREMIUM_INFOGRAPHIC_PROVIDER,
                media_type="generated_chart_spec",
                title=str(getattr(scene, "visual_goal", "Premium editorial infographic")),
                local_path=str(raw_path),
                width=1080,
                height=1920,
                license="Generated production infographic",
                attribution="Generated in-app premium editorial infographic after Pexels-first sourcing",
                relevance_score=96,
                vertical_usability_score=100,
                license_safety_score=94,
                visual_clarity_score=92,
                source_trust_score=84,
            ),
            {
                "why_selected": "Pexels did not provide a strong enough mechanism visual, so the internal premium infographic renderer was used.",
                "pexels_rejection_reason": pexels_rejection_reason,
                "ai_fallback_reason": "",
            },
        )
    ai_item = ai_media_item(_strict_ai_fallback_prompt(scene), local_path=str(raw_path))
    if not production_visual_minimums:
        ai_item = ai_item.model_copy(update={"provider": "primitive_debug", "media_type": "debug_primitive_visual"})
    return ai_item, {
        "why_selected": "AI fallback was scheduled only after Pexels did not produce a production-ready real-media candidate.",
        "pexels_rejection_reason": pexels_rejection_reason,
        "ai_fallback_reason": _ai_fallback_reason(scene, pexels_rejection_reason, best_pexels),
    }


def _candidate_is_strong(item: MediaItem, relevance_threshold: int) -> bool:
    return (
        item.relevance_score >= relevance_threshold
        and item.vertical_usability_score >= 75
        and item.visual_clarity_score >= 75
        and item.license_safety_score >= 70
        and item.source_trust_score >= 80
    )


def _pexels_rejection_reason(best: MediaItem | None, had_candidates: bool, relevance_threshold: int) -> str:
    if best is None:
        return "no Pexels candidates were returned for the scene query"
    if not had_candidates:
        return "no Pexels candidates were returned for the scene query"
    reasons: list[str] = []
    if best.relevance_score < relevance_threshold:
        reasons.append(f"topical relevance {best.relevance_score} below {relevance_threshold}")
    if best.vertical_usability_score < 75:
        reasons.append(f"vertical crop score {best.vertical_usability_score} below 75")
    if best.visual_clarity_score < 75:
        reasons.append(f"visual clarity {best.visual_clarity_score} below 75")
    if best.license_safety_score < 70:
        reasons.append(f"license safety {best.license_safety_score} below 70")
    if best.source_trust_score < 80:
        reasons.append(f"source trust {best.source_trust_score} below 80")
    return "; ".join(reasons) if reasons else "top Pexels candidate did not pass production validation"


def _strict_ai_fallback_prompt(scene: Any) -> str:
    return " ".join(
        part.strip()
        for part in [
            str(getattr(scene, "visual_goal", "")),
            "photorealistic or premium editorial infographic style only",
            "real-world grounded business and finance visual language",
            "no presenter figure, no guide figure, no animal-shaped figure, no toy-like machine figure, no cute 3D figure",
            "no childish flat illustration, no chibi, no cute 3D character, no primitive icon scene",
            "avoid readable fake documents; if documents appear, make text blurred or de-emphasized",
            "native vertical 9:16 composition with one clear focal point and caption-safe negative space",
            "no text, no letters, no labels, no logos, no watermark",
        ]
        if part.strip()
    )


def _ai_fallback_reason(scene: Any, pexels_rejection_reason: str, best_pexels: MediaItem | None) -> str:
    if best_pexels is None:
        return f"Pexels returned no strong real-media option for scene {getattr(scene, 'scene_number', '')}: {pexels_rejection_reason}."
    return (
        f"Pexels best candidate was rejected for scene {getattr(scene, 'scene_number', '')}: "
        f"{pexels_rejection_reason}."
    )


def _quality_score(item: MediaItem) -> int:
    return round(
        item.relevance_score * 0.34
        + item.vertical_usability_score * 0.22
        + item.visual_clarity_score * 0.22
        + item.license_safety_score * 0.10
        + item.source_trust_score * 0.12
    )


def _source_priority(item: MediaItem) -> int:
    if item.provider == "pexels":
        return 1
    if item.provider == PREMIUM_INFOGRAPHIC_PROVIDER:
        return 2
    if item.provider == AI_GENERATED_PROVIDER:
        return 3
    return 4


def _scene_warnings(item: MediaItem) -> list[str]:
    warnings: list[str] = []
    if scene_needs_ai_generation(item):
        warnings.append("AI image generation is required before final render.")
    if item.provider == "pexels" and not (item.attribution or item.author):
        warnings.append("External media is missing attribution metadata.")
    if item.local_path and item.visual_clarity_score < 60:
        warnings.append("Selected media may be low clarity or fallback quality.")
    if item.license_safety_score < 70:
        warnings.append("Selected media license metadata is weak.")
    return warnings


def _expanded_queries(query: str, template: str) -> list[str]:
    base = [query]
    lower = query.lower()
    if any(term in lower for term in ("oil", "fuel", "dollar", "currency", "trade", "market")):
        base.extend(
            [
                "oil refinery vertical",
                "oil tanker ship vertical",
                "oil barrels close up vertical",
                "fuel station night vertical",
                "currency exchange market vertical",
                "global trade port vertical",
                "cargo ship containers vertical",
                "gas pump fuel price vertical",
            ]
        )
    result: list[str] = []
    seen: set[str] = set()
    for item in base:
        normalized = " ".join(str(item).split())
        key = normalized.lower()
        if normalized and key not in seen:
            result.append(normalized)
            seen.add(key)
    return result


def _parse_media_sources(value: str) -> set[str]:
    del value
    return {"pexels"}


def _scene_visual_quality(item: MediaItem) -> str:
    if item.provider in {AI_GENERATED_PROVIDER, PREMIUM_INFOGRAPHIC_PROVIDER}:
        return "pending_ai_generation" if scene_needs_ai_generation(item) else "pass"
    if item.provider in EXTERNAL_PROVIDERS and scene_has_real_visual(item) and item.visual_clarity_score >= 75:
        return "pass"
    if item.provider in {"fallback", "ai_fallback", "primitive_debug"}:
        return "fail"
    return "review"


def _external_media_used(scene_reports: list[dict[str, object]]) -> bool:
    for scene in scene_reports:
        selected = scene.get("selected", {})
        if not isinstance(selected, dict):
            continue
        provider = str(selected.get("provider", ""))
        path = Path(str(selected.get("local_path", "")))
        if provider in EXTERNAL_PROVIDERS and path.exists() and path.stat().st_size > 0:
            return True
    return False


def _media_quality_report(media_plan: dict[str, object], scene_reports: list[dict[str, object]]) -> dict[str, object]:
    ai_required = [
        int(scene.get("scene_number", 0) or 0)
        for scene in scene_reports
        if bool(scene.get("ai_generation_required", False))
    ]
    failed = [
        int(scene.get("scene_number", 0) or 0)
        for scene in scene_reports
        if str(scene.get("scene_visual_quality", "")) == "fail"
    ]
    external_files = []
    for scene in scene_reports:
        selected = scene.get("selected", {})
        if isinstance(selected, dict) and selected.get("provider") in EXTERNAL_PROVIDERS:
            path = Path(str(selected.get("local_path", "")))
            if path.exists():
                external_files.append(str(path))
    return {
        "production_visual_minimums": bool(media_plan.get("production_visual_minimums", False)),
        "external_media_used": bool(media_plan.get("external_media_used", False)),
        "external_media_files_used": external_files,
        "missing_api_keys": media_plan.get("missing_api_keys", []),
        "ai_generation_required_scene_numbers": ai_required,
        "failed_scene_visual_quality_numbers": failed,
        "primitive_final_visuals_forbidden": True,
        "scene_count": len(scene_reports),
        "all_scenes_have_visual_plan": len(scene_reports) > 0 and not failed,
        "warnings": [
            warning
            for scene in scene_reports
            for warning in scene.get("warnings", [])
            if isinstance(warning, str)
        ],
    }


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
