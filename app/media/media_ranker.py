"""Rank media candidates for explainer Reel scenes."""

from __future__ import annotations

from app.media.media_item import MediaItem
from app.media.media_license import license_safety_score


def rank_media_items(items: list[MediaItem], query: str) -> list[MediaItem]:
    terms = {term.lower() for term in query.split() if len(term) > 2}
    ranked: list[MediaItem] = []
    for item in items:
        title_text = f"{item.title} {item.url}".lower()
        relevance = min(100, 45 + sum(12 for term in terms if term in title_text))
        vertical = _vertical_score(item.width, item.height)
        license_score = license_safety_score(item)
        clarity = 84 if item.width >= 1080 or item.height >= 1080 else 62
        trust = 90 if item.provider in {"pexels", "unsplash", "wikimedia"} else 72
        ranked.append(
            item.model_copy(
                update={
                    "relevance_score": relevance,
                    "vertical_usability_score": vertical,
                    "license_safety_score": license_score,
                    "visual_clarity_score": clarity,
                    "source_trust_score": trust,
                }
            )
        )
    return sorted(
        ranked,
        key=lambda item: (
            item.relevance_score
            + item.vertical_usability_score
            + item.license_safety_score
            + item.visual_clarity_score
            + item.source_trust_score
        ),
        reverse=True,
    )


def _vertical_score(width: int, height: int) -> int:
    if width <= 0 or height <= 0:
        return 60
    ratio = height / max(1, width)
    if ratio >= 1.35:
        return 96
    if ratio >= 0.9:
        return 78
    return 58
