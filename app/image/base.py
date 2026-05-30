"""Base interfaces for image providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ImageProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def generate_image(self, prompt: str, output_path: Path) -> None:
        """Generate an image for a prompt and save it to output_path."""

