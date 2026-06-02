"""Prompt templates for hybrid story explainer planning and image generation."""

from __future__ import annotations

from typing import Any

from app.mascot.mascot_asset_manager import MIKO_NEGATIVE_PROMPT, MIKO_VISUAL_PROMPT
from app.mascot.mascot_profile import MascotProfile


HYBRID_STORY_PLANNER_BRIEF = """
Create an 8-scene Hybrid Story Explainer Reel. Every scene must be a meaningful scene:
real-world context, a concrete proxy situation, cause-effect mechanism, consequence,
contrast, nuance, and takeaway. Miko is a small guide, not the main subject.
Avoid title-card writing, generic role labels, human host close-ups, and financial advice.
"""

HYBRID_MASCOT_NEGATIVE_PROMPT = (
    "giant centered character, toy catalog image, isolated mascot on blank background, stretched character, "
    "cropped face, low quality, flat vector, primitive shapes, text, logo, watermark, PowerPoint slide, "
    "empty background, unrelated props, human presenter"
)


def build_hybrid_scene_image_prompt(
    profile: MascotProfile | None,
    scene: Any,
    scene_number: int,
) -> str:
    """Build a production image prompt for one hybrid scene."""

    base_goal = str(getattr(scene, "ai_scene_prompt", "") or getattr(scene, "visual_objective", ""))
    visual_type = str(getattr(scene, "visual_type", ""))
    mascot_presence = str(getattr(scene, "mascot_presence", "none"))
    share = float(getattr(scene, "mascot_frame_share_target", 0.0) or 0.0)
    required = ", ".join(str(item) for item in getattr(scene, "required_context_objects", []) if str(item).strip())
    forbidden = ", ".join(str(item) for item in getattr(scene, "forbidden_visuals", []) if str(item).strip())

    parts = [
        base_goal,
        f"scene {scene_number}, hybrid story explainer, native 9:16 vertical frame",
        "premium editorial realism, concrete objects, strong composition, subject-first visual storytelling",
        "clean caption-safe lower third, no poster layout, no dominant title card",
        f"required context objects: {required}" if required else "",
    ]
    if mascot_presence != "none" and profile is not None:
        mascot_base = MIKO_VISUAL_PROMPT if profile.mascot_id == "miko" else profile.image_prompt_base
        mascot_negative = MIKO_NEGATIVE_PROMPT if profile.mascot_id == "miko" else profile.negative_prompt
        parts.extend(
            [
                mascot_base,
                f"Miko is a small contextual guide, target frame share {share:.0%}, never the whole content",
                "Miko points to a relevant object such as an invoice, oil barrel, dollar flow, map, wallet, or chart",
                "Miko must be naturally integrated into the scene with correct proportions and no crop",
                f"avoid mascot problems: {mascot_negative}, {HYBRID_MASCOT_NEGATIVE_PROMPT}",
            ]
        )
    else:
        parts.append("no mascot unless the scene explicitly requires one")

    if visual_type == "premium_infographic":
        parts.append("cause-effect infographic should feel editorial and story-integrated, not a dry chart")
    if forbidden:
        parts.append(f"avoid: {forbidden}")
    parts.append("strict image-only rule: no text, no letters, no readable signs, no labels, no logos, no watermark")
    return " ".join(part.strip() for part in parts if part and part.strip())
