"""Pexels media provider."""

from __future__ import annotations

import os
import time

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
        if media_type == "video":
            return self._search_videos(query, limit)
        endpoint = "https://api.pexels.com/v1/search"
        params = {"query": query, "per_page": min(limit, 15), "orientation": "portrait"}
        try:
            response = self._get(endpoint, params)
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
                    download_url=str(src.get("portrait") or src.get("large2x") or src.get("original") or src.get("large") or ""),
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

    def _search_videos(self, query: str, limit: int = 5) -> list[MediaItem]:
        endpoint = "https://api.pexels.com/videos/search"
        params = {"query": query, "per_page": min(limit, 15), "orientation": "portrait"}
        try:
            response = self._get(endpoint, params)
            response.raise_for_status()
        except requests.RequestException:
            return []
        items: list[MediaItem] = []
        for video in response.json().get("videos", []):
            files = video.get("video_files", []) if isinstance(video, dict) else []
            best_url = ""
            best_width = int(video.get("width", 0) or 0)
            best_height = int(video.get("height", 0) or 0)
            if isinstance(files, list):
                ranked = sorted(
                    [item for item in files if isinstance(item, dict) and item.get("link")],
                    key=lambda item: (int(item.get("height", 0) or 0), int(item.get("width", 0) or 0)),
                    reverse=True,
                )
                if ranked:
                    best = ranked[0]
                    best_url = str(best.get("link", ""))
                    best_width = int(best.get("width", best_width) or best_width)
                    best_height = int(best.get("height", best_height) or best_height)
            thumbnail_url = str(video.get("image", "") or "")
            user = video.get("user", {}) if isinstance(video.get("user", {}), dict) else {}
            items.append(
                MediaItem(
                    provider=self.name,
                    media_type="stock_video",
                    title=str(video.get("url", "") or query),
                    url=str(video.get("url", "")),
                    download_url=thumbnail_url or best_url,
                    width=best_width,
                    height=best_height,
                    author=str(user.get("name", "")),
                    author_url=str(user.get("url", "")),
                    license="Pexels License",
                    license_url="https://www.pexels.com/license/",
                    attribution=f"Video by {user.get('name', 'Pexels')} on Pexels",
                )
            )
        return items

    def _get(self, endpoint: str, params: dict[str, object]) -> requests.Response:
        response = requests.get(
            endpoint,
            headers={"Authorization": self.api_key or "", "User-Agent": "auto-carousel-editorial-explainer/1.0"},
            params=params,
            timeout=self.timeout_seconds,
        )
        if response.status_code == 429:
            retry_after = _retry_after_seconds(response.headers.get("Retry-After", ""))
            if retry_after > 0:
                time.sleep(min(5.0, retry_after))
                response = requests.get(
                    endpoint,
                    headers={"Authorization": self.api_key or "", "User-Agent": "auto-carousel-editorial-explainer/1.0"},
                    params=params,
                    timeout=self.timeout_seconds,
                )
        return response


def _retry_after_seconds(value: str) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0
