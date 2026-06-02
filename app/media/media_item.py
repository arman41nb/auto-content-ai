"""Normalized media item metadata."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class MediaItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    media_type: str
    title: str = ""
    url: str = ""
    download_url: str = ""
    local_path: str = ""
    width: int = 0
    height: int = 0
    author: str = ""
    author_url: str = ""
    license: str = ""
    license_url: str = ""
    attribution: str = ""
    relevance_score: int = 0
    vertical_usability_score: int = 0
    license_safety_score: int = 0
    visual_clarity_score: int = 0
    source_trust_score: int = 0
