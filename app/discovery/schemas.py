"""Pydantic schemas for topic discovery."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


DiscoveryLane = Literal["what_if_disaster", "extreme_science", "future_scenario", "any"]


class TopicCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(..., min_length=1)
    niche: str = Field(..., min_length=1)
    lane: DiscoveryLane = "any"
    angle: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    source_url: str | None = None
    source_title: str | None = None
    source_summary: str | None = None
    keywords: list[str] = Field(default_factory=list)
    visual_shock_score: float = 0.0
    curiosity_gap_score: float = 0.0
    dm_share_potential: float = 0.0
    watch_retention_potential: float = 0.0
    cold_audience_fit: float = 0.0
    first_second_clarity: float = 0.0
    score: float = 0.0
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @field_validator("topic", "niche", "angle", "source")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("lane", mode="before")
    @classmethod
    def normalize_lane(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().lower()
        return value

    @field_validator("source_url", "source_title", "source_summary")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(value.strip().split())
        return cleaned or None

    @field_validator("keywords", "reasons", "warnings")
    @classmethod
    def normalize_string_lists(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            cleaned = " ".join(str(value).strip().split())
            if cleaned and cleaned not in normalized:
                normalized.append(cleaned)
        return normalized
