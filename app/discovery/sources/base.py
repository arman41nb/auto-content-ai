"""Base classes for discovery sources."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.discovery.schemas import DiscoveryLane, TopicCandidate


class DiscoverySource(ABC):
    name: str

    @abstractmethod
    def fetch(
        self,
        niche: str,
        count: int,
        query: str | None = None,
        lane: DiscoveryLane = "any",
    ) -> list[TopicCandidate]:
        """Return unscored topic candidates for a niche."""


def compact_summary(value: str | None, max_length: int = 420) -> str | None:
    if not value:
        return None
    clean = " ".join(value.strip().split())
    if len(clean) <= max_length:
        return clean
    return clean[: max_length - 3].rstrip() + "..."
