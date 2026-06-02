"""Unsplash media provider."""

from __future__ import annotations

import os

import requests

from app.media.base import MediaProvider
from app.media.media_item import MediaItem


class UnsplashProvider(MediaProvider):
    name = "unsplash"

    def __init__(self, access_key: str | None = None, timeout_seconds: int = 20) -> None:
        self.access_key = access_key or os.getenv("UNSPLASH_ACCESS_KEY")
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, media_type: str = "photo", limit: int = 5) -> list[MediaItem]:
        if not self.access_key:
            return []
        try:
            response = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": query, "per_page": min(limit, 15), "orientation": "portrait", "client_id": self.access_key},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException:
            return []
        items: list[MediaItem] = []
        for photo in response.json().get("results", []):
            urls = photo.get("urls", {}) if isinstance(photo, dict) else {}
            user = photo.get("user", {}) if isinstance(photo, dict) else {}
            links = photo.get("links", {}) if isinstance(photo, dict) else {}
            items.append(
                MediaItem(
                    provider=self.name,
                    media_type="stock_photo",
                    title=str(photo.get("alt_description", "") or photo.get("description", "") or query),
                    url=str(links.get("html", "")),
                    download_url=str(urls.get("regular") or urls.get("full") or ""),
                    width=int(photo.get("width", 0) or 0),
                    height=int(photo.get("height", 0) or 0),
                    author=str(user.get("name", "")),
                    author_url=str(user.get("links", {}).get("html", "") if isinstance(user.get("links", {}), dict) else ""),
                    license="Unsplash License",
                    license_url="https://unsplash.com/license",
                    attribution=f"Photo by {user.get('name', 'Unsplash')} on Unsplash",
                )
            )
        return items
