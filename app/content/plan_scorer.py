"""Rule-based scoring for valid carousel plans."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.content.schemas import (
    CAPTION_TARGET_MAX_WORDS,
    CAPTION_TARGET_MIN_WORDS,
    CarouselPlan,
    count_words,
)


SCIENCE_UNCERTAINTY_MARKERS = (
    "may",
    "could",
    "might",
    "scientists think",
    "researchers suggest",
    "one possible explanation",
    "appears to",
    "is thought to",
)
FUTURE_SPECULATION_MARKERS = ("what if", "could", "might", "may", "in this scenario", "speculative")
GENERIC_CTA_PHRASES = ("learn more", "discover", "explore", "share your thoughts", "save for more")
CONCRETE_WORDS = (
    "smoke",
    "bread",
    "street",
    "bath",
    "glass",
    "rain",
    "wind",
    "heat",
    "market",
    "room",
    "door",
    "dust",
    "water",
    "ocean",
    "river",
    "road",
    "power",
    "radio",
    "tap",
    "infrastructure",
    "marble",
    "planet",
    "surface",
    "crowd",
)
HOOK_WORDS = (
    "wrong",
    "survive",
    "hidden",
    "danger",
    "violent",
    "impossible",
    "cramped",
    "smoke",
    "glass",
    "last",
    "truth",
    "cost",
)


@dataclass(frozen=True)
class PlanScore:
    score: int
    breakdown: dict[str, int]
    notes: list[str]

    def as_dict(self) -> dict[str, object]:
        return {"score": self.score, "breakdown": self.breakdown, "notes": self.notes}


def score_plan(plan: CarouselPlan) -> PlanScore:
    """Score a validated plan from 0 to 100 without extra LLM calls."""

    breakdown: dict[str, int] = {}
    notes: list[str] = []
    breakdown["slide_1_hook_strength"] = _score_hook(plan, notes)
    breakdown["headline_specificity"] = _score_headlines(plan, notes)
    breakdown["concrete_visual_detail"] = _score_visual_detail(plan, notes)
    breakdown["selected_pattern_present"] = _score_selected_pattern(plan, notes)
    breakdown["content_angle_clarity"] = _score_content_angle(plan, notes)
    breakdown["caption_quality"] = _score_caption(plan, notes)
    breakdown["uncertainty_language"] = _score_uncertainty(plan, notes)
    breakdown["non_generic_cta"] = _score_cta(plan, notes)
    breakdown["image_prompt_quality"] = _score_image_prompts(plan, notes)
    total = max(0, min(100, sum(breakdown.values())))
    return PlanScore(score=total, breakdown=breakdown, notes=notes)


def _score_hook(plan: CarouselPlan, notes: list[str]) -> int:
    if not plan.slides:
        notes.append("No slides available for hook scoring.")
        return 0
    first = plan.slides[0]
    text = f"{first.headline} {first.subtext}".lower()
    score = 5
    if count_words(first.headline) <= 8:
        score += 2
    if any(word in text for word in HOOK_WORDS):
        score += 4
    if "?" in text or any(word in text for word in ("but", "until", "before", "wrong")):
        score += 2
    if _has_concrete_language(text):
        score += 2
    if score < 10:
        notes.append("Slide 1 hook could use more concrete tension.")
    return min(score, 15)


def _score_headlines(plan: CarouselPlan, notes: list[str]) -> int:
    if not plan.slides:
        return 0
    specific_count = 0
    for slide in plan.slides:
        text = slide.headline.lower()
        if _has_concrete_language(text) or count_words(slide.headline) >= 4:
            specific_count += 1
    score = round(15 * specific_count / len(plan.slides))
    if score < 11:
        notes.append("Several headlines read generic or label-like.")
    return score


def _score_visual_detail(plan: CarouselPlan, notes: list[str]) -> int:
    if not plan.slides:
        return 0
    detailed = 0
    for slide in plan.slides:
        text = f"{slide.visual_goal} {slide.image_prompt}".lower()
        if _has_concrete_language(text) and count_words(text) >= 14:
            detailed += 1
    score = round(15 * detailed / len(plan.slides))
    if score < 11:
        notes.append("Visual goals or prompts need more tangible scene detail.")
    return score


def _score_selected_pattern(plan: CarouselPlan, notes: list[str]) -> int:
    value = plan.selected_pattern.strip().lower()
    if value and value not in {"selected pattern", "exact selected pattern name", "pattern name", "none"}:
        return 10
    notes.append("selected_pattern is missing or placeholder-like.")
    return 0


def _score_content_angle(plan: CarouselPlan, notes: list[str]) -> int:
    words = count_words(plan.content_angle)
    score = 0
    if words >= 8:
        score += 4
    if plan.topic.lower().split()[0] in plan.content_angle.lower():
        score += 2
    if _has_concrete_language(plan.content_angle.lower()):
        score += 2
    if "." in plan.content_angle or words <= 28:
        score += 2
    if score < 7:
        notes.append("content_angle could be clearer and more topic-specific.")
    return min(score, 10)


def _score_caption(plan: CarouselPlan, notes: list[str]) -> int:
    caption = plan.caption.strip()
    words = count_words(caption)
    score = 0
    if CAPTION_TARGET_MIN_WORDS <= words <= CAPTION_TARGET_MAX_WORDS:
        score += 5
    elif words >= 40:
        score += 2
    if caption.count("\n") >= 4:
        score += 3
    if "?" in caption:
        score += 2
    if any(marker in caption.lower() for marker in ("save", "follow")):
        score += 2
    if _has_concrete_language(caption.lower()):
        score += 3
    if score < 11:
        notes.append("Caption is valid but could be more Instagram-native.")
    return min(score, 15)


def _score_uncertainty(plan: CarouselPlan, notes: list[str]) -> int:
    niche = plan.niche.strip().lower()
    text = f"{plan.caption} {plan.content_angle} " + " ".join(slide.fact_claim for slide in plan.slides)
    lower = text.lower()
    if niche == "science":
        if any(marker in lower for marker in SCIENCE_UNCERTAINTY_MARKERS):
            return 5
        notes.append("Science plan lacks uncertainty language.")
        return 0
    if niche == "future":
        if any(marker in lower for marker in FUTURE_SPECULATION_MARKERS):
            return 5
        notes.append("Future plan lacks speculative framing.")
        return 0
    return 5


def _score_cta(plan: CarouselPlan, notes: list[str]) -> int:
    final_text = ""
    if plan.slides:
        final = plan.slides[-1]
        final_text = f"{final.headline} {final.subtext}"
    text = f"{final_text} {plan.caption}".lower()
    if any(phrase in text for phrase in GENERIC_CTA_PHRASES):
        notes.append("CTA uses generic engagement language.")
        return 1
    if any(marker in text for marker in ("would you", "could you", "comment", "save this", "send this")):
        return 5
    if "?" in text and any(marker in text for marker in ("save", "follow")):
        return 4
    notes.append("CTA could be more specific.")
    return 2


def _score_image_prompts(plan: CarouselPlan, notes: list[str]) -> int:
    if not plan.slides:
        return 0
    strong = 0
    for slide in plan.slides:
        prompt = slide.image_prompt.lower()
        if (
            "cinematic" in prompt
            and "vertical" in prompt
            and "no text" in prompt
            and any(marker in prompt for marker in ("text-safe", "negative space", "safe area"))
            and _has_concrete_language(prompt)
        ):
            strong += 1
    score = round(10 * strong / len(plan.slides))
    if score < 8:
        notes.append("Some image prompts are missing cinematic, vertical, no-text, or scene detail.")
    return score


def _has_concrete_language(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9\s]", " ", value.lower())
    return any(word in normalized.split() for word in CONCRETE_WORDS)
