"""Professional still-image motion rules for editorial Reels."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image


REEL_SIZE = (1080, 1920)


@dataclass(frozen=True)
class MotionPreset:
    name: str
    scale_start: float
    scale_end: float
    x_start: float = 0.0
    x_end: float = 0.0
    y_start: float = 0.0
    y_end: float = 0.0
    transition: str = "clean_cut"
    artificial_motion: bool = False
    description: str = ""

    @property
    def scale_delta(self) -> float:
        return abs(self.scale_end - self.scale_start)


MOTION_PRESETS: dict[str, MotionPreset] = {
    "static_hold": MotionPreset(
        name="static_hold",
        scale_start=1.0,
        scale_end=1.0,
        description="No camera move; lets strong real-world composition and captions carry the scene.",
    ),
    "subtle_push": MotionPreset(
        name="subtle_push",
        scale_start=1.0,
        scale_end=1.025,
        artificial_motion=True,
        description="Small importance push, capped under three percent and never used as a repeating default.",
    ),
    "subtle_pull": MotionPreset(
        name="subtle_pull",
        scale_start=1.025,
        scale_end=1.0,
        artificial_motion=True,
        description="Rare context reveal with a capped pull-back.",
    ),
    "lateral_drift": MotionPreset(
        name="lateral_drift",
        scale_start=1.018,
        scale_end=1.018,
        x_start=-0.010,
        x_end=0.010,
        artificial_motion=True,
        description="Small two-percent-or-less frame drift for wide stills; no visible zoom ramp.",
    ),
    "subject_locked_hold": MotionPreset(
        name="subject_locked_hold",
        scale_start=1.008,
        scale_end=1.008,
        description="Slight cinematic crop only; holds when the subject already fills the frame.",
    ),
    "documentary_cut": MotionPreset(
        name="documentary_cut",
        scale_start=1.0,
        scale_end=1.0,
        transition="soft_cut_4_frames",
        description="Restrained real-world cut with no artificial camera movement.",
    ),
    "infographic_reveal": MotionPreset(
        name="infographic_reveal",
        scale_start=1.0,
        scale_end=1.0,
        description="Infographic energy should come from captions or graphic layers, not full-frame zoom.",
    ),
    "micro_parallax": MotionPreset(
        name="micro_parallax",
        scale_start=1.012,
        scale_end=1.012,
        x_start=-0.006,
        x_end=0.006,
        y_start=0.004,
        y_end=-0.004,
        artificial_motion=True,
        description="Reserved for true layered assets; not faked for ordinary stills.",
    ),
}


BANNED_MOTION_DEFAULTS = {
    "automatic_alternating_zoom",
    "scale_change_above_three_percent_for_stills",
    "same_preset_repeated_across_all_scenes",
    "fake_movement_zoom",
    "dramatic_pan_zoom_every_slide",
    "random_motion_unrelated_to_narration",
}


def preset(name: str) -> MotionPreset:
    return MOTION_PRESETS.get(name, MOTION_PRESETS["static_hold"])


def motion_entry_from_preset(name: str, **overrides: Any) -> dict[str, Any]:
    base = preset(name)
    entry = {
        "selected_motion_preset": base.name,
        "scale_start": base.scale_start,
        "scale_end": base.scale_end,
        "x_motion": {"start": base.x_start, "end": base.x_end, "unit": "frame_ratio"},
        "y_motion": {"start": base.y_start, "end": base.y_end, "unit": "frame_ratio"},
        "transition_in": "clean_cut",
        "transition_out": base.transition,
        "artificial_motion": base.artificial_motion,
        "preset_description": base.description,
    }
    entry.update(overrides)
    return entry


def compose_motion_background(
    image_path: Path,
    motion: dict[str, Any] | None,
    progress: float,
    size: tuple[int, int] = REEL_SIZE,
) -> Image.Image:
    with Image.open(image_path) as source:
        base = cover_crop(source.convert("RGB"), size)

    motion_dict = motion if isinstance(motion, dict) else {}
    scale_start = _float(motion_dict.get("scale_start"), 1.0)
    scale_end = _float(motion_dict.get("scale_end"), scale_start)
    progress = max(0.0, min(1.0, progress))
    scale = max(1.0, _lerp(scale_start, scale_end, progress))
    x_motion = _motion_axis(motion_dict.get("x_motion"), progress)
    y_motion = _motion_axis(motion_dict.get("y_motion"), progress)
    scale = max(scale, 1.0 + min(0.02, abs(x_motion)) + min(0.02, abs(y_motion)))

    zoomed = base.resize((int(size[0] * scale), int(size[1] * scale)), Image.Resampling.LANCZOS)
    max_x = max(0, zoomed.width - size[0])
    max_y = max(0, zoomed.height - size[1])
    x = _clamp_int(-max_x // 2 + int(x_motion * size[0]), -max_x, 0)
    y = _clamp_int(-max_y // 2 + int(y_motion * size[1]), -max_y, 0)
    canvas = Image.new("RGBA", size, (0, 0, 0, 255))
    canvas.alpha_composite(zoomed.convert("RGBA"), (x, y))
    return canvas


def cover_crop(image: Image.Image, size: tuple[int, int] = REEL_SIZE) -> Image.Image:
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def motion_scale_delta(scene: dict[str, Any]) -> float:
    return abs(_float(scene.get("scale_end"), 1.0) - _float(scene.get("scale_start"), 1.0))


def _motion_axis(value: Any, progress: float) -> float:
    if isinstance(value, dict):
        return _lerp(_float(value.get("start"), 0.0), _float(value.get("end"), 0.0), progress)
    return _float(value, 0.0)


def _lerp(start: float, end: float, progress: float) -> float:
    return start + (end - start) * progress


def _float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _clamp_int(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))
