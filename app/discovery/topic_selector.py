"""Topic selection helpers."""

from __future__ import annotations

from app.discovery.schemas import TopicCandidate


def select_top_topics(candidates: list[TopicCandidate], count: int) -> list[TopicCandidate]:
    deduped: dict[str, TopicCandidate] = {}
    for candidate in candidates:
        key = _normalize_topic(candidate.topic)
        current = deduped.get(key)
        if current is None or candidate.score > current.score:
            deduped[key] = candidate
    return sorted(deduped.values(), key=lambda item: item.score, reverse=True)[: max(count, 0)]


def _normalize_topic(value: str) -> str:
    return " ".join(value.lower().strip().split())

