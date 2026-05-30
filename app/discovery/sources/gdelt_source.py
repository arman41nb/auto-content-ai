"""GDELT public news query topic source."""

from __future__ import annotations

import requests

from app.discovery.schemas import DiscoveryLane, TopicCandidate
from app.discovery.sources.base import DiscoverySource, compact_summary


GDELT_QUERIES = {
    "science": "(space OR astronomy OR exoplanet OR blackhole OR NASA)",
    "future": "(future OR AI OR Mars OR climate OR robotics)",
    "history": "(archaeology OR ancient OR medieval OR museum)",
}
LANE_QUERIES = {
    "what_if_disaster": "(asteroid OR solarstorm OR volcano OR earthquake OR ocean OR moon)",
    "extreme_science": "(exoplanet OR blackhole OR neutronstar OR astronomy OR Jupiter OR Mars)",
    "future_scenario": "(AI OR robotics OR Mars OR futurecity OR autonomousvehicles)",
    "any": "",
}


class GdeltSource(DiscoverySource):
    name = "gdelt"

    def __init__(self, timeout_seconds: float = 12.0) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch(
        self,
        niche: str,
        count: int,
        query: str | None = None,
        lane: DiscoveryLane = "any",
    ) -> list[TopicCandidate]:
        gdelt_query = query or LANE_QUERIES.get(lane, "") or GDELT_QUERIES.get(niche.lower(), niche)
        try:
            response = requests.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={
                    "query": gdelt_query,
                    "mode": "artlist",
                    "format": "json",
                    "maxrecords": max(count, 1),
                    "sort": "HybridRel",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"GDELT request failed: {exc}") from exc

        articles = payload.get("articles", []) if isinstance(payload, dict) else []
        candidates: list[TopicCandidate] = []
        for article in articles:
            if not isinstance(article, dict):
                continue
            title = str(article.get("title") or "").strip()
            if not title:
                continue
            candidates.append(
                TopicCandidate(
                    topic=_topic_from_title(title, niche),
                    niche=niche,
                    lane=lane,
                    angle=f"Use this current public-news hook as a simple evergreen explainer: {title}.",
                    source=self.name,
                    source_url=article.get("url") if isinstance(article.get("url"), str) else None,
                    source_title=title,
                    source_summary=compact_summary(str(article.get("seendate") or article.get("domain") or "")),
                    keywords=[niche, "recent", "news"],
                    reasons=["Found through GDELT recent web coverage."],
                )
            )
            if len(candidates) >= count:
                break
        return candidates


def _topic_from_title(title: str, niche: str) -> str:
    clean = " ".join(title.split())
    if niche.lower() == "future":
        return f"The future behind: {clean[:95]}"
    return clean[:120]
