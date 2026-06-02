"""Prompt builders for mascot scenes."""

from __future__ import annotations

from app.mascot.mascot_profile import MascotProfile


def build_mascot_reference_prompt(profile: MascotProfile) -> str:
    return " ".join(
        [
            profile.image_prompt_base,
            "single character reference, full body, centered, plain warm neutral background",
            "rounded soft modern 3D illustration, expressive eyes, brandable silhouette",
            "no text, no letters, no logos, no watermark",
            f"avoid: {profile.negative_prompt}",
        ]
    )


def build_mascot_scene_prompt(profile: MascotProfile, action: str, setting: str, visual_goal: str) -> str:
    return " ".join(
        [
            profile.image_prompt_base,
            f"action: {action}",
            f"setting: {setting}",
            f"scene goal: {visual_goal}",
            "native vertical 9:16 educational Reel frame, clear lower caption-safe area",
            "no text, no letters, no labels, no logos, no watermark",
            f"avoid: {profile.negative_prompt}",
        ]
    )

