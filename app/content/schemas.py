"""Pydantic schemas for carousel plans."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


SlideRole = Literal["hook", "setup", "fact", "twist", "CTA", "final"]
TextPosition = Literal["bottom_left", "center", "top_left"]
MAX_HEADLINE_WORDS = 8
MAX_SUBTEXT_WORDS = 14
CAPTION_HARD_MIN_WORDS = 40
CAPTION_TARGET_MIN_WORDS = 80
CAPTION_TARGET_MAX_WORDS = 140


def count_words(value: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:['-][A-Za-z0-9]+)?", value))


class CarouselSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slide_number: int = Field(..., ge=1)
    role: SlideRole
    tag: str = Field(..., min_length=1, max_length=32)
    headline: str = Field(..., min_length=1, max_length=120)
    subtext: str = Field(default="", max_length=240)
    visual_goal: str = Field(..., min_length=1, max_length=300)
    image_prompt: str = Field(..., min_length=1, max_length=900)
    text_position: TextPosition
    composition_hint: str = Field(..., min_length=1, max_length=300)
    fact_claim: str = Field(default="", max_length=500)
    needs_fact_check: bool = True

    @field_validator("tag")
    @classmethod
    def normalize_tag(cls, value: str) -> str:
        return " ".join(value.strip().upper().split())

    @field_validator("headline", "subtext", "visual_goal", "composition_hint", "fact_claim")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("headline")
    @classmethod
    def headline_must_be_instagram_short(cls, value: str) -> str:
        if count_words(value) > MAX_HEADLINE_WORDS:
            raise ValueError(f"Headline must be {MAX_HEADLINE_WORDS} words or fewer.")
        return value

    @field_validator("subtext")
    @classmethod
    def subtext_must_be_instagram_short(cls, value: str) -> str:
        if value and count_words(value) > MAX_SUBTEXT_WORDS:
            raise ValueError(f"Subtext must be {MAX_SUBTEXT_WORDS} words or fewer.")
        return value

    @field_validator("image_prompt")
    @classmethod
    def image_prompt_must_include_visual_requirements(cls, value: str) -> str:
        clean = " ".join(value.strip().split())
        lower = clean.lower()
        if "cinematic" not in lower:
            clean = f"cinematic realistic style, {clean}"
            lower = clean.lower()
        if "vertical" not in lower:
            clean = f"{clean}, vertical composition"
            lower = clean.lower()
        if not any(phrase in lower for phrase in ("text-safe", "negative space", "safe area")):
            clean = f"{clean}, text-safe negative space for overlay"
        if "no text" not in clean.lower():
            clean = f"{clean}, no text"
        return clean


class CarouselPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(..., min_length=1, max_length=160)
    niche: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=160)
    selected_pattern: str = Field(..., min_length=1, max_length=120)
    content_angle: str = Field(..., min_length=1, max_length=300)
    target_audience: str = Field(..., min_length=1, max_length=220)
    tone: str = Field(..., min_length=1, max_length=160)
    caption: str = Field(..., min_length=1, max_length=2200)
    hashtags: list[str] = Field(..., min_length=1, max_length=30)
    slides: list[CarouselSlide] = Field(..., min_length=1, max_length=20)

    @field_validator(
        "topic",
        "niche",
        "title",
        "selected_pattern",
        "content_angle",
        "target_audience",
        "tone",
        "caption",
    )
    @classmethod
    def normalize_string(cls, value: str) -> str:
        return value.strip()

    @field_validator("hashtags")
    @classmethod
    def normalize_hashtags(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            tag = value.strip().lower().lstrip("#")
            tag = "".join(ch for ch in tag if ch.isalnum() or ch == "_")
            if tag and tag not in normalized:
                normalized.append(tag)
        if not normalized:
            raise ValueError("At least one hashtag is required.")
        return normalized

    @field_validator("caption")
    @classmethod
    def caption_must_be_story_style(cls, value: str) -> str:
        word_count = count_words(value)
        if word_count < CAPTION_HARD_MIN_WORDS:
            raise ValueError(
                f"Caption must be at least {CAPTION_HARD_MIN_WORDS} words. "
                f"Got {word_count}."
            )
        if "#" in value:
            raise ValueError("Caption must not include hashtags.")
        return value

    @model_validator(mode="after")
    def validate_slide_numbers(self) -> "CarouselPlan":
        expected = list(range(1, len(self.slides) + 1))
        actual = [slide.slide_number for slide in self.slides]
        if actual != expected:
            raise ValueError(f"Slide numbers must be sequential starting at 1. Got {actual}.")
        if self.slides and self.slides[0].role != "hook":
            raise ValueError("Slide 1 must use role 'hook'.")
        if len(self.slides) > 1 and self.slides[-1].role not in {"CTA", "final"}:
            raise ValueError("Final slide must use role 'CTA' or 'final'.")
        return self
