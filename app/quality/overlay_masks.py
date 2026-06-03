"""Expected renderer overlay regions for artifact QA bookkeeping."""

from __future__ import annotations

from app.content.schemas import CarouselSlide
from app.render.carousel_renderer import CANVAS_SIZE


def get_expected_overlay_regions(
    slide: CarouselSlide,
    template_name: str,
    output_size: tuple[int, int] = CANVAS_SIZE,
) -> list[dict[str, object]]:
    """Return approximate regions occupied by intentional Pillow-rendered text."""

    width, height = output_size
    if template_name.startswith("editorial_explainer_reel"):
        regions = [
            _region("scene_label", 58, 58, 360, 132, width, height),
            _region("handle", width - 360, height - 130, width - 58, height - 56, width, height),
            _region("headline_subtext_box", 58, int(height * 0.56), width - 100, height - 260, width, height),
            _region("subtle_gradient", 0, int(height * 0.54), width, height, width, height),
        ]
        return regions

    if template_name.startswith("cinematic_reel_editorial"):
        regions = [
            _region("tag_badge", 58, 54, 460, 134, width, height),
            _region("slide_count", width - 180, 54, width - 58, 112, width, height),
            _region("handle", 58, height - 118, 330, height - 54, width, height),
        ]
        if slide.text_position == "top_left":
            regions.append(_region("headline_subtext_box", 58, 210, width - 110, 520, width, height))
        elif slide.text_position == "center":
            regions.append(_region("headline_subtext_box", 58, 430, width - 110, 760, width, height))
        else:
            regions.append(_region("headline_subtext_box", 58, int(height * 0.58), width - 110, height - 210, width, height))
        regions.append(_region("subtle_gradient", 0, int(height * 0.52), width, height, width, height))
        return regions

    regions = [
        _region("tag_badge", 48, 48, 430, 150, width, height),
        _region("slide_count", width - 260, 48, width - 48, 120, width, height),
        _region("handle", width - 370, height - 130, width - 48, height - 44, width, height),
        _region("footer_gradient", 0, int(height * 0.68), width, height, width, height),
    ]
    if template_name == "cinematic_cta":
        regions.append(_region("cta_center_box", 120, 510, width - 120, height - 210, width, height))
    elif template_name == "cinematic_cover":
        regions.append(_region("headline_subtext_box", 42, 640, width - 110, height - 160, width, height))
    elif slide.text_position == "top_left":
        regions.append(_region("headline_subtext_box", 42, 190, width - 160, 620, width, height))
    elif slide.text_position == "center":
        regions.append(_region("headline_subtext_box", 42, 310, width - 120, 900, width, height))
    else:
        regions.append(_region("headline_subtext_box", 42, 700, width - 160, height - 125, width, height))
    return regions


def _region(
    name: str,
    left: int,
    top: int,
    right: int,
    bottom: int,
    width: int,
    height: int,
) -> dict[str, object]:
    left = max(0, min(width, left))
    right = max(left, min(width, right))
    top = max(0, min(height, top))
    bottom = max(top, min(height, bottom))
    return {"name": name, "box": [left, top, right, bottom]}
