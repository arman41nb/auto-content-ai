"""NASA public API topic source."""

from __future__ import annotations

import os

import requests

from app.discovery.schemas import DiscoveryLane, TopicCandidate
from app.discovery.sources.base import DiscoverySource, compact_summary


NASA_QUERIES = {
    "science": "exoplanet OR black hole OR nebula OR neutron star",
    "future": "Mars habitat OR Artemis moon OR space technology",
    "history": "Apollo mission OR space history",
}
LANE_QUERIES = {
    "what_if_disaster": "asteroid impact OR solar storm OR Earth atmosphere OR Moon tides",
    "extreme_science": "exoplanet OR black hole OR neutron star OR rogue planet OR Jupiter storm",
    "future_scenario": "Mars habitat OR Artemis Moon base OR space technology",
    "any": "",
}


class NasaSource(DiscoverySource):
    name = "nasa"

    def __init__(self, timeout_seconds: float = 12.0) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch(
        self,
        niche: str,
        count: int,
        query: str | None = None,
        lane: DiscoveryLane = "any",
    ) -> list[TopicCandidate]:
        api_key = os.getenv("NASA_API_KEY") or "DEMO_KEY"
        candidates: list[TopicCandidate] = []
        candidates.extend(self._fetch_apod(niche=niche, count=min(count, 5), api_key=api_key, lane=lane))
        if len(candidates) < count:
            candidates.extend(
                self._fetch_image_search(
                    niche=niche,
                    count=count - len(candidates),
                    query=query or LANE_QUERIES.get(lane, "") or NASA_QUERIES.get(niche.lower(), "space science"),
                    lane=lane,
                )
            )
        return candidates[:count]

    def _fetch_apod(self, niche: str, count: int, api_key: str, lane: DiscoveryLane) -> list[TopicCandidate]:
        try:
            response = requests.get(
                "https://api.nasa.gov/planetary/apod",
                params={"api_key": api_key, "count": max(count, 1), "thumbs": "false"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"NASA APOD request failed: {exc}") from exc

        if isinstance(payload, dict):
            rows = [payload]
        elif isinstance(payload, list):
            rows = payload
        else:
            return []

        candidates: list[TopicCandidate] = []
        for item in rows:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            summary = compact_summary(str(item.get("explanation") or ""))
            candidates.append(
                TopicCandidate(
                    topic=_topic_from_title(title, niche),
                    niche=niche,
                    lane=lane,
                    angle=f"Use NASA's image context to explain why {title} is visually surprising.",
                    source=self.name,
                    source_url=item.get("url") if isinstance(item.get("url"), str) else None,
                    source_title=title,
                    source_summary=summary,
                    keywords=_keywords_for_niche(niche) + ["NASA", "space"],
                    reasons=["Found through NASA APOD."],
                )
            )
        return candidates

    def _fetch_image_search(self, niche: str, count: int, query: str, lane: DiscoveryLane) -> list[TopicCandidate]:
        try:
            response = requests.get(
                "https://images-api.nasa.gov/search",
                params={"q": query, "media_type": "image"},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"NASA image search request failed: {exc}") from exc

        items = payload.get("collection", {}).get("items", []) if isinstance(payload, dict) else []
        candidates: list[TopicCandidate] = []
        for item in items:
            data_list = item.get("data", []) if isinstance(item, dict) else []
            if not data_list or not isinstance(data_list[0], dict):
                continue
            data = data_list[0]
            title = str(data.get("title") or "").strip()
            if not title:
                continue
            summary = compact_summary(str(data.get("description") or ""))
            candidates.append(
                TopicCandidate(
                    topic=_topic_from_title(title, niche),
                    niche=niche,
                    lane=lane,
                    angle=f"Turn the NASA archive result into a clear visual explainer: {title}.",
                    source=self.name,
                    source_url=item.get("href") if isinstance(item.get("href"), str) else None,
                    source_title=title,
                    source_summary=summary,
                    keywords=_keywords_for_niche(niche) + ["NASA"],
                    reasons=["Found through NASA image search."],
                )
            )
            if len(candidates) >= count:
                break
        return candidates


def _topic_from_title(title: str, niche: str) -> str:
    clean = " ".join(title.split())
    if niche.lower() == "future" and not clean.lower().startswith("what if"):
        return f"The future hinted by {clean}"
    return clean[:120]


def _keywords_for_niche(niche: str) -> list[str]:
    if niche.lower() == "future":
        return ["future", "Mars", "moon", "technology"]
    if niche.lower() == "history":
        return ["history", "space history", "mission"]
    return ["science", "planet", "star", "space"]
