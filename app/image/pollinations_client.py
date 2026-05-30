"""Pollinations.ai image generation client."""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, UnidentifiedImageError

from app.image.base import ImageProvider


class PollinationsImageError(RuntimeError):
    """Raised when Pollinations cannot produce a valid image."""


class PollinationsClient(ImageProvider):
    name = "pollinations"
    model = "flux"

    def __init__(
        self,
        rate_limit_seconds: float = 15.0,
        width: int = 1080,
        height: int = 1350,
        retries: int = 3,
        timeout_seconds: int = 120,
    ) -> None:
        self.rate_limit_seconds = rate_limit_seconds
        self.width = width
        self.height = height
        self.retries = retries
        self.timeout_seconds = timeout_seconds

    def generate_image(self, prompt: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://image.pollinations.ai/prompt/{quote(prompt)}"
        params = {
            "model": self.model,
            "width": self.width,
            "height": self.height,
            "enhance": "true",
            "private": "true",
        }

        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                response = requests.get(url, params=params, timeout=self.timeout_seconds)
                if response.status_code != 200:
                    raise PollinationsImageError(
                        f"HTTP {response.status_code}: {response.text[:200]}"
                    )

                try:
                    image = Image.open(BytesIO(response.content))
                    image.verify()
                except (UnidentifiedImageError, OSError) as exc:
                    raise PollinationsImageError("Pollinations response was not a valid image.") from exc

                output_path.write_bytes(response.content)
                return
            except (requests.RequestException, PollinationsImageError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(2 ** (attempt - 1))

        raise PollinationsImageError(f"Failed to generate image after {self.retries} attempts: {last_error}")

    def wait_between_requests(self) -> None:
        if self.rate_limit_seconds > 0:
            time.sleep(self.rate_limit_seconds)

