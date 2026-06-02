"""Wikimedia Commons media provider."""

from __future__ import annotations

import requests

from app.media.base import MediaProvider
from app.media.media_item import MediaItem


class WikimediaProvider(MediaProvider):
    name = "wikimedia"

    def __init__(self, timeout_seconds: int = 20) -> None:
        self.timeout_seconds = timeout_seconds

    def search(self, query: str, media_type: str = "photo", limit: int = 5) -> list[MediaItem]:
        try:
            response = requests.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": f"file:{query}",
                    "gsrnamespace": 6,
                    "gsrlimit": min(limit, 10),
                    "prop": "imageinfo",
                    "iiprop": "url|size|mime|extmetadata",
                    "format": "json",
                },
                headers={"User-Agent": "AutoCarouselExplainerReel/1.0 (local educational content tool)"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException:
            return []
        pages = response.json().get("query", {}).get("pages", {})
        items: list[MediaItem] = []
        for page in pages.values():
            info_list = page.get("imageinfo", []) if isinstance(page, dict) else []
            if not info_list:
                continue
            info = info_list[0]
            mime = str(info.get("mime", ""))
            if not mime.startswith("image/"):
                continue
            meta = info.get("extmetadata", {}) if isinstance(info.get("extmetadata", {}), dict) else {}
            artist = _meta(meta, "Artist")
            license_short = _meta(meta, "LicenseShortName") or _meta(meta, "UsageTerms")
            license_url = _meta(meta, "LicenseUrl")
            title = str(page.get("title", query)).replace("File:", "")
            url = str(info.get("descriptionurl", ""))
            items.append(
                MediaItem(
                    provider=self.name,
                    media_type="wikimedia_image",
                    title=title,
                    url=url,
                    download_url=str(info.get("url", "")),
                    width=int(info.get("width", 0) or 0),
                    height=int(info.get("height", 0) or 0),
                    author=_strip_html(artist),
                    author_url=url,
                    license=license_short or "Wikimedia Commons license metadata",
                    license_url=license_url,
                    attribution=f"{title} by {_strip_html(artist) or 'Wikimedia Commons'} ({license_short or 'license metadata'})",
                )
            )
        return items


def _meta(metadata: dict[str, object], key: str) -> str:
    value = metadata.get(key, {})
    if isinstance(value, dict):
        return str(value.get("value", "") or "")
    return ""


def _strip_html(value: str) -> str:
    text = value.replace("<br>", " ").replace("<br />", " ")
    out = []
    in_tag = False
    for char in text:
        if char == "<":
            in_tag = True
        elif char == ">":
            in_tag = False
        elif not in_tag:
            out.append(char)
    return " ".join("".join(out).split())
