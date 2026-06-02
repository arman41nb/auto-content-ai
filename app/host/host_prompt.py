"""Prompt helpers for fictional host image generation."""

from __future__ import annotations

from app.host.host_profile import HostProfile


def build_host_reference_prompt(host: HostProfile, variant: int = 1) -> str:
    angle = "front-facing medium portrait" if variant == 1 else "three-quarter medium portrait"
    return (
        f"{host.image_prompt_base}, {angle}, calm intelligent expression, cinematic creator studio lighting, "
        "consistent wardrobe, same fictional person, vertical 9:16 composition, no text, no logos, no watermark. "
        f"Negative prompt: {host.negative_prompt}"
    )


def build_host_scene_prompt(host: HostProfile, visual_goal: str, scene_number: int) -> str:
    framing = "waist-up host in modern educational studio" if scene_number == 1 else "host beside a clean abstract explainer wall"
    return (
        f"{host.image_prompt_base}, {framing}, {visual_goal}, warm but precise delivery, "
        "professional newsroom and educational creator vibe, vertical 9:16 cinematic frame, "
        "image-only background, no text, no logos, no watermark, no celebrity resemblance. "
        f"Negative prompt: {host.negative_prompt}"
    )
