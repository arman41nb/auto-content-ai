"""Base class for optional media providers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.media.media_item import MediaItem


class MediaProvider(ABC):
    name: str

    @abstractmethod
    def search(self, query: str, media_type: str = "photo", limit: int = 5) -> list[MediaItem]:
        raise NotImplementedError
