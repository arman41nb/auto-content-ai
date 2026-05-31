"""Sanitize selected raw images before final rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageStat

from app.content.schemas import CarouselPlan
from app.image.quality import _text_component_features


BOTTOM_ZONE_START = 0.68


@dataclass(frozen=True)
class SanitizedSlide:
    slide_key: str
    input_path: str
    output_path: str
    sanitized: bool
    suspicion_score: float
    sanitizer_area_ratio: float = 0.0
    sanitizer_visual_damage_risk: str = "low"
    false_positive_suspected: bool = False
    actions: list[str] = field(default_factory=list)
    features: dict[str, int] = field(default_factory=dict)


def sanitize_post_images(plan: CarouselPlan, raw_dir: Path, sanitized_dir: Path) -> dict[str, object]:
    """Create sanitized copies for raw slides with likely lower-band AI text artifacts."""

    sanitized_dir.mkdir(parents=True, exist_ok=True)
    slides: list[SanitizedSlide] = []
    for slide in plan.slides:
        slide_key = f"slide_{slide.slide_number:02d}"
        raw_path = raw_dir / f"{slide_key}.jpg"
        output_path = sanitized_dir / f"{slide_key}.jpg"
        if not raw_path.exists():
            slides.append(
                SanitizedSlide(
                    slide_key=slide_key,
                    input_path=str(raw_path),
                    output_path=str(output_path),
                    sanitized=False,
                    suspicion_score=0.0,
                    actions=["missing_raw_image"],
                    features={},
                )
            )
            continue

        image = Image.open(raw_path).convert("RGB")
        suspicion_score, features = bottom_artifact_suspicion(image)
        actions: list[str] = []
        sanitized = False
        area_ratio = 0.0
        false_positive = _false_positive_suspected(suspicion_score, features)
        if suspicion_score >= 40.0 and not false_positive:
            image = protect_bottom_band(image)
            image.save(output_path, "JPEG", quality=94, optimize=True)
            sanitized = True
            area_ratio = targeted_sanitizer_area_ratio(image)
            actions = ["targeted_lower_watermark_soft_blur", "local_soft_gradient"]
            if area_ratio > 0.20:
                actions.append("warning_modified_more_than_20_percent")
        else:
            image.save(output_path, "JPEG", quality=94, optimize=True)
            actions = ["raw_copy_no_sanitization_needed"]
            if false_positive:
                actions.append("false_positive_suspected")

        slides.append(
            SanitizedSlide(
                slide_key=slide_key,
                input_path=str(raw_path),
                output_path=str(output_path),
                sanitized=sanitized,
                suspicion_score=round(suspicion_score, 2),
                sanitizer_area_ratio=round(area_ratio, 4),
                sanitizer_visual_damage_risk=sanitizer_visual_damage_risk(area_ratio),
                false_positive_suspected=false_positive,
                actions=actions,
                features=features,
            )
        )

    sanitized_slides = [slide.slide_key for slide in slides if slide.sanitized]
    available_slides = [
        slide.slide_key
        for slide in slides
        if Path(slide.output_path).exists()
    ]
    area_by_slide = {slide.slide_key: slide.sanitizer_area_ratio for slide in slides}
    max_area_ratio = max(area_by_slide.values(), default=0.0)
    damage_risk = sanitizer_visual_damage_risk(max_area_ratio)
    return {
        "sanitized_images_used": bool(available_slides),
        "sanitized_slides": sanitized_slides,
        "sanitized_available_slides": available_slides,
        "sanitizer_area_ratio": round(max_area_ratio, 4),
        "sanitizer_area_ratio_per_slide": area_by_slide,
        "sanitizer_visual_damage_risk": damage_risk,
        "sanitizer_visual_damage_risk_per_slide": {
            slide.slide_key: slide.sanitizer_visual_damage_risk for slide in slides
        },
        "false_positive_suspected": any(slide.false_positive_suspected for slide in slides),
        "false_positive_suspected_per_slide": {
            slide.slide_key: slide.false_positive_suspected for slide in slides
        },
        "qa_sensitivity_level": "reduced_targeted",
        "sanitizer_actions_per_slide": {slide.slide_key: slide.actions for slide in slides},
        "sanitizer_suspicion_score_per_slide": {
            slide.slide_key: slide.suspicion_score for slide in slides
        },
        "sanitizer_features_per_slide": {slide.slide_key: slide.features for slide in slides},
    }


def preferred_image_dir(output_dir: Path, raw_dir: Path) -> Path:
    sanitized_dir = output_dir / "sanitized_images"
    if sanitized_dir.exists() and any(sanitized_dir.glob("slide_*.jpg")):
        return sanitized_dir
    return raw_dir


def preferred_image_path(raw_path: Path, sanitized_dir: Path) -> Path:
    sanitized_path = sanitized_dir / raw_path.name
    return sanitized_path if sanitized_path.exists() else raw_path


def bottom_artifact_suspicion(image: Image.Image) -> tuple[float, dict[str, int]]:
    features = _text_component_features(image)
    width, height = image.size
    bottom = image.crop((0, int(height * BOTTOM_ZONE_START), width, height)).convert("L")
    edge_score = int(ImageStat.Stat(bottom.filter(ImageFilter.FIND_EDGES)).mean[0])
    contrast = int(ImageStat.Stat(bottom).stddev[0])
    features = {**features, "lower_band_edge_score": edge_score, "lower_band_contrast": contrast}

    score = 0.0
    score += min(42.0, features.get("bottom_components", 0) * 7.0)
    score += min(50.0, features.get("bottom_long_text_components", 0) * 50.0)
    score += min(24.0, max(0, edge_score - 30) * 1.2)
    if contrast > 58 and edge_score > 36:
        score += 14.0
    return min(100.0, score), features


def protect_bottom_band(image: Image.Image) -> Image.Image:
    """Softly treat the likely lower watermark strip without obscuring the whole bottom half."""

    rgba = image.convert("RGBA")
    width, height = rgba.size
    band_top = int(height * 0.82)
    side_margin = int(width * 0.08)
    band = rgba.crop((side_margin, band_top, width - side_margin, height)).filter(ImageFilter.GaussianBlur(radius=4))
    dark = Image.new("RGBA", band.size, (0, 0, 0, 36))
    band = Image.alpha_composite(band, dark)
    rgba.alpha_composite(band, (side_margin, band_top))

    gradient = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    for y in range(max(0, band_top - 44), height):
        progress = (y - (band_top - 44)) / max(1, height - (band_top - 44))
        alpha = int(6 + 42 * max(0.0, min(1.0, progress)) ** 1.4)
        draw.line((side_margin, y, width - side_margin, y), fill=(0, 0, 0, min(54, alpha)))
    return Image.alpha_composite(rgba, gradient).convert("RGB")


def targeted_sanitizer_area_ratio(image: Image.Image) -> float:
    width, height = image.size
    changed_width = width * 0.84
    changed_height = height * 0.18
    return (changed_width * changed_height) / max(1, width * height)


def sanitizer_visual_damage_risk(area_ratio: float) -> str:
    if area_ratio > 0.20:
        return "high"
    if area_ratio > 0.12:
        return "medium"
    return "low"


def _false_positive_suspected(suspicion_score: float, features: dict[str, int]) -> bool:
    has_text_band = features.get("bottom_long_text_components", 0) >= 1 or features.get("bottom_components", 0) >= 8
    edge_only = features.get("lower_band_edge_score", 0) >= 44 and not has_text_band
    return 40.0 <= suspicion_score < 70.0 and edge_only
