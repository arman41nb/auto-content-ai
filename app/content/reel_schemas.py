"""Schemas and deterministic story plans for native Reel output."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.content.schemas import CarouselPlan, CarouselSlide, count_words


SceneTransition = Literal["cut", "fade"]


class ReelScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_number: int = Field(..., ge=1, le=5)
    duration_seconds: float = Field(..., ge=1.4, le=3.0)
    visual_prompt: str = Field(..., min_length=1, max_length=1000)
    on_screen_text: str = Field(..., min_length=1, max_length=80)
    voiceover_line: str = Field(..., min_length=1, max_length=180)
    camera_motion: str = Field(..., min_length=1, max_length=180)
    transition: SceneTransition = "cut"

    @field_validator("visual_prompt", "on_screen_text", "voiceover_line", "camera_motion")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("on_screen_text")
    @classmethod
    def on_screen_text_is_minimal(cls, value: str) -> str:
        if count_words(value) > 5:
            raise ValueError("on_screen_text must be 5 words or fewer.")
        if "#" in value:
            raise ValueError("on_screen_text must not include hashtags.")
        return value.upper()

    @field_validator("voiceover_line")
    @classmethod
    def voiceover_is_clean(cls, value: str) -> str:
        lower = value.lower()
        if "#" in value:
            raise ValueError("voiceover_line must not include hashtags.")
        if "follow for more" in lower:
            raise ValueError("voiceover_line must not include follow-for-more language.")
        if re.search(r"[^\x00-\x7F]", value):
            raise ValueError("voiceover_line must be English-only ASCII text.")
        return value


class ReelPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(..., min_length=1, max_length=160)
    niche: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=160)
    cover_text: str = Field(..., min_length=1, max_length=80)
    scenes: list[ReelScene] = Field(..., min_length=5, max_length=5)

    @field_validator("topic", "niche", "title", "cover_text")
    @classmethod
    def normalize_string(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @model_validator(mode="after")
    def validate_story_shape(self) -> "ReelPlan":
        actual = [scene.scene_number for scene in self.scenes]
        if actual != [1, 2, 3, 4, 5]:
            raise ValueError(f"Scene numbers must be 1..5. Got {actual}.")
        total_duration = sum(scene.duration_seconds for scene in self.scenes)
        if not 8.0 <= total_duration <= 12.0:
            raise ValueError(f"Total duration must be 8-12 seconds. Got {total_duration:.1f}.")
        voiceover_words = count_words(" ".join(scene.voiceover_line for scene in self.scenes))
        if not 25 <= voiceover_words <= 45:
            raise ValueError(f"Total voiceover must be 25-45 words. Got {voiceover_words}.")
        return self

    @property
    def voiceover_script(self) -> str:
        return " ".join(scene.voiceover_line for scene in self.scenes)


def deterministic_ocean_reel_plan(niche: str = "science") -> ReelPlan:
    """Return the benchmark native Reel story plan requested for first output."""

    return ReelPlan(
        topic="What if oceans rose overnight?",
        niche=niche,
        title="What if oceans rose overnight?",
        cover_text="IF THE OCEAN MOVED",
        scenes=[
            ReelScene(
                scene_number=1,
                duration_seconds=2.0,
                on_screen_text="THE OCEAN MOVES",
                voiceover_line="What if oceans rose overnight?",
                visual_prompt=(
                    "cinematic documentary still, massive coastal city street suddenly flooded at dawn, "
                    "abandoned cars half submerged, people far in the distance, cold overcast light, "
                    "high realism, no text, no signs, no logos, no watermark, no typography"
                ),
                camera_motion="slow zoom from 100% to 108%, slight left-to-right pan",
                transition="cut",
            ),
            ReelScene(
                scene_number=2,
                duration_seconds=2.0,
                on_screen_text="ROADS VANISH",
                voiceover_line="In the first hours, roads disappear under water.",
                visual_prompt=(
                    "street-level cinematic shot of traffic lights and cars submerged in floodwater, "
                    "empty road becoming a river, realistic documentary lighting, no text, no signs, "
                    "no logos, no watermark, no typography"
                ),
                camera_motion="slow zoom from 100% to 108%, slight right-to-left pan",
                transition="cut",
            ),
            ReelScene(
                scene_number=3,
                duration_seconds=2.0,
                on_screen_text="POWER FAILS",
                voiceover_line="Then power, transport, and clean water start failing.",
                visual_prompt=(
                    "inside a dark apartment with floodwater entering the room, floating household objects, "
                    "emergency flashlight glow, human-scale disaster detail, no text, no signs, no logos, "
                    "no watermark, no typography"
                ),
                camera_motion="slow zoom from 100% to 108%, slight upward pan",
                transition="fade",
            ),
            ReelScene(
                scene_number=4,
                duration_seconds=2.0,
                on_screen_text="NO WAY OUT",
                voiceover_line="The danger is not just drowning. It is being trapped.",
                visual_prompt=(
                    "underground metro entrance flooded, emergency lights reflected in black water, "
                    "blocked escape route, cinematic realism, no text, no signs, no logos, no watermark, "
                    "no typography"
                ),
                camera_motion="slow zoom from 100% to 108%, slight left-to-right pan",
                transition="cut",
            ),
            ReelScene(
                scene_number=5,
                duration_seconds=2.0,
                on_screen_text="WHERE DO YOU GO?",
                voiceover_line="You have one question left: where would you go first?",
                visual_prompt=(
                    "single survivor seen from behind standing on a rooftop above a flooded city, "
                    "distant skyline underwater, quiet cinematic survival moment, no text, no signs, "
                    "no logos, no watermark, no typography"
                ),
                camera_motion="slow zoom from 100% to 108%, slight right-to-left pan",
                transition="fade",
            ),
        ],
    )


def reel_plan_to_carousel_plan(reel_plan: ReelPlan) -> CarouselPlan:
    """Bridge native Reel scenes into the existing image-generation pipeline."""

    slides: list[CarouselSlide] = []
    roles = ["hook", "setup", "fact", "twist", "final"]
    tags = ["HOOK", "IMPACT", "HUMAN", "TRAP", "SURVIVE"]
    for scene, role, tag in zip(reel_plan.scenes, roles, tags):
        slides.append(
            CarouselSlide(
                slide_number=scene.scene_number,
                role=role,  # type: ignore[arg-type]
                tag=tag,
                headline=scene.on_screen_text,
                subtext="",
                visual_goal=scene.visual_prompt,
                image_prompt=scene.visual_prompt,
                text_position="bottom_left",
                composition_hint="full-screen 9:16 cinematic frame with natural low-detail lower edge",
                fact_claim=scene.voiceover_line,
                needs_fact_check=False,
            )
        )
    return CarouselPlan(
        topic=reel_plan.topic,
        niche=reel_plan.niche,
        title=reel_plan.title,
        selected_pattern="native_reel_story",
        content_angle="A tense five-scene survival question about sudden overnight ocean rise.",
        target_audience="Zero-follower cold Instagram viewers who share cinematic what-if scenarios.",
        tone="premium, tense, cinematic, minimal, survival-focused",
        caption=(
            "Imagine waking up to a shoreline that moved into the city overnight.\n\n"
            "The first problem is not dramatic trivia; it is roads disappearing, power failing, "
            "and clean water becoming harder to trust.\n\n"
            "This Reel keeps the question human-scale: what changes first, what traps you, "
            "and where would you move before everyone else tries the same route?\n\n"
            "What would your first decision be?"
        ),
        hashtags=["science", "whatif", "unrealscience"],
        slides=slides,
    )
