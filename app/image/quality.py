"""Lightweight image QA and candidate selection."""

from __future__ import annotations

import math
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps, ImageStat

from app.content.schemas import CarouselSlide


TEXT_SAFE_BOXES = {
    "top_left": (0.05, 0.08, 0.72, 0.42),
    "center": (0.08, 0.30, 0.92, 0.70),
    "bottom_left": (0.05, 0.58, 0.78, 0.92),
}

HISTORY_ALIGNMENT_TERMS = {
    "rome": ["rome", "roman", "insula", "insulae", "bath", "market", "street", "bread", "tunics"],
    "ancient": ["ancient", "roman", "period", "stone", "clay", "plaster", "oil lamps"],
    "daily": ["daily", "working", "ordinary", "crowded", "street", "market", "apartment"],
}


@dataclass(frozen=True)
class CandidateScore:
    filename: str
    score: float
    artifact_risk_score: float
    high_artifact_risk: bool
    artifact_penalty: float
    text_penalty: float
    composition_score: float
    prompt_alignment_score: float
    warnings: list[str] = field(default_factory=list)
    ocr_text: str = ""


@dataclass(frozen=True)
class ImageSelection:
    slide_number: int
    prompt_used: str
    variant_filenames: list[str]
    selected_variant: str
    chosen_variant: int
    rejected_variants: list[str]
    scores: list[CandidateScore]
    selection_reason: str
    image_quality_warnings: list[str]


def select_best_candidate(
    slide: CarouselSlide,
    prompt: str,
    variant_paths: list[Path],
    final_path: Path,
    niche: str,
) -> ImageSelection:
    """Score candidates, copy the best one to final_path, and return debug metadata."""

    scores = [score_candidate(path, slide, prompt, niche) for path in variant_paths]
    clean_scores = [score for score in scores if not score.high_artifact_risk]
    best = max(clean_scores or scores, key=lambda item: item.score)
    best_path = next(path for path in variant_paths if path.name == best.filename)

    final_path.parent.mkdir(parents=True, exist_ok=True)
    if best_path.resolve() != final_path.resolve():
        shutil.copyfile(best_path, final_path)

    warnings = list(best.warnings)
    high_risk_rejections = [score.filename for score in scores if score.high_artifact_risk and score.filename != best.filename]
    if high_risk_rejections:
        warnings.append(
            "Rejected image candidate(s) with high text/watermark artifact risk: "
            + ", ".join(high_risk_rejections)
            + "."
        )
    if best.high_artifact_risk:
        warnings.append(
            "High text/watermark artifact risk remains because no clean image alternative was available."
        )
    if best.score < 55:
        warnings.append("All generated candidates scored below the preferred quality threshold.")

    rejected = [score.filename for score in scores if score.filename != best.filename]
    chosen_variant = _extract_variant_number(best.filename)
    reason = (
        f"Selected {best.filename} with score {best.score:.1f}; "
        f"artifact risk {best.artifact_risk_score:.1f}, "
        f"composition {best.composition_score:.1f}, text penalty {best.text_penalty:.1f}, "
        f"artifact penalty {best.artifact_penalty:.1f}."
    )
    return ImageSelection(
        slide_number=slide.slide_number,
        prompt_used=prompt,
        variant_filenames=[path.name for path in variant_paths],
        selected_variant=best.filename,
        chosen_variant=chosen_variant,
        rejected_variants=rejected,
        scores=scores,
        selection_reason=reason,
        image_quality_warnings=warnings,
    )


def score_candidate(path: Path, slide: CarouselSlide, prompt: str, niche: str) -> CandidateScore:
    warnings: list[str] = []
    image = Image.open(path).convert("RGB")

    artifact_penalty, artifact_risk = _artifact_penalty(image, warnings)
    text_penalty, text_risk, ocr_text = _text_penalty(image, slide.text_position, warnings)
    composition_score = _composition_score(image, slide.text_position, warnings)
    alignment_score = _prompt_alignment_score(slide, prompt, niche, warnings)

    artifact_risk_score = max(artifact_risk, text_risk)
    high_artifact_risk = artifact_risk_score >= 70.0
    if high_artifact_risk:
        warnings.append("High text/watermark artifact risk detected; slide is not publish-ready.")

    score = 45.0 + composition_score + alignment_score - artifact_penalty - text_penalty
    if high_artifact_risk:
        score -= 28.0
    score = max(0.0, min(100.0, score))

    return CandidateScore(
        filename=path.name,
        score=round(score, 2),
        artifact_risk_score=round(artifact_risk_score, 2),
        high_artifact_risk=high_artifact_risk,
        artifact_penalty=round(artifact_penalty, 2),
        text_penalty=round(text_penalty, 2),
        composition_score=round(composition_score, 2),
        prompt_alignment_score=round(alignment_score, 2),
        warnings=warnings,
        ocr_text=ocr_text,
    )


def selection_to_dict(selection: ImageSelection) -> dict[str, object]:
    return {
        "slide_number": selection.slide_number,
        "prompt_used": selection.prompt_used,
        "variant_filenames": selection.variant_filenames,
        "selected_variant": selection.selected_variant,
        "chosen_variant": selection.chosen_variant,
        "rejected_variants": selection.rejected_variants,
        "scores": [score.__dict__ for score in selection.scores],
        "selection_reason": selection.selection_reason,
        "image_quality_warnings": selection.image_quality_warnings,
    }


def _artifact_penalty(image: Image.Image, warnings: list[str]) -> tuple[float, float]:
    grayscale = ImageOps.grayscale(image)
    stat = ImageStat.Stat(grayscale)
    brightness = stat.mean[0]
    contrast = stat.stddev[0]
    edges = grayscale.filter(ImageFilter.FIND_EDGES)
    edge_mean = ImageStat.Stat(edges).mean[0]

    penalty = 0.0
    risk = 0.0
    if brightness < 24 or brightness > 238:
        penalty += 14.0
        risk += 8.0
        warnings.append("Image brightness is extreme.")
    if contrast < 22:
        penalty += 10.0
        risk += 8.0
        warnings.append("Image contrast is very low.")
    if edge_mean > 42:
        penalty += 8.0
        risk += 12.0
        warnings.append("Image has unusually noisy edges that may indicate artifacts.")
    return penalty, min(100.0, risk)


def _text_penalty(
    image: Image.Image,
    text_position: str,
    warnings: list[str],
) -> tuple[float, float, str]:
    ocr_text = _try_ocr(image)
    penalty = 0.0
    risk = 0.0

    if ocr_text:
        text_like = re.sub(r"[^A-Za-z0-9]", "", ocr_text)
        if len(text_like) >= 4:
            penalty += min(55.0, 18.0 + len(text_like) * 1.4)
            risk += min(80.0, 35.0 + len(text_like) * 1.6)
            warnings.append("OCR detected possible accidental text artifacts.")
        if re.search(r"(watermark|shutterstock|alamy|getty|dreamstime|preview|sample|stock)", ocr_text, re.I):
            penalty += 50.0
            risk += 90.0
            warnings.append("OCR detected watermark-like text.")

    safe_crop = _safe_crop(image, text_position)
    edges = ImageOps.grayscale(safe_crop).filter(ImageFilter.FIND_EDGES)
    edge_mean = ImageStat.Stat(edges).mean[0]
    if edge_mean > 34:
        penalty += 9.0
        warnings.append("Text-safe area is visually busy and may fight the overlay.")

    safe_features = _text_component_features(safe_crop)
    full_features = _text_component_features(image)
    if safe_features["components"] >= 10:
        penalty += min(18.0, safe_features["components"] * 0.9)
        warnings.append("Detected small character-like shapes in the text-safe area.")
    if full_features["components"] >= 26:
        penalty += min(14.0, full_features["components"] * 0.35)
        warnings.append("Detected repeated high-contrast character-like shapes.")
    if full_features["max_band_components"] >= 10:
        penalty += 14.0
        risk += 12.0
        warnings.append("Detected suspicious horizontal text-like bands.")
    if full_features["long_text_components"] >= 3:
        penalty += 30.0
        risk += 42.0
        warnings.append("Detected repeated long horizontal gibberish/text bands.")
    if full_features["bottom_components"] >= 5 or full_features["bottom_edge_score"] >= 48:
        penalty += 18.0
        risk += 22.0
        warnings.append("Detected watermark-like artifacts in the bottom zone.")
    if full_features["bottom_long_text_components"] >= 1:
        penalty += 42.0
        risk += 58.0
        warnings.append("Detected bottom watermark-like text band.")
    if full_features["center_components"] >= 18:
        penalty += 10.0
        warnings.append("Detected clustered unreadable text-like artifacts near the center.")
    if full_features["center_long_text_components"] >= 2:
        penalty += 22.0
        risk += 24.0
        warnings.append("Detected clustered unreadable horizontal text near the center.")

    return penalty, min(100.0, risk), ocr_text


def _composition_score(image: Image.Image, text_position: str, warnings: list[str]) -> float:
    crop = _safe_crop(image, text_position)
    grayscale = ImageOps.grayscale(crop)
    stat = ImageStat.Stat(grayscale)
    brightness = stat.mean[0]
    contrast = stat.stddev[0]
    edges = ImageStat.Stat(grayscale.filter(ImageFilter.FIND_EDGES)).mean[0]

    score = 24.0
    if 28 <= brightness <= 145:
        score += 8.0
    else:
        score -= 7.0
        warnings.append("Text-safe area may be too bright or too dark.")

    if contrast <= 52:
        score += 6.0
    else:
        score -= 5.0
        warnings.append("Text-safe area has high contrast.")

    if edges <= 30:
        score += 7.0
    else:
        score -= 6.0

    return max(0.0, min(45.0, score))


def _prompt_alignment_score(
    slide: CarouselSlide,
    prompt: str,
    niche: str,
    warnings: list[str],
) -> float:
    haystack = " ".join([prompt, slide.visual_goal, slide.headline, slide.subtext]).lower()
    score = 10.0

    if niche.strip().lower() == "history":
        matched = 0
        for family_terms in HISTORY_ALIGNMENT_TERMS.values():
            if any(term in haystack for term in family_terms):
                matched += 1
        score += matched * 4.0
        if matched < 2:
            warnings.append("Prompt alignment heuristic found limited history-specific scene detail.")

    if "no text" in haystack and "text-safe" in haystack:
        score += 5.0
    if slide.tag.lower() in haystack:
        score += 2.0
    if len(slide.visual_goal.split()) >= 8:
        score += 3.0

    return max(0.0, min(25.0, score))


def _safe_crop(image: Image.Image, text_position: str) -> Image.Image:
    box = TEXT_SAFE_BOXES.get(text_position, TEXT_SAFE_BOXES["bottom_left"])
    width, height = image.size
    left = math.floor(width * box[0])
    top = math.floor(height * box[1])
    right = math.ceil(width * box[2])
    bottom = math.ceil(height * box[3])
    return image.crop((left, top, right, bottom))


def _try_ocr(image: Image.Image) -> str:
    try:
        import pytesseract  # type: ignore[import-not-found]
    except Exception:
        return ""

    try:
        small = image.copy()
        small.thumbnail((900, 900))
        return " ".join(pytesseract.image_to_string(small).split())
    except Exception:
        return ""


def _text_component_score(image: Image.Image) -> int:
    """Detect clusters that look like accidental bright letters without OCR."""

    return _text_component_features(image)["components"]


def _text_component_features(image: Image.Image) -> dict[str, int]:
    """Detect repeated high-contrast text-like components without OCR."""

    grayscale = ImageOps.grayscale(image)
    grayscale.thumbnail((700, 700))
    stat = ImageStat.Stat(grayscale)
    mean = stat.mean[0]
    stddev = stat.stddev[0]
    low_threshold = min(78, max(34, int(mean - stddev * 1.15)))
    high_threshold = max(158, min(212, int(mean + stddev * 1.15)))
    width, height = grayscale.size
    pixels = grayscale.load()
    visited: set[tuple[int, int]] = set()
    components = 0
    long_text_components = 0
    bottom_components = 0
    bottom_long_text_components = 0
    center_components = 0
    center_long_text_components = 0
    band_counts = [0 for _ in range(20)]

    for y in range(height):
        for x in range(width):
            if (x, y) in visited or not _is_high_contrast_text_pixel(pixels[x, y], low_threshold, high_threshold):
                continue
            stack = [(x, y)]
            visited.add((x, y))
            min_x = max_x = x
            min_y = max_y = y
            area = 0

            while stack:
                current_x, current_y = stack.pop()
                area += 1
                min_x = min(min_x, current_x)
                max_x = max(max_x, current_x)
                min_y = min(min_y, current_y)
                max_y = max(max_y, current_y)

                for next_x, next_y in (
                    (current_x + 1, current_y),
                    (current_x - 1, current_y),
                    (current_x, current_y + 1),
                    (current_x, current_y - 1),
                ):
                    if (
                        0 <= next_x < width
                        and 0 <= next_y < height
                        and (next_x, next_y) not in visited
                        and _is_high_contrast_text_pixel(pixels[next_x, next_y], low_threshold, high_threshold)
                    ):
                        visited.add((next_x, next_y))
                        stack.append((next_x, next_y))

            box_width = max_x - min_x + 1
            box_height = max_y - min_y + 1
            aspect = box_width / max(1, box_height)
            fill_ratio = area / max(1, box_width * box_height)
            center_y = (min_y + max_y) / 2
            center_x = (min_x + max_x) / 2
            is_bottom_zone = center_y >= height * 0.74 and width * 0.08 <= center_x <= width * 0.92
            is_center_zone = height * 0.30 <= center_y <= height * 0.70 and width * 0.15 <= center_x <= width * 0.85
            is_long_text_band = (
                60 <= box_width <= 650
                and 3 <= box_height <= 44
                and 30 <= area <= 7000
                and aspect >= 7
                and fill_ratio <= 0.74
            )
            if is_long_text_band:
                long_text_components += 1
                if is_bottom_zone:
                    bottom_long_text_components += 1
                if is_center_zone:
                    center_long_text_components += 1
            if (
                2 <= box_width <= 140
                and 4 <= box_height <= 38
                and 4 <= area <= 1800
                and aspect <= 14
                and fill_ratio <= 0.82
            ):
                components += 1
                band_index = min(len(band_counts) - 1, int(center_y / max(1, height) * len(band_counts)))
                band_counts[band_index] += 1
                if is_bottom_zone:
                    bottom_components += 1
                if is_center_zone:
                    center_components += 1

    bottom_crop = grayscale.crop((0, int(height * 0.74), width, height))
    bottom_edges = bottom_crop.filter(ImageFilter.FIND_EDGES)
    bottom_edge_score = int(ImageStat.Stat(bottom_edges).mean[0])

    return {
        "components": components,
        "long_text_components": long_text_components,
        "bottom_components": bottom_components,
        "bottom_long_text_components": bottom_long_text_components,
        "center_components": center_components,
        "center_long_text_components": center_long_text_components,
        "max_band_components": max(band_counts) if band_counts else 0,
        "bottom_edge_score": bottom_edge_score,
    }


def _is_high_contrast_text_pixel(value: int, low_threshold: int, high_threshold: int) -> bool:
    return value <= low_threshold or value >= high_threshold


def _extract_variant_number(filename: str) -> int:
    match = re.search(r"variant_(\d+)", filename)
    if not match:
        return 1
    return int(match.group(1))
