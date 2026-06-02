"""Schemas and adapters for hosted explainer Reel plans."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.content.reel_schemas import ReelPlan, ReelScene
from app.content.schemas import CarouselPlan, CarouselSlide, count_words


SceneRole = Literal["hook", "setup", "mechanism", "example", "takeaway"]
VisualType = Literal[
    "host_ai",
    "ai_image",
    "stock_photo",
    "stock_video",
    "wikimedia_image",
    "generated_chart",
    "simple_motion_graphic",
]


class ExplainerScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_number: int = Field(..., ge=1, le=5)
    duration_seconds: float = Field(..., ge=3.0, le=8.0)
    role: SceneRole
    visual_type: VisualType
    visual_goal: str = Field(..., min_length=1, max_length=500)
    media_query: str = Field(..., min_length=1, max_length=180)
    host_line: str = Field(default="", max_length=220)
    voiceover_line: str = Field(..., min_length=1, max_length=260)
    on_screen_text: str = Field(..., min_length=1, max_length=80)
    caption_priority_words: list[str] = Field(default_factory=list, max_length=8)
    fact_claim: str = Field(default="", max_length=500)
    needs_fact_check: bool = False
    source_needed: bool = False

    @field_validator("visual_goal", "media_query", "host_line", "voiceover_line", "on_screen_text", "fact_claim")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("voiceover_line")
    @classmethod
    def voiceover_is_ascii(cls, value: str) -> str:
        if "#" in value:
            raise ValueError("voiceover_line must not include hashtags.")
        if re.search(r"[^\x00-\x7F]", value):
            raise ValueError("voiceover_line must be ASCII English for now.")
        return value

    @field_validator("on_screen_text")
    @classmethod
    def on_screen_is_short(cls, value: str) -> str:
        if count_words(value) > 6:
            raise ValueError("on_screen_text must be 6 words or fewer.")
        return value.upper()


class ExplainerPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(..., min_length=1, max_length=160)
    niche: str = Field(..., min_length=1, max_length=80)
    explainer_angle: str = Field(..., min_length=1, max_length=260)
    target_audience: str = Field(..., min_length=1, max_length=220)
    hook: str = Field(..., min_length=1, max_length=180)
    core_question: str = Field(..., min_length=1, max_length=180)
    simple_answer: str = Field(..., min_length=1, max_length=300)
    key_terms: list[str] = Field(default_factory=list, max_length=10)
    caveats: list[str] = Field(default_factory=list, max_length=8)
    caption: str = Field(..., min_length=40, max_length=2200)
    hashtags: list[str] = Field(..., min_length=1, max_length=30)
    scenes: list[ExplainerScene] = Field(..., min_length=5, max_length=5)

    @model_validator(mode="after")
    def validate_shape(self) -> "ExplainerPlan":
        actual = [scene.scene_number for scene in self.scenes]
        if actual != [1, 2, 3, 4, 5]:
            raise ValueError(f"Scene numbers must be 1..5. Got {actual}.")
        total = sum(scene.duration_seconds for scene in self.scenes)
        if not 20 <= total <= 35:
            raise ValueError(f"Explainer Reel duration must be 20-35 seconds. Got {total:.1f}.")
        host_count = sum(1 for scene in self.scenes if scene.visual_type == "host_ai")
        if not 1 <= host_count <= 2:
            raise ValueError("Host must appear in 1-2 scenes.")
        script_words = count_words(self.voiceover_script)
        if not 45 <= script_words <= 105:
            raise ValueError(f"Explainer voiceover should be 45-105 words. Got {script_words}.")
        return self

    @property
    def voiceover_script(self) -> str:
        return " ".join(scene.voiceover_line for scene in self.scenes)


def explainer_plan_to_reel_plan(plan: ExplainerPlan) -> ReelPlan:
    return ReelPlan(
        topic=plan.topic,
        niche=plan.niche,
        title=plan.core_question,
        cover_text=_cover_text(plan.topic),
        scenes=[
            ReelScene(
                scene_number=scene.scene_number,
                duration_seconds=min(3.0, max(1.4, scene.duration_seconds / 2.3)),
                visual_prompt=scene.visual_goal,
                on_screen_text=scene.on_screen_text,
                voiceover_line=scene.voiceover_line,
                camera_motion="slow educational push-in with subtle lateral pan",
                transition="fade" if scene.scene_number in {2, 4} else "cut",
            )
            for scene in plan.scenes
        ],
    )


def explainer_plan_to_carousel_plan(plan: ExplainerPlan) -> CarouselPlan:
    role_map = {
        "hook": "hook",
        "setup": "setup",
        "mechanism": "fact",
        "example": "twist",
        "takeaway": "final",
    }
    slides: list[CarouselSlide] = []
    for scene in plan.scenes:
        slides.append(
            CarouselSlide(
                slide_number=scene.scene_number,
                role=role_map[scene.role],  # type: ignore[arg-type]
                tag=scene.role,
                headline=scene.on_screen_text,
                subtext="",
                visual_goal=scene.visual_goal,
                image_prompt=scene.visual_goal,
                text_position="bottom_left",
                composition_hint="full-screen 9:16 explainer frame with clean caption-safe lower third",
                fact_claim=scene.fact_claim or scene.voiceover_line,
                needs_fact_check=scene.needs_fact_check,
            )
        )
    return CarouselPlan(
        topic=plan.topic,
        niche=plan.niche,
        title=plan.core_question,
        selected_pattern="explainer_host_reel",
        content_angle=plan.explainer_angle,
        target_audience=plan.target_audience,
        tone="professional, calm, useful, premium short explainer",
        caption=plan.caption,
        hashtags=plan.hashtags,
        slides=slides,
    )


def _cover_text(topic: str) -> str:
    words = [word.upper() for word in re.findall(r"[A-Za-z0-9]+", topic) if word.lower() not in {"what", "is", "the"}]
    return " ".join(words[:5]) or "EXPLAINED"
