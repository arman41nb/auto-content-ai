"""Quality checks for editorial Reel motion plans."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.render.editorial_motion import motion_scale_delta


STILL_SOURCE_TYPES = {"pexels_photo", "infographic", "ai_fallback"}
BANNED_TRANSITIONS = {"zoom_transition", "spin", "slide_gimmick", "long_fade", "random_zoom"}


def run_editorial_motion_quality(
    output_dir: Path,
    motion_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = motion_plan if isinstance(motion_plan, dict) else _read_json(output_dir / "editorial_motion_plan.json")
    report = evaluate_editorial_motion(payload)
    write_editorial_motion_quality_report(output_dir, report)
    return report


def evaluate_editorial_motion(motion_plan: dict[str, Any]) -> dict[str, Any]:
    scenes = motion_plan.get("scenes", [])
    scene_list = [scene for scene in scenes if isinstance(scene, dict)] if isinstance(scenes, list) else []
    if not scene_list:
        return {
            "quality_gate_passed": False,
            "publish_ready": False,
            "review_required": True,
            "recommended_action": "polish_motion",
            "obvious_zoom_count": 0,
            "obvious_zoom_scene_numbers": [],
            "max_scale_delta": 0.0,
            "max_still_scale_delta": 0.0,
            "average_scale_delta": 0.0,
            "average_still_scale_delta": 0.0,
            "repeated_motion_pattern_count": 0,
            "slideshow_motion_risk": "high",
            "motion_relevance_score": 0,
            "transition_variety_score": 0,
            "video_clip_utilization_score": 0,
            "combined_motion_load_score": 0,
            "editorial_motion_score": 0,
            "video_clips_used_count": 0,
            "photo_scenes_count": 0,
            "artificial_motion_scenes_count": 0,
            "artificial_motion_scene_numbers": [],
            "blocking_issues": ["Editorial motion plan is missing or empty."],
            "warnings": [],
        }
    still_scenes = [scene for scene in scene_list if str(scene.get("source_type", "")) in STILL_SOURCE_TYPES]
    still_deltas = [motion_scale_delta(scene) for scene in still_scenes]
    all_deltas = [motion_scale_delta(scene) for scene in scene_list]
    obvious_zoom_scenes = [
        int(scene.get("scene_number", 0) or 0)
        for scene in still_scenes
        if motion_scale_delta(scene) > 0.03 or "zoom" in str(scene.get("selected_motion_preset", "")).lower()
    ]
    over_cap_scenes = [
        int(scene.get("scene_number", 0) or 0)
        for scene in still_scenes
        if motion_scale_delta(scene) > 0.035 and "justified_large_scale_delta" not in str(scene.get("reason", "")).lower()
    ]
    repeated_motion_pattern_count = _repeated_motion_pattern_count(scene_list)
    repeated_zoom_direction_count = _repeated_zoom_direction_count(scene_list)
    max_scale_delta = max(all_deltas) if all_deltas else 0.0
    max_still_scale_delta = max(still_deltas) if still_deltas else 0.0
    average_still_scale_delta = sum(still_deltas) / len(still_deltas) if still_deltas else 0.0
    average_combined_motion_load = _average(
        [_float(scene.get("combined_motion_load_score"), 0.0) for scene in scene_list]
    )
    slideshow_motion_risk = _slideshow_risk(
        obvious_zoom_count=len(obvious_zoom_scenes),
        average_still_scale_delta=average_still_scale_delta,
        repeated_motion_pattern_count=repeated_motion_pattern_count + repeated_zoom_direction_count,
        average_combined_motion_load=average_combined_motion_load,
    )
    transition_variety_score = _transition_variety_score(motion_plan, scene_list)
    motion_relevance_score = _motion_relevance_score(scene_list)
    video_clip_utilization_score = _video_clip_utilization_score(motion_plan, scene_list)
    combined_motion_load_score = round(max(0.0, min(100.0, average_combined_motion_load)))
    editorial_motion_score = _editorial_motion_score(
        obvious_zoom_count=len(obvious_zoom_scenes),
        max_still_scale_delta=max_still_scale_delta,
        average_still_scale_delta=average_still_scale_delta,
        repeated_motion_pattern_count=repeated_motion_pattern_count + repeated_zoom_direction_count,
        slideshow_motion_risk=slideshow_motion_risk,
        transition_variety_score=transition_variety_score,
        motion_relevance_score=motion_relevance_score,
        video_clip_utilization_score=video_clip_utilization_score,
        combined_motion_load_score=combined_motion_load_score,
    )
    blocking: list[str] = []
    warnings: list[str] = []
    if len(obvious_zoom_scenes) > 1:
        blocking.append("obvious_zoom_count is above 1.")
    if over_cap_scenes:
        blocking.append("still image scale delta above 0.035 on scene(s): " + ", ".join(str(item) for item in over_cap_scenes) + ".")
    if average_still_scale_delta > 0.02:
        blocking.append(f"average still-image scale delta is above 0.020: {average_still_scale_delta:.3f}.")
    if repeated_zoom_direction_count > 0:
        blocking.append("same zoom direction repeats across 3+ scenes.")
    if slideshow_motion_risk == "high":
        blocking.append("slideshow_motion_risk is high.")
    if editorial_motion_score < 85:
        blocking.append(f"editorial_motion_score is below 85: {editorial_motion_score}.")
    if repeated_motion_pattern_count > 0:
        warnings.append("A motion preset repeats across 3+ adjacent scenes; verify the reason is intentional.")
    if transition_variety_score < 80:
        warnings.append("Transition plan feels repetitive or uses a banned transition.")
    review_required = bool(blocking or warnings)
    return {
        "quality_gate_passed": not blocking,
        "publish_ready": not blocking,
        "review_required": review_required,
        "recommended_action": "polish_motion" if blocking or slideshow_motion_risk == "high" else "review",
        "obvious_zoom_count": len(obvious_zoom_scenes),
        "obvious_zoom_scene_numbers": obvious_zoom_scenes,
        "max_scale_delta": round(max_scale_delta, 4),
        "max_still_scale_delta": round(max_still_scale_delta, 4),
        "average_scale_delta": round(_average(all_deltas), 4),
        "average_still_scale_delta": round(average_still_scale_delta, 4),
        "repeated_motion_pattern_count": repeated_motion_pattern_count + repeated_zoom_direction_count,
        "slideshow_motion_risk": slideshow_motion_risk,
        "motion_relevance_score": motion_relevance_score,
        "transition_variety_score": transition_variety_score,
        "video_clip_utilization_score": video_clip_utilization_score,
        "combined_motion_load_score": combined_motion_load_score,
        "editorial_motion_score": editorial_motion_score,
        "video_clips_used_count": int(motion_plan.get("video_clips_used_count", 0) or 0),
        "photo_scenes_count": int(motion_plan.get("photo_scenes_count", 0) or 0),
        "artificial_motion_scenes_count": int(motion_plan.get("artificial_motion_scenes_count", 0) or 0),
        "artificial_motion_scene_numbers": [
            int(scene.get("scene_number", 0) or 0)
            for scene in scene_list
            if bool(scene.get("artificial_motion", False))
        ],
        "blocking_issues": _dedupe(blocking),
        "warnings": _dedupe(warnings),
    }


def write_editorial_motion_quality_report(output_dir: Path, report: dict[str, Any]) -> None:
    (output_dir / "editorial_motion_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Editorial Motion Quality Report",
        "",
        f"- quality_gate_passed: {str(report.get('quality_gate_passed', False)).lower()}",
        f"- publish_ready: {str(report.get('publish_ready', False)).lower()}",
        f"- review_required: {str(report.get('review_required', False)).lower()}",
        f"- recommended_action: {report.get('recommended_action', '')}",
        f"- obvious_zoom_count: {report.get('obvious_zoom_count', 0)}",
        f"- max_still_scale_delta: {report.get('max_still_scale_delta', 0)}",
        f"- average_still_scale_delta: {report.get('average_still_scale_delta', 0)}",
        f"- repeated_motion_pattern_count: {report.get('repeated_motion_pattern_count', 0)}",
        f"- slideshow_motion_risk: {report.get('slideshow_motion_risk', '')}",
        f"- transition_variety_score: {report.get('transition_variety_score', 0)}",
        f"- video_clip_utilization_score: {report.get('video_clip_utilization_score', 0)}",
        f"- combined_motion_load_score: {report.get('combined_motion_load_score', 0)}",
        f"- editorial_motion_score: {report.get('editorial_motion_score', 0)}",
        "",
        "## Blocking Issues",
    ]
    blockers = report.get("blocking_issues", [])
    lines.extend(f"- {issue}" for issue in blockers) if isinstance(blockers, list) and blockers else lines.append("- None")
    lines.extend(["", "## Warnings"])
    warnings = report.get("warnings", [])
    lines.extend(f"- {warning}" for warning in warnings) if isinstance(warnings, list) and warnings else lines.append("- None")
    (output_dir / "editorial_motion_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _repeated_motion_pattern_count(scenes: list[dict[str, Any]]) -> int:
    count = 0
    run_name = ""
    run_length = 0
    for scene in scenes:
        name = str(scene.get("selected_motion_preset", ""))
        if name == run_name:
            run_length += 1
        else:
            if run_length >= 3 and run_name not in {"static_hold", "subject_locked_hold"}:
                count += 1
            run_name = name
            run_length = 1
    if run_length >= 3 and run_name not in {"static_hold", "subject_locked_hold"}:
        count += 1
    return count


def _repeated_zoom_direction_count(scenes: list[dict[str, Any]]) -> int:
    count = 0
    run_direction = ""
    run_length = 0
    for scene in scenes:
        direction = _zoom_direction(scene)
        if direction and direction == run_direction:
            run_length += 1
        else:
            if run_direction and run_length >= 3:
                count += 1
            run_direction = direction
            run_length = 1 if direction else 0
    if run_direction and run_length >= 3:
        count += 1
    return count


def _zoom_direction(scene: dict[str, Any]) -> str:
    start = _float(scene.get("scale_start"), 1.0)
    end = _float(scene.get("scale_end"), start)
    if abs(end - start) < 0.008:
        return ""
    return "push" if end > start else "pull"


def _slideshow_risk(
    obvious_zoom_count: int,
    average_still_scale_delta: float,
    repeated_motion_pattern_count: int,
    average_combined_motion_load: float,
) -> str:
    if obvious_zoom_count > 1 or average_still_scale_delta > 0.025 or repeated_motion_pattern_count > 0:
        return "high"
    if obvious_zoom_count == 1 or average_still_scale_delta > 0.017 or average_combined_motion_load > 58:
        return "medium"
    return "low"


def _transition_variety_score(motion_plan: dict[str, Any], scenes: list[dict[str, Any]]) -> int:
    transitions = motion_plan.get("transition_plan", [])
    names = [
        str(item.get("transition", ""))
        for item in transitions
        if isinstance(item, dict)
    ] if isinstance(transitions, list) else []
    if not names:
        names = [str(scene.get("transition_out", "")) for scene in scenes if scene.get("transition_out") not in {"", "none"}]
    if any(name in BANNED_TRANSITIONS for name in names):
        return 45
    if not names:
        return 85
    if all(name in {"clean_cut", "soft_cut_4_frames", "match_cut"} for name in names):
        return 92 if len(set(names)) > 1 else 88
    return 76


def _motion_relevance_score(scenes: list[dict[str, Any]]) -> int:
    score = 96
    for scene in scenes:
        risk = str(scene.get("amateur_motion_risk", "low"))
        reason = str(scene.get("reason", "")).strip()
        if risk == "high":
            score -= 18
        elif risk == "medium":
            score -= 7
        if not reason:
            score -= 5
        if str(scene.get("source_type", "")) == "infographic" and scene.get("selected_motion_preset") != "infographic_reveal":
            score -= 12
    return max(0, min(100, score))


def _video_clip_utilization_score(motion_plan: dict[str, Any], scenes: list[dict[str, Any]]) -> int:
    available = sum(1 for scene in scenes if scene.get("source_type") == "pexels_video" and scene.get("video_clip_available"))
    used = int(motion_plan.get("video_clips_used_count", 0) or 0)
    if available == 0:
        return 90
    return 100 if used >= available else max(60, round(100 * used / available))


def _editorial_motion_score(
    obvious_zoom_count: int,
    max_still_scale_delta: float,
    average_still_scale_delta: float,
    repeated_motion_pattern_count: int,
    slideshow_motion_risk: str,
    transition_variety_score: int,
    motion_relevance_score: int,
    video_clip_utilization_score: int,
    combined_motion_load_score: int,
) -> int:
    score = 100
    score -= obvious_zoom_count * 12
    score -= repeated_motion_pattern_count * 14
    score -= max(0, round((max_still_scale_delta - 0.025) * 600))
    score -= max(0, round((average_still_scale_delta - 0.015) * 700))
    if slideshow_motion_risk == "high":
        score -= 22
    elif slideshow_motion_risk == "medium":
        score -= 8
    score -= max(0, round((80 - transition_variety_score) * 0.5))
    score -= max(0, round((86 - motion_relevance_score) * 0.6))
    score -= max(0, round((75 - video_clip_utilization_score) * 0.2))
    score -= max(0, round((combined_motion_load_score - 62) * 0.35))
    return max(0, min(100, score))


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            result.append(value)
            seen.add(key)
    return result
