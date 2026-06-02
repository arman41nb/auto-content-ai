"""Pexels media provider."""

from __future__ import annotations

import os

import requests

from app.media.base import MediaProvider
from app.media.media_item import MediaItem


class PexelsProvider(MediaProvider):
    name = "pexels"

    def __init__(self, api_key: str | None = None, timeout_seconds: int = 20) -> None:
        self.api_key = api_key or os.getenv("PEXELS_API_KEY")
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, media_type: str = "photo", limit: int = 5) -> list[MediaItem]:
        if not self.api_key:
            return []
        endpoint = "https://api.pexels.com/v1/search"
        params = {"query": query, "per_page": min(limit, 15), "orientation": "portrait"}
        try:
            response = requests.get(endpoint, headers={"Authorization": self.api_key}, params=params, timeout=self.timeout_seconds)
            response.raise_for_status()
        except requests.RequestException:
            return []
        items: list[MediaItem] = []
        for photo in response.json().get("photos", []):
            src = photo.get("src", {}) if isinstance(photo, dict) else {}
            items.append(
                MediaItem(
                    provider=self.name,
                    media_type="stock_photo",
                    title=str(photo.get("alt", "") or query),
                    url=str(photo.get("url", "")),
                    download_url=str(src.get("large2x") or src.get("large") or src.get("original") or ""),
                    width=int(photo.get("width", 0) or 0),
                    height=int(photo.get("height", 0) or 0),
                    author=str(photo.get("photographer", "")),
                    author_url=str(photo.get("photographer_url", "")),
                    license="Pexels License",
                    license_url="https://www.pexels.com/license/",
                    attribution=f"Photo by {photo.get('photographer', 'Pexels')} on Pexels",
                )
            )
        return items
