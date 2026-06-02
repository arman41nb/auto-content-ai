"""Download and normalize selected media assets."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import requests
from PIL import Image, ImageDraw

from app.media.media_item import MediaItem


REEL_SIZE = (1080, 1920)


def download_media_item(item: MediaItem, output_path: Path, timeout_seconds: int = 30) -> MediaItem:
    if item.local_path and Path(item.local_path).exists():
        return item
    if not item.download_url:
        return item
    try:
        response = requests.get(item.download_url, timeout=timeout_seconds)
        response.raise_for_status()
        image = Image.open(BytesIO(response.content)).convert("RGB")
    except Exception:
        return item
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _cover_crop(image, REEL_SIZE).save(output_path, "JPEG", quality=94, optimize=True)
    return item.model_copy(update={"local_path": str(output_path), "width": image.width, "height": image.height})


def create_fallback_visual(output_path: Path, title: str, label: str = "EXPLAINER") -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", REEL_SIZE, (20, 27, 34))
    draw = ImageDraw.Draw(image)
    for y in range(REEL_SIZE[1]):
        r = int(20 + y / REEL_SIZE[1] * 16)
        g = int(27 + y / REEL_SIZE[1] * 26)
        b = int(34 + y / REEL_SIZE[1] * 20)
        draw.line((0, y, REEL_SIZE[0], y), fill=(r, g, b))
    draw.rectangle((96, 240, 984, 1540), outline=(220, 190, 118), width=5)
    draw.text((118, 280), label[:24].upper(), fill=(230, 214, 168))
    draw.text((118, 340), title[:68], fill=(244, 244, 238))
    image.save(output_path, "JPEG", quality=94, optimize=True)
    return output_path


def _cover_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))
