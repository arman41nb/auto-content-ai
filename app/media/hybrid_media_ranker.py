"""Hybrid story media ranking helpers."""

from __future__ import annotations

from typing import Any

from app.media.media_item import MediaItem
from app.media.media_license import license_safety_score


CONTEXT_TERMS = {
    "oil",
    "fuel",
    "tanker",
    "barrel",
    "refinery",
    "gas",
    "station",
    "invoice",
    "importer",
    "export",
    "shipping",
    "currency",
    "dollar",
    "market",
    "trade",
    "port",
}


def rank_hybrid_media_items(items: list[MediaItem], scene: Any) -> list[MediaItem]:
    ranked = [score_hybrid_media_item(item, scene) for item in items]
    return sorted(
        ranked,
        key=lambda item: (
            item.relevance_score * 1.4
            + item.vertical_usability_score
            + item.visual_clarity_score
            + item.license_safety_score
            + item.source_trust_score
        ),
        reverse=True,
    )


def score_hybrid_media_item(item: MediaItem, scene: Any) -> MediaItem:
    query = str(getattr(scene, "media_query", "") or "")
    required = " ".join(str(value) for value in getattr(scene, "required_context_objects", []) if str(value).strip())
    terms = {term.lower() for term in f"{query} {required}".split() if len(term) > 2}
    title_text = f"{item.title} {item.url}".lower()
    overlap = sum(1 for term in terms if term in title_text)
    relevance = min(100, 44 + overlap * 10)
    if any(term in title_text for term in CONTEXT_TERMS):
        relevance = min(100, relevance + 16)
    if str(getattr(scene, "visual_type", "")) in {"real_world_broll", "hybrid_broll_overlay"}:
        relevance = min(100, relevance + 5)

    vertical = _vertical_score(item.width, item.height)
    clarity = 90 if item.width >= 1080 and item.height >= 1280 else 84 if item.height >= 1080 else 60
    if item.media_type == "stock_video":
        clarity = min(96, clarity + 4)
        vertical = min(100, vertical + 3)
    trust = 92 if item.provider in {"pexels", "unsplash", "wikimedia"} else 70
    return item.model_copy(
        update={
            "relevance_score": relevance,
            "vertical_usability_score": vertical,
            "license_safety_score": license_safety_score(item),
            "visual_clarity_score": clarity,
            "source_trust_score": trust,
        }
    )


def rejection_reason(item: MediaItem, winner: MediaItem | None = None) -> str:
    if winner is not None and item == winner:
        return "selected"
    reasons: list[str] = []
    if item.relevance_score < 80:
        reasons.append(f"scene relevance {item.relevance_score} below 80")
    if item.vertical_usability_score < 75:
        reasons.append(f"vertical crop score {item.vertical_usability_score} below 75")
    if item.visual_clarity_score < 75:
        reasons.append(f"visual clarity {item.visual_clarity_score} below 75")
    if item.license_safety_score < 70:
        reasons.append("license metadata is weak")
    return "; ".join(reasons) if reasons else "lower combined rank than selected media"


def _vertical_score(width: int, height: int) -> int:
    if width <= 0 or height <= 0:
        return 62
    ratio = height / max(1, width)
    if ratio >= 1.55:
        return 100
    if ratio >= 1.25:
        return 94
    if ratio >= 0.9:
        return 78
    return 58
