"""Reel-native motion infographic backgrounds."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from app.render.premium_infographics import create_premium_infographic_still, oil_dollar_premium_infographic


def create_motion_infographic_still(scene: Any, output_path: Path, progress: float = 1.0) -> Path:
    return create_premium_infographic_still(scene, output_path, progress=progress)


def oil_dollar_infographic(scene: Any, progress: float = 1.0) -> Image.Image:
    return oil_dollar_premium_infographic(scene, progress=progress)
