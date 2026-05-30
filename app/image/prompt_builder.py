"""Build stronger image prompts from planned carousel slides."""

from __future__ import annotations

from dataclasses import dataclass

from app.content.schemas import CarouselSlide


BASE_POSITIVE_CONSTRAINTS = [
    "cinematic realistic documentary still",
    "documentary photography feel",
    "lived-in daily life",
    "natural realistic lighting",
    "rough tactile materials",
    "vertical 9:16 Reel-first composition with a 4:5 center-safe crop",
    "clear subject separation",
    "strong depth",
    "usable negative space without empty black bands",
]

BASE_NEGATIVE_CONSTRAINTS = [
    "no text",
    "no letters",
    "no words",
    "no signs",
    "no signage",
    "no captions",
    "no subtitles",
    "no watermark",
    "no logo",
    "no UI",
    "no poster",
    "no labels",
    "no typography",
    "no caption inside the image",
    "clean image only",
    "no malformed hands",
    "no distorted faces",
    "no extra limbs",
]

STRICT_NO_TEXT_INSTRUCTION = (
    "no text, no letters, no words, no signs, no captions, no subtitles, "
    "no logos, no watermark, no UI, no posters, no labels, no typography, clean image only"
)

TEXT_INVITING_TERMS = {
    "field note": "cinematic observation",
    "documentary note": "cinematic scene",
    "news": "realistic scene",
    "poster": "image",
    "label": "object",
    "signage": "background architecture",
    "readable sign": "plain surface",
}

HISTORY_POSITIVE_CONSTRAINTS = [
    "historically inspired ancient Roman setting when relevant to the topic",
    "working-class environment",
    "ordinary non-elite people",
    "worn tunics and practical clothing",
    "stone, timber, clay, plaster, dust, smoke, oil lamps",
    "crowded urban texture",
    "period-appropriate props only",
]

HISTORY_NEGATIVE_CONSTRAINTS = [
    "no modern architecture",
    "no contemporary interior design",
    "no minimal studio look",
    "no modern furniture",
    "no glass skyscrapers",
    "no electric lights",
    "no plastic objects",
    "no modern street signs",
    "no printed labels",
    "no fantasy armor",
]

DISASTER_TOPIC_MARKERS = (
    "flood",
    "flooded",
    "ocean",
    "oceans",
    "sea level",
    "water rises",
    "rose overnight",
    "overnight",
    "disaster",
    "survival",
    "evacuation",
    "power fails",
    "clean water",
)

DISASTER_POSITIVE_CONSTRAINTS = [
    "premium cinematic science documentary style",
    "natural cinematic lighting",
    "realistic documentary still",
    "human-scale survival detail",
    "not a poster",
    "not a horror movie poster",
    "image-led composition",
    "no giant black empty zones",
    "no dark blank lower band",
]

DISASTER_NEGATIVE_CONSTRAINTS = [
    "no repeated generic flooded skyline",
    "no black empty lower third",
    "no oversized empty foreground",
    "no drowning close-up face",
    "no horror poster expression",
    "no fake movie poster",
]


@dataclass(frozen=True)
class BuiltImagePrompt:
    prompt: str
    positive_constraints: list[str]
    negative_constraints: list[str]


def build_image_prompt(slide: CarouselSlide, niche: str) -> BuiltImagePrompt:
    """Return an enriched image prompt for a slide and niche."""

    positive = list(BASE_POSITIVE_CONSTRAINTS)
    negative = list(BASE_NEGATIVE_CONSTRAINTS)
    disaster = _looks_like_what_if_disaster(slide)

    if niche.strip().lower() == "history":
        positive.extend(HISTORY_POSITIVE_CONSTRAINTS)
        negative.extend(HISTORY_NEGATIVE_CONSTRAINTS)
    if disaster:
        positive.extend(DISASTER_POSITIVE_CONSTRAINTS)
        negative.extend(DISASTER_NEGATIVE_CONSTRAINTS)

    safe_area = _safe_area_instruction(slide.text_position, disaster=disaster)
    camera_direction = _disaster_camera_direction(slide) if disaster else ""
    scene = " ".join(
        part.strip()
        for part in [
            _clean_disaster_scene_prompt(_remove_text_inviting_terms(slide.image_prompt), disaster=disaster),
            camera_direction,
            f"Exact scene goal: {slide.visual_goal}",
            f"Composition: {slide.composition_hint}",
            safe_area,
        ]
        if part.strip()
    )

    prompt = (
        f"{scene}. Positive constraints: {', '.join(_dedupe(positive))}. "
        f"Negative constraints: {', '.join(_dedupe(negative))}. "
        f"Strict image-only rule: {STRICT_NO_TEXT_INSTRUCTION}."
    )
    return BuiltImagePrompt(
        prompt=_clean_prompt(prompt, max_length=1800),
        positive_constraints=_dedupe(positive),
        negative_constraints=_dedupe(negative),
    )


def _safe_area_instruction(position: str, disaster: bool = False) -> str:
    if disaster:
        if position == "top_left":
            return "Leave readable low-detail sky or wall texture near the upper left, but keep the scene image-led and avoid blank black space."
        if position == "center":
            return "Keep a natural low-detail mid-frame area for short captions, without creating a pasted empty zone."
        return "Leave usable negative space near the lower left edge with natural shadow or water texture, not a huge black lower band."
    if position == "top_left":
        return "Reserve a low-detail darker text-safe negative space in the upper left quadrant."
    if position == "center":
        return "Keep the central vertical area low-detail enough for overlaid text while preserving the scene."
    return "Reserve a low-detail darker text-safe negative space in the lower third, especially lower left."


def _looks_like_what_if_disaster(slide: CarouselSlide) -> bool:
    text = " ".join(
        [
            slide.headline,
            slide.subtext,
            slide.visual_goal,
            slide.image_prompt,
            slide.fact_claim,
        ]
    ).lower()
    return any(marker in text for marker in DISASTER_TOPIC_MARKERS)


def _disaster_camera_direction(slide: CarouselSlide) -> str:
    directions = {
        1: (
            "Camera shot: wide cinematic establishing shot, flooded coast or downtown at dawn, "
            "clear impossible scale, roads already disappearing."
        ),
        2: (
            "Camera shot: street-level survival perspective, people moving through waist-deep water, "
            "abandoned cars partly submerged, urgent but realistic."
        ),
        3: (
            "Camera shot: interior human-scale consequence, dim apartment or stairwell during power failure, "
            "flashlights, water at the doorway, no melodrama."
        ),
        4: (
            "Camera shot: infrastructure and hidden consequence, damaged water plant, flooded subway entrance, "
            "emergency pipes, bottled water scarcity, practical detail."
        ),
        5: (
            "Camera shot: close-up emotional survival detail, single survivor seen from behind looking at flooded skyline "
            "or a hand holding an emergency radio above floodwater."
        ),
    }
    return directions.get(slide.slide_number, "Camera shot: distinct documentary angle that avoids repeating the previous flooded city composition.")


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            result.append(value.strip())
            seen.add(key)
    return result


def _remove_text_inviting_terms(value: str) -> str:
    clean = value
    for term, replacement in TEXT_INVITING_TERMS.items():
        clean = clean.replace(term, replacement)
        clean = clean.replace(term.title(), replacement)
    return clean


def _clean_disaster_scene_prompt(value: str, disaster: bool) -> str:
    if not disaster:
        return value
    replacements = {
        "text-safe dark negative space in the lower third": "natural low-detail image area near the lower edge",
        "dark negative space in the lower third": "natural low-detail image area near the lower edge",
        "dark lower third": "natural textured lower edge",
        "text-safe dark negative space": "natural low-detail image area",
    }
    clean = value
    for old, new in replacements.items():
        clean = clean.replace(old, new)
        clean = clean.replace(old.title(), new)
    return clean


def _clean_prompt(prompt: str, max_length: int) -> str:
    clean = " ".join(prompt.strip().split())
    if len(clean) <= max_length:
        return clean
    return clean[: max_length - 1].rstrip(" ,.;") + "."
