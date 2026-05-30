"""Wikipedia and Wikimedia public endpoint topic source."""

from __future__ import annotations

from datetime import date

import requests

from app.discovery.schemas import DiscoveryLane, TopicCandidate
from app.discovery.sources.base import DiscoverySource, compact_summary


SEARCH_SEEDS = {
    "science": ["exoplanet", "black hole", "rogue planet", "neutron star", "gravity"],
    "future": ["Mars colonization", "artificial intelligence in traffic", "sea level rise", "future city"],
    "history": ["ancient Rome daily life", "medieval castle", "Black Death", "Titanic"],
}
LANE_SEARCH_SEEDS = {
    "what_if_disaster": ["oxygen", "Earth rotation", "Moon tides", "solar storm", "asteroid impact"],
    "extreme_science": ["neutron star", "black hole", "rogue planet", "exoplanet weather", "Jupiter storm"],
    "future_scenario": ["Mars colonization", "artificial intelligence in traffic", "robotics", "future city"],
    "any": [],
}


class WikipediaSource(DiscoverySource):
    name = "wikipedia"

    def __init__(self, timeout_seconds: float = 12.0) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch(
        self,
        niche: str,
        count: int,
        query: str | None = None,
        lane: DiscoveryLane = "any",
    ) -> list[TopicCandidate]:
        if niche.lower() == "history" and not query:
            candidates = self._fetch_on_this_day(count)
            if len(candidates) >= count:
                return candidates[:count]
        else:
            candidates = []

        seeds = [query] if query else LANE_SEARCH_SEEDS.get(lane, []) or SEARCH_SEEDS.get(niche.lower(), [niche])
        for seed in seeds:
            candidates.extend(self._fetch_search(seed=seed, niche=niche, remaining=count - len(candidates), lane=lane))
            if len(candidates) >= count:
                break
        return candidates[:count]

    def _fetch_on_this_day(self, count: int) -> list[TopicCandidate]:
        today = date.today()
        try:
            response = requests.get(
                f"https://en.wikipedia.org/api/rest_v1/feed/onthisday/events/{today.month:02d}/{today.day:02d}",
                timeout=self.timeout_seconds,
                headers={"User-Agent": "auto-carousel-topic-discovery/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"Wikipedia On This Day request failed: {exc}") from exc

        events = payload.get("events", []) if isinstance(payload, dict) else []
        candidates: list[TopicCandidate] = []
        for event in events:
            if not isinstance(event, dict):
                continue
            text = str(event.get("text") or "").strip()
            pages = event.get("pages") or []
            title = _page_title(pages) or text[:80]
            if not text or not title:
                continue
            candidates.append(
                TopicCandidate(
                    topic=_history_topic(title, text),
                    niche="history",
                    angle=f"Use the event as a date-based history carousel with one vivid human detail.",
                    source=self.name,
                    source_url=_page_url(pages),
                    source_title=title,
                    source_summary=compact_summary(text),
                    keywords=["history", "on this day", "event"],
                    reasons=["Found through Wikipedia On This Day."],
                )
            )
            if len(candidates) >= count:
                break
        return candidates

    def _fetch_search(self, seed: str, niche: str, remaining: int, lane: DiscoveryLane) -> list[TopicCandidate]:
        if remaining <= 0:
            return []
        try:
            response = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "format": "json",
                    "generator": "search",
                    "gsrsearch": seed,
                    "gsrlimit": max(remaining, 1),
                    "prop": "extracts|info",
                    "exintro": "1",
                    "explaintext": "1",
                    "inprop": "url",
                },
                timeout=self.timeout_seconds,
                headers={"User-Agent": "auto-carousel-topic-discovery/1.0"},
            )
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise RuntimeError(f"Wikipedia search request failed: {exc}") from exc

        pages = payload.get("query", {}).get("pages", {}) if isinstance(payload, dict) else {}
        candidates: list[TopicCandidate] = []
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            title = str(page.get("title") or "").strip()
            summary = compact_summary(str(page.get("extract") or ""))
            if not title:
                continue
            candidates.append(
                TopicCandidate(
                    topic=_topic_for_niche(title, niche),
                    niche=niche,
                    lane=lane,
                    angle=_angle_for_niche(title, niche),
                    source=self.name,
                    source_url=page.get("fullurl") if isinstance(page.get("fullurl"), str) else None,
                    source_title=title,
                    source_summary=summary,
                    keywords=[niche, seed],
                    reasons=["Found through Wikipedia search."],
                )
            )
        return candidates


def _page_title(pages: object) -> str | None:
    if isinstance(pages, list) and pages and isinstance(pages[0], dict):
        return str(pages[0].get("title") or "").strip() or None
    return None


def _page_url(pages: object) -> str | None:
    if isinstance(pages, list) and pages and isinstance(pages[0], dict):
        urls = pages[0].get("content_urls", {})
        desktop = urls.get("desktop", {}) if isinstance(urls, dict) else {}
        page = desktop.get("page") if isinstance(desktop, dict) else None
        return page if isinstance(page, str) else None
    return None


def _history_topic(title: str, text: str) -> str:
    if len(title.split()) <= 7:
        return title
    return text[:100].rstrip(".")


def _topic_for_niche(title: str, niche: str) -> str:
    clean = " ".join(title.split())
    if niche.lower() == "future" and not clean.lower().startswith("what if"):
        return f"What if {clean} shaped the future"
    return clean[:120]


def _angle_for_niche(title: str, niche: str) -> str:
    if niche.lower() == "history":
        return f"Find the daily-life or survival angle inside {title}."
    if niche.lower() == "future":
        return f"Explain {title} as a near-future what-if with concrete consequences."
    return f"Make {title} feel surprising, visual, and easy to explain."
