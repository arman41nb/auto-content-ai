"""Scene-aware editorial motion planning for hostless explainer Reels."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.render.editorial_motion import motion_entry_from_preset, motion_scale_delta


def plan_editorial_motion(
    explainer_plan: Any,
    media_plan: dict[str, Any] | None = None,
    scene_timings: list[dict[str, Any]] | None = None,
    caption_segments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    media_plan = media_plan if isinstance(media_plan, dict) else {}
    media_scenes = _media_scenes_by_number(media_plan)
    timings = _timings_by_number(scene_timings or [])
    caption_load = _caption_load_by_scene(caption_segments or [])
    scenes: list[dict[str, Any]] = []
    previous_preset = ""

    for scene in explainer_plan.scenes:
        scene_number = int(scene.scene_number)
        media_scene = media_scenes.get(scene_number, {})
        source_type = _source_type(media_scene, scene)
        composition = _composition(scene, media_scene)
        selected = _selected_media(media_scene)
        video_clip_available = _video_clip_available(selected)
        preset_name, reason = _choose_preset(
            scene=scene,
            source_type=source_type,
            composition=composition,
            previous_preset=previous_preset,
            video_clip_available=video_clip_available,
        )
        entry = motion_entry_from_preset(preset_name)
        entry.update(
            {
                "scene_number": scene_number,
                "source_type": source_type,
                "scene_role": _scene_role(scene),
                "image_composition": composition,
                "caption_location": "lower_third_safe_zone",
                "focal_point": _focal_point(composition),
                "duration_seconds": _duration_seconds(scene, timings.get(scene_number, {})),
                "transition_in": _transition_in(scene_number, source_type),
                "transition_out": _transition_out(scene_number, len(explainer_plan.scenes), source_type),
                "reason": reason,
                "video_clip_available": video_clip_available,
                "video_clip_path": str(selected.get("local_video_path", "") or ""),
            }
        )
        _apply_caption_motion_load(entry, int(caption_load.get(scene_number, 0)))
        scenes.append(entry)
        previous_preset = str(entry.get("selected_motion_preset", ""))

    transition_plan = [
        {
            "from_scene": int(scene["scene_number"]),
            "to_scene": int(scene["scene_number"]) + 1,
            "transition": scene["transition_out"],
            "reason": _transition_reason(scene),
        }
        for scene in scenes
        if int(scene["scene_number"]) < len(scenes)
    ]
    counts = _scene_counts(scenes)
    return {
        "version": "editorial_motion_v1",
        "template": "editorial_explainer_reel",
        "motion_rules": {
            "obvious_ken_burns_default": False,
            "max_still_scale_delta": 0.035,
            "preferred_photo_presets": ["static_hold", "subject_locked_hold", "lateral_drift"],
            "banned_defaults": [
                "automatic alternating zoom-in / zoom-out",
                "scale changes above 3% for still photos",
                "same motion preset repeated across all scenes",
                "zooming just to create fake movement",
                "dramatic pan/zoom on every slide",
                "random motion unrelated to narration",
            ],
        },
        "scenes": scenes,
        "transition_plan": transition_plan,
        **counts,
    }


def save_editorial_motion_plan(output_dir: Path, motion_plan: dict[str, Any]) -> Path:
    path = output_dir / "editorial_motion_plan.json"
    path.write_text(json.dumps(motion_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    reel_dir = output_dir / "final_reel"
    if reel_dir.exists():
        (reel_dir / "editorial_motion_plan.json").write_text(
            json.dumps(motion_plan, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return path


def edit_beats_from_motion_plan(
    motion_plan: dict[str, Any],
    scene_timings: list[dict[str, Any]],
    caption_segments: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    scenes = motion_plan.get("scenes", [])
    motion_by_scene = {
        int(scene.get("scene_number", 0) or 0): scene
        for scene in scenes
        if isinstance(scene, dict)
    } if isinstance(scenes, list) else {}
    caption_count = _caption_count_by_scene(caption_segments or [])
    beats: list[dict[str, Any]] = []
    for timing in scene_timings:
        if not isinstance(timing, dict):
            continue
        scene_number = int(timing.get("scene_number", 0) or 0)
        motion = motion_by_scene.get(scene_number, {})
        beats.append(
            {
                "scene_number": scene_number,
                "start_seconds": timing.get("start_seconds", 0.0),
                "end_seconds": timing.get("end_seconds", 0.0),
                "transition": motion.get("transition_in", "clean_cut") if scene_number > 1 else "none",
                "transition_out": motion.get("transition_out", "clean_cut"),
                "motion_profile": motion.get("selected_motion_preset", "static_hold"),
                "scale_start": motion.get("scale_start", 1.0),
                "scale_end": motion.get("scale_end", 1.0),
                "caption_count": caption_count.get(scene_number, 0),
                "cut_on_phrase_boundary": True,
                "amateur_motion_risk": motion.get("amateur_motion_risk", "low"),
            }
        )
    return beats


def _choose_preset(
    scene: Any,
    source_type: str,
    composition: str,
    previous_preset: str,
    video_clip_available: bool,
) -> tuple[str, str]:
    role = _scene_role(scene)
    if source_type == "pexels_video":
        return (
            "static_hold",
            "Use actual Pexels clip motion when available; do not add fake zoom to a video scene."
            if video_clip_available
            else "Pexels provided a video result but only a still poster is local, so hold the frame instead of faking camera motion.",
        )
    if source_type == "infographic":
        return "infographic_reveal", "Mechanism/takeaway scene should reveal information with caption or graphic elements, not full-frame zoom."
    if source_type == "ai_fallback":
        if role in {"hook", "takeaway"} and previous_preset != "subtle_push":
            return "subtle_push", "AI fallback gets only a capped importance push because the composition needs a little life."
        return "static_hold", "AI fallback motion is minimized to avoid artificial slideshow energy."
    if composition == "wide_shot" and role not in {"takeaway"} and previous_preset != "lateral_drift":
        return "lateral_drift", "Wide real-world photo gets a small lateral drift instead of a zoom ramp."
    if composition in {"close_up", "object_detail", "document"}:
        return "subject_locked_hold", "The subject already fills the frame, so lock the image and let captions provide rhythm."
    if role == "takeaway":
        return "static_hold", "Takeaway should feel calm and conclusive."
    if previous_preset != "static_hold":
        return "static_hold", "Strong real-world still can hold without fake movement."
    return "subject_locked_hold", "Adjacent repetition avoided while keeping movement nearly static."


def _apply_caption_motion_load(entry: dict[str, Any], caption_motion_load_score: int) -> None:
    image_load = _image_motion_load(entry)
    combined = image_load + caption_motion_load_score + _transition_load(str(entry.get("transition_out", "")))
    if combined > 58 and str(entry.get("selected_motion_preset", "")) in {"subtle_push", "subtle_pull"}:
        replacement = motion_entry_from_preset("static_hold")
        entry.update(
            {
                "selected_motion_preset": replacement["selected_motion_preset"],
                "scale_start": replacement["scale_start"],
                "scale_end": replacement["scale_end"],
                "x_motion": replacement["x_motion"],
                "y_motion": replacement["y_motion"],
                "artificial_motion": replacement["artificial_motion"],
                "reason": str(entry.get("reason", "")) + " Caption motion is active, so background motion was reduced.",
            }
        )
        image_load = _image_motion_load(entry)
        combined = image_load + caption_motion_load_score + _transition_load(str(entry.get("transition_out", "")))
    entry["caption_motion_load_score"] = caption_motion_load_score
    entry["combined_motion_load_score"] = combined
    entry["amateur_motion_risk"] = _amateur_motion_risk(entry, combined)


def _image_motion_load(entry: dict[str, Any]) -> int:
    preset = str(entry.get("selected_motion_preset", ""))
    scale_load = round(motion_scale_delta(entry) * 1000)
    pan_load = _axis_load(entry.get("x_motion")) + _axis_load(entry.get("y_motion"))
    if preset in {"static_hold", "subject_locked_hold", "infographic_reveal", "documentary_cut"}:
        return min(12, scale_load + pan_load)
    return min(34, scale_load + pan_load + 8)


def _axis_load(value: Any) -> int:
    if not isinstance(value, dict):
        return 0
    try:
        return round(abs(float(value.get("end", 0.0)) - float(value.get("start", 0.0))) * 500)
    except (TypeError, ValueError):
        return 0


def _transition_load(name: str) -> int:
    return 2 if name in {"clean_cut", "none"} else 5 if name == "soft_cut_4_frames" else 14


def _amateur_motion_risk(entry: dict[str, Any], combined: int) -> str:
    if motion_scale_delta(entry) > 0.035 or combined > 72:
        return "high"
    if motion_scale_delta(entry) > 0.025 or combined > 58:
        return "medium"
    return "low"


def _source_type(media_scene: dict[str, Any], scene: Any) -> str:
    selected = _selected_media(media_scene)
    provider = str(selected.get("provider", media_scene.get("selected_source_type", "")) or "").lower()
    media_type = str(selected.get("media_type", media_scene.get("scene_type", "")) or "").lower()
    visual_type = str(getattr(scene, "visual_type", "")).lower()
    if provider == "pexels" and "video" in media_type:
        return "pexels_video"
    if provider == "pexels":
        return "pexels_photo"
    if provider == "premium_infographic" or visual_type == "premium_infographic" or "chart" in media_type:
        return "infographic"
    if provider in {"ai_generated", "ai_fallback", "fallback"} or visual_type == "ai_image":
        return "ai_fallback"
    return provider or visual_type or "unknown"


def _composition(scene: Any, media_scene: dict[str, Any]) -> str:
    selected = _selected_media(media_scene)
    text = " ".join(
        [
            str(getattr(scene, "visual_goal", "")),
            str(getattr(scene, "media_query", "")),
            str(selected.get("title", "")),
        ]
    ).lower()
    if any(term in text for term in ("chart", "infographic", "summary card", "diagram", "arrow")):
        return "chart"
    if any(term in text for term in ("document", "receipt", "invoice", "paper", "contract")):
        return "document"
    if any(term in text for term in ("close-up", "close up", "detail", "bill", "barrel", "pump")):
        return "object_detail"
    if any(term in text for term in ("ship", "port", "container", "refinery", "tower", "logistics", "wide", "ocean")):
        return "wide_shot"
    return "close_up"


def _focal_point(composition: str) -> str:
    if composition == "wide_shot":
        return "upper_middle_subject_safe_lower_third"
    if composition in {"object_detail", "close_up", "document"}:
        return "center_subject_locked"
    if composition == "chart":
        return "graphic_center"
    return "center"


def _transition_in(scene_number: int, source_type: str) -> str:
    if scene_number == 1:
        return "none"
    if source_type == "infographic":
        return "clean_cut"
    return "clean_cut"


def _transition_out(scene_number: int, scene_count: int, source_type: str) -> str:
    if scene_number >= scene_count:
        return "none"
    if source_type == "infographic":
        return "soft_cut_4_frames"
    return "clean_cut"


def _transition_reason(scene: dict[str, Any]) -> str:
    if scene.get("transition_out") == "soft_cut_4_frames":
        return "Short restrained soft cut out of explanatory graphic; no slideshow fade."
    return "Clean editorial cut; avoids flashy or repeated slideshow transitions."


def _scene_counts(scenes: list[dict[str, Any]]) -> dict[str, int]:
    video_count = sum(1 for scene in scenes if scene.get("source_type") == "pexels_video" and scene.get("video_clip_available"))
    photo_count = sum(1 for scene in scenes if scene.get("source_type") == "pexels_photo")
    artificial = sum(1 for scene in scenes if bool(scene.get("artificial_motion", False)))
    return {
        "video_clips_used_count": video_count,
        "photo_scenes_count": photo_count,
        "artificial_motion_scenes_count": artificial,
    }


def _caption_load_by_scene(caption_segments: list[dict[str, Any]]) -> dict[int, int]:
    counts = _caption_count_by_scene(caption_segments)
    load: dict[int, int] = {}
    for scene_number, count in counts.items():
        load[scene_number] = min(44, 10 + count * 6)
    return load


def _caption_count_by_scene(caption_segments: list[dict[str, Any]]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for segment in caption_segments:
        if not isinstance(segment, dict):
            continue
        scene_number = int(segment.get("scene_number", 0) or 0)
        if scene_number > 0:
            counts[scene_number] = counts.get(scene_number, 0) + 1
    return counts


def _media_scenes_by_number(media_plan: dict[str, Any]) -> dict[int, dict[str, Any]]:
    scenes = media_plan.get("scenes", [])
    if not isinstance(scenes, list):
        return {}
    result: dict[int, dict[str, Any]] = {}
    for scene in scenes:
        if isinstance(scene, dict):
            scene_number = int(scene.get("scene_number", 0) or 0)
            if scene_number:
                result[scene_number] = scene
    return result


def _timings_by_number(scene_timings: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {
        int(timing.get("scene_number", 0) or 0): timing
        for timing in scene_timings
        if isinstance(timing, dict)
    }


def _duration_seconds(scene: Any, timing: dict[str, Any]) -> float:
    if timing:
        try:
            return round(float(timing.get("duration_seconds", 0.0) or 0.0), 3)
        except (TypeError, ValueError):
            pass
    return round(float(getattr(scene, "duration_seconds", 0.0) or 0.0), 3)


def _scene_role(scene: Any) -> str:
    role = str(getattr(scene, "role", "") or "").lower()
    if role == "example":
        return "contrast"
    return role or "setup"


def _selected_media(media_scene: dict[str, Any]) -> dict[str, Any]:
    selected = media_scene.get("selected", {})
    return selected if isinstance(selected, dict) else {}


def _video_clip_available(selected: dict[str, Any]) -> bool:
    path = Path(str(selected.get("local_video_path", "") or ""))
    return path.exists() and path.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}
