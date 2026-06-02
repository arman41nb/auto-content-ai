"""Media license helpers."""

from __future__ import annotations

from app.media.media_item import MediaItem


SAFE_LICENSE_TERMS = ("public domain", "cc0", "creative commons", "unsplash", "pexels")


def license_safety_score(item: MediaItem) -> int:
    text = f"{item.license} {item.license_url} {item.provider}".lower()
    if any(term in text for term in SAFE_LICENSE_TERMS):
        return 92
    if item.attribution:
        return 72
    return 35


def attribution_payload(items: list[MediaItem]) -> dict[str, object]:
    external = [item for item in items if item.provider in {"pexels", "unsplash", "wikimedia"} and item.local_path]
    return {
        "external_media_used": bool(external),
        "items": [item.model_dump() for item in items],
        "missing_attribution_count": sum(1 for item in external if not item.attribution and not item.author),
    }
