"""Font loading for rendered carousel slides."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont


WINDOWS_BOLD_FONTS = [
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]
WINDOWS_REGULAR_FONTS = [
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
]
LINUX_BOLD_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
LINUX_REGULAR_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


@dataclass(frozen=True)
class FontSet:
    headline: ImageFont.ImageFont
    subtext: ImageFont.ImageFont
    badge: ImageFont.ImageFont
    meta: ImageFont.ImageFont
    warnings: list[str]


def _find_font(paths: list[str]) -> str | None:
    for path in paths:
        if Path(path).exists():
            return path
    return None


def _load(path: str | None, size: int, warnings: list[str]) -> ImageFont.ImageFont:
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            warnings.append(f"Could not load font: {path}")
    warnings.append(f"No TrueType font found for size {size}; using Pillow default.")
    return ImageFont.load_default()


def load_font_set() -> FontSet:
    warnings: list[str] = []
    bold_path = _find_font(WINDOWS_BOLD_FONTS + LINUX_BOLD_FONTS)
    regular_path = _find_font(WINDOWS_REGULAR_FONTS + LINUX_REGULAR_FONTS)
    return FontSet(
        headline=_load(bold_path, 70, warnings),
        subtext=_load(regular_path, 38, warnings),
        badge=_load(bold_path, 28, warnings),
        meta=_load(regular_path, 28, warnings),
        warnings=warnings,
    )


def load_font(size: int, bold: bool, warnings: list[str]) -> ImageFont.ImageFont:
    paths = WINDOWS_BOLD_FONTS + LINUX_BOLD_FONTS if bold else WINDOWS_REGULAR_FONTS + LINUX_REGULAR_FONTS
    return _load(_find_font(paths), size, warnings)

