"""Schemas and adapters for mascot story explainer Reels."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.content.reel_schemas import ReelPlan, ReelScene
from app.content.schemas import CarouselPlan, CarouselSlide, count_words


MascotSceneRole = Literal["hook", "question", "analogy", "mechanism", "example", "twist", "takeaway"]
MascotVisualType = Literal["mascot_ai", "broll_video", "broll_photo", "chart_motion", "object_scene_ai", "mixed"]


class MascotStoryScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_number: int = Field(..., ge=1, le=9)
    role: MascotSceneRole
    duration_target: float = Field(..., ge=2.0, le=4.8)
    visual_type: MascotVisualType
    visual_goal: str = Field(..., min_length=1, max_length=520)
    mascot_action: str = Field(default="", max_length=220)
    setting: str = Field(..., min_length=1, max_length=220)
    media_query: str = Field(..., min_length=1, max_length=180)
    voiceover_line: str = Field(..., min_length=1, max_length=260)
    on_screen_caption: str = Field(..., min_length=1, max_length=80)
    key_words: list[str] = Field(default_factory=list, max_length=8)
    required_visual_elements: list[str] = Field(default_factory=list, max_length=8)
    forbidden_visual_elements: list[str] = Field(default_factory=list, max_length=8)
    fact_claim: str = Field(default="", max_length=500)
    source_needed: bool = False
    emotion: str = Field(default="curious", max_length=40)

    @field_validator(
        "visual_goal",
        "mascot_action",
        "setting",
        "media_query",
        "voiceover_line",
        "on_screen_caption",
        "fact_claim",
        "emotion",
    )
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

    @field_validator("on_screen_caption")
    @classmethod
    def on_screen_is_short(cls, value: str) -> str:
        if count_words(value) > 4:
            raise ValueError("on_screen_caption must be 4 words or fewer.")
        return value.upper()


class MascotStoryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(..., min_length=1, max_length=160)
    niche: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=180)
    story_angle: str = Field(..., min_length=1, max_length=260)
    audience: str = Field(..., min_length=1, max_length=220)
    core_question: str = Field(..., min_length=1, max_length=180)
    simple_answer: str = Field(..., min_length=1, max_length=320)
    analogy: str = Field(..., min_length=1, max_length=320)
    caveat: str = Field(..., min_length=1, max_length=420)
    caption: str = Field(..., min_length=40, max_length=2200)
    hashtags: list[str] = Field(..., min_length=1, max_length=30)
    mascot_id: str = Field(default="miko", min_length=1, max_length=80)
    scenes: list[MascotStoryScene] = Field(..., min_length=7, max_length=9)

    @model_validator(mode="after")
    def validate_story_shape(self) -> "MascotStoryPlan":
        expected = list(range(1, len(self.scenes) + 1))
        actual = [scene.scene_number for scene in self.scenes]
        if actual != expected:
            raise ValueError(f"Scene numbers must be consecutive. Got {actual}.")
        total = sum(scene.duration_target for scene in self.scenes)
        if not 22 <= total <= 35:
            raise ValueError(f"Mascot story Reel duration must be 22-35 seconds. Got {total:.1f}.")
        mascot_count = sum(1 for scene in self.scenes if scene.visual_type in {"mascot_ai", "mixed"})
        if mascot_count < 2:
            raise ValueError("Mascot must appear in at least 2 scenes.")
        if not any(scene.visual_type == "chart_motion" for scene in self.scenes):
            raise ValueError("At least one motion infographic scene is required.")
        if not any(scene.visual_type == "object_scene_ai" for scene in self.scenes):
            raise ValueError("At least one visual analogy or object scene is required.")
        script_words = count_words(self.voiceover_script)
        if not 55 <= script_words <= 115:
            raise ValueError(f"Mascot story voiceover should be 55-115 words. Got {script_words}.")
        return self

    @property
    def voiceover_script(self) -> str:
        return " ".join(scene.voiceover_line for scene in self.scenes)


def mascot_story_plan_to_reel_plan(plan: MascotStoryPlan) -> ReelPlan:
    return ReelPlan(
        topic=plan.topic,
        niche=plan.niche,
        title=plan.title,
        cover_text=_cover_text(plan.topic),
        scenes=[
            ReelScene(
                scene_number=scene.scene_number,
                duration_seconds=scene.duration_target,
                visual_prompt=scene.visual_goal,
                on_screen_text=scene.on_screen_caption,
                voiceover_line=scene.voiceover_line,
                camera_motion="fast educational micro push with animated caption-safe framing",
                transition="cut",
            )
            for scene in plan.scenes
        ],
    )


def mascot_story_plan_to_carousel_plan(plan: MascotStoryPlan) -> CarouselPlan:
    role_map = {
        "hook": "hook",
        "question": "setup",
        "analogy": "fact",
        "mechanism": "fact",
        "example": "twist",
        "twist": "twist",
        "takeaway": "final",
    }
    slides = [
        CarouselSlide(
            slide_number=scene.scene_number,
            role=role_map[scene.role],  # type: ignore[arg-type]
            tag=scene.role,
            headline=scene.on_screen_caption,
            subtext="",
            visual_goal=scene.visual_goal,
            image_prompt=scene.visual_goal,
            text_position="bottom_left",
            composition_hint="full-screen 9:16 mascot story Reel frame with clean caption-safe lower third",
            fact_claim=scene.fact_claim or scene.voiceover_line,
            needs_fact_check=scene.source_needed,
        )
        for scene in plan.scenes
    ]
    return CarouselPlan(
        topic=plan.topic,
        niche=plan.niche,
        title=plan.title,
        selected_pattern="mascot_story_explainer",
        content_angle=plan.story_angle,
        target_audience=plan.audience,
        tone="charming, useful, story-based, premium viral educational Reel",
        caption=plan.caption,
        hashtags=plan.hashtags,
        slides=slides,
    )


def _cover_text(topic: str) -> str:
    words = [word.upper() for word in re.findall(r"[A-Za-z0-9]+", topic) if word.lower() not in {"what", "is", "the"}]
    return " ".join(words[:4]) or "EXPLAINED"
