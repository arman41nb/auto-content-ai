"""Schemas and adapters for hybrid story explainer Reels."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.content.reel_schemas import ReelPlan, ReelScene
from app.content.schemas import CarouselPlan, CarouselSlide, count_words


HybridSceneRole = Literal[
    "hook",
    "question",
    "setup",
    "mechanism",
    "consequence",
    "contrast",
    "nuance",
    "takeaway",
]
HybridVisualType = Literal[
    "real_world_broll",
    "ai_realistic_scene",
    "mascot_context_scene",
    "mascot_small_overlay",
    "premium_infographic",
    "hybrid_broll_overlay",
    "takeaway_scene",
]
MascotPresence = Literal["none", "small_corner", "side_guide", "interacting", "central_only_if_justified"]
ProxyRole = Literal[
    "none",
    "importer",
    "business_owner",
    "student",
    "curious_friend",
    "market_watcher",
    "shipping_manager",
    "shopper",
]


ROLE_SEQUENCE: tuple[HybridSceneRole, ...] = (
    "hook",
    "question",
    "setup",
    "mechanism",
    "consequence",
    "contrast",
    "nuance",
    "takeaway",
)
REALISTIC_CONTEXT_TYPES = {"real_world_broll", "ai_realistic_scene", "hybrid_broll_overlay", "mascot_context_scene"}
MASCOT_TYPES = {"mascot_context_scene", "mascot_small_overlay", "takeaway_scene"}
GENERIC_LABELS = {
    "HOOK",
    "FIELD NOTE",
    "QUESTION",
    "ANALOGY",
    "MECHANISM",
    "EXAMPLE",
    "TWIST",
    "TAKEAWAY",
    "THE QUESTION",
    "THE LINK",
    "THE TRAP",
    "THE TAKEAWAY",
}


class HybridStoryScene(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_number: int = Field(..., ge=1, le=8)
    role: HybridSceneRole
    duration_target: float = Field(..., ge=2.4, le=5.4)
    narrative_function: str = Field(..., min_length=1, max_length=360)
    voiceover_line: str = Field(..., min_length=1, max_length=300)
    conversational_line_optional: str = Field(default="", max_length=220)
    questioner_line_optional: str = Field(default="", max_length=220)
    mascot_line_optional: str = Field(default="", max_length=220)
    proxy_role_optional: ProxyRole = "none"
    visual_type: HybridVisualType
    media_query: str = Field(..., min_length=1, max_length=220)
    ai_scene_prompt: str = Field(..., min_length=1, max_length=900)
    mascot_presence: MascotPresence = "none"
    mascot_frame_share_target: float = Field(default=0.0, ge=0.0, le=0.65)
    required_context_objects: list[str] = Field(default_factory=list, max_length=10)
    forbidden_visuals: list[str] = Field(default_factory=list, max_length=12)
    caption_text: str = Field(..., min_length=1, max_length=80)
    key_words: list[str] = Field(default_factory=list, max_length=10)
    fact_claim: str = Field(default="", max_length=520)
    source_needed: bool = False
    caveat_required: bool = False
    visual_objective: str = Field(..., min_length=1, max_length=520)
    composition_notes: str = Field(..., min_length=1, max_length=520)
    transition_intent: str = Field(..., min_length=1, max_length=180)

    @field_validator(
        "narrative_function",
        "voiceover_line",
        "conversational_line_optional",
        "questioner_line_optional",
        "mascot_line_optional",
        "media_query",
        "ai_scene_prompt",
        "caption_text",
        "fact_claim",
        "visual_objective",
        "composition_notes",
        "transition_intent",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.strip().split())

    @field_validator("voiceover_line")
    @classmethod
    def voiceover_is_plain_english(cls, value: str) -> str:
        if "#" in value:
            raise ValueError("voiceover_line must not include hashtags.")
        if re.search(r"[^\x00-\x7F]", value):
            raise ValueError("voiceover_line must be ASCII English for now.")
        if any(phrase in value.lower() for phrase in ("let's dive in", "explore", "discover")):
            raise ValueError("voiceover_line uses generic explainer phrasing.")
        return value

    @field_validator("caption_text")
    @classmethod
    def caption_is_short_and_not_debug_label(cls, value: str) -> str:
        clean = " ".join(value.strip().split())
        if count_words(clean) > 8:
            raise ValueError("caption_text must be 8 words or fewer.")
        if clean.upper() in GENERIC_LABELS:
            raise ValueError("caption_text must not be a dominant role/debug label.")
        return clean

    @model_validator(mode="after")
    def validate_mascot_logic(self) -> "HybridStoryScene":
        if self.mascot_presence == "none" and self.visual_type in MASCOT_TYPES:
            raise ValueError("Mascot visual types require mascot_presence.")
        if self.mascot_presence != "none" and self.mascot_frame_share_target <= 0:
            raise ValueError("Mascot scenes need a mascot_frame_share_target.")
        if self.mascot_presence != "central_only_if_justified" and self.mascot_frame_share_target > 0.45:
            raise ValueError("Mascot frame share above 45% requires central_only_if_justified.")
        if not self.required_context_objects:
            raise ValueError("Every hybrid scene needs required_context_objects.")
        return self


class HybridStoryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(..., min_length=1, max_length=160)
    niche: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=180)
    story_angle: str = Field(..., min_length=1, max_length=320)
    audience: str = Field(..., min_length=1, max_length=240)
    core_question: str = Field(..., min_length=1, max_length=180)
    simple_answer: str = Field(..., min_length=1, max_length=360)
    caveat: str = Field(..., min_length=1, max_length=520)
    caption: str = Field(..., min_length=40, max_length=2200)
    hashtags: list[str] = Field(..., min_length=1, max_length=30)
    mascot_id: str = Field(default="miko", min_length=1, max_length=80)
    caption_style: str = Field(default="hybrid_editorial", min_length=1, max_length=80)
    scenes: list[HybridStoryScene] = Field(..., min_length=8, max_length=8)

    @model_validator(mode="after")
    def validate_hybrid_shape(self) -> "HybridStoryPlan":
        expected_numbers = list(range(1, 9))
        actual_numbers = [scene.scene_number for scene in self.scenes]
        if actual_numbers != expected_numbers:
            raise ValueError(f"Scene numbers must be 1-8. Got {actual_numbers}.")
        roles = tuple(scene.role for scene in self.scenes)
        if roles != ROLE_SEQUENCE:
            raise ValueError(f"Hybrid story roles must follow {ROLE_SEQUENCE}. Got {roles}.")
        total = sum(scene.duration_target for scene in self.scenes)
        if not 24 <= total <= 38:
            raise ValueError(f"Hybrid story Reel duration must be 24-38 seconds. Got {total:.1f}.")
        real_context = sum(1 for scene in self.scenes if scene.visual_type in REALISTIC_CONTEXT_TYPES)
        if real_context < 3:
            raise ValueError("At least 3 real-world or realistic context scenes are required.")
        mascot_count = sum(1 for scene in self.scenes if scene.mascot_presence != "none")
        if mascot_count < 2:
            raise ValueError("Miko must appear in at least 2 scenes.")
        central_count = sum(1 for scene in self.scenes if scene.mascot_presence == "central_only_if_justified")
        if central_count > 1:
            raise ValueError("No more than 1 scene may have mascot as the central subject.")
        dominant_count = sum(1 for scene in self.scenes if scene.mascot_frame_share_target > 0.35)
        if dominant_count > 3:
            raise ValueError("No more than 3 scenes may be mascot-dominant.")
        if not any(scene.visual_type == "premium_infographic" for scene in self.scenes):
            raise ValueError("At least 1 premium infographic scene is required.")
        if not any(scene.proxy_role_optional != "none" or scene.questioner_line_optional for scene in self.scenes):
            raise ValueError("At least 1 questioner or proxy scene is required.")
        if not any(scene.role == "contrast" for scene in self.scenes):
            raise ValueError("At least 1 contrast or twist scene is required.")
        script_words = count_words(self.voiceover_script)
        if not 55 <= script_words <= 115:
            raise ValueError(f"Hybrid voiceover should be 55-115 words. Got {script_words}.")
        financial_text = " ".join([self.topic, self.niche, self.caption, self.caveat, self.voiceover_script]).lower()
        if any(term in financial_text for term in ("oil", "dollar", "currency", "economy")):
            if "not financial advice" not in financial_text:
                raise ValueError("Economy topics must include no-financial-advice language.")
            if "indirect" not in financial_text and "context" not in financial_text:
                raise ValueError("Economy topics must describe the relationship as indirect or context-dependent.")
        return self

    @property
    def voiceover_script(self) -> str:
        return " ".join(scene.voiceover_line for scene in self.scenes)


def hybrid_story_plan_to_reel_plan(plan: HybridStoryPlan) -> ReelPlan:
    return ReelPlan(
        topic=plan.topic,
        niche=plan.niche,
        title=plan.title,
        cover_text=_cover_text(plan.topic),
        scenes=[
            ReelScene(
                scene_number=scene.scene_number,
                duration_seconds=scene.duration_target,
                visual_prompt=scene.ai_scene_prompt,
                on_screen_text=scene.caption_text,
                voiceover_line=scene.voiceover_line,
                camera_motion=_camera_motion(scene),
                transition="cut",
            )
            for scene in plan.scenes
        ],
    )


def hybrid_story_plan_to_carousel_plan(plan: HybridStoryPlan) -> CarouselPlan:
    role_map = {
        "hook": "hook",
        "question": "setup",
        "setup": "fact",
        "mechanism": "fact",
        "consequence": "fact",
        "contrast": "twist",
        "nuance": "twist",
        "takeaway": "final",
    }
    slides = [
        CarouselSlide(
            slide_number=scene.scene_number,
            role=role_map[scene.role],  # type: ignore[arg-type]
            tag=_human_label(scene.role),
            headline=scene.caption_text,
            subtext="",
            visual_goal=scene.visual_objective,
            image_prompt=scene.ai_scene_prompt,
            text_position="bottom_left",
            composition_hint=scene.composition_notes,
            fact_claim=scene.fact_claim or scene.voiceover_line,
            needs_fact_check=scene.source_needed,
        )
        for scene in plan.scenes
    ]
    return CarouselPlan(
        topic=plan.topic,
        niche=plan.niche,
        title=plan.title,
        selected_pattern="hybrid_story_explainer",
        content_angle=plan.story_angle,
        target_audience=plan.audience,
        tone="clear, story-led, premium social-first educational explainer",
        caption=plan.caption,
        hashtags=plan.hashtags,
        slides=slides,
    )


def _camera_motion(scene: HybridStoryScene) -> str:
    if scene.visual_type == "premium_infographic":
        return "cause-effect card reveal with clean editorial pacing"
    if scene.visual_type in {"real_world_broll", "hybrid_broll_overlay"}:
        return "subtle documentary push-in with cut on voice beat"
    if scene.mascot_presence != "none":
        return "small mascot guide reaction with subject-first framing"
    return "premium parallax push with concrete object focus"


def _human_label(role: str) -> str:
    return {
        "hook": "The Moment",
        "question": "The Question",
        "setup": "The Setup",
        "mechanism": "The Link",
        "consequence": "The Pressure",
        "contrast": "The Other Side",
        "nuance": "The Catch",
        "takeaway": "The Takeaway",
    }.get(role, "Scene")


def _cover_text(topic: str) -> str:
    words = [word.upper() for word in re.findall(r"[A-Za-z0-9]+", topic) if word.lower() not in {"what", "is", "the"}]
    return " ".join(words[:4]) or "EXPLAINED"
