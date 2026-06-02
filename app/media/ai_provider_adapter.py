"""AI media provider adapter metadata."""

from __future__ import annotations

from app.media.media_item import MediaItem


def ai_media_item(title: str, local_path: str = "") -> MediaItem:
    return MediaItem(
        provider="ai",
        media_type="ai_image",
        title=title,
        local_path=local_path,
        license="AI-generated image",
        attribution="Generated with configured AI image provider",
        relevance_score=86,
        vertical_usability_score=92,
        license_safety_score=80,
        visual_clarity_score=78,
        source_trust_score=70,
    )
