"""Strict quality gate for native 9:16 Reel story packages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageFilter, ImageStat

from app.content.reel_schemas import ReelPlan
from app.render.native_reel_renderer import REEL_SIZE


def run_native_reel_quality_gate(
    output_dir: Path,
    reel_plan: ReelPlan,
    metadata: dict[str, Any],
    voiceover_requested: bool,
) -> dict[str, Any]:
    reel_dir = output_dir / "final_reel"
    frames_dir = reel_dir / "frames"
    cover_path = reel_dir / "cover.jpg"
    reel_path = reel_dir / "reel.mp4"
    frame_paths = [frames_dir / f"frame_{scene.scene_number:02d}.jpg" for scene in reel_plan.scenes]

    frame_dimensions_ok = all(_image_is_size(path, REEL_SIZE) for path in frame_paths)
    cover_native = _image_is_size(cover_path, REEL_SIZE)
    reel_export = metadata.get("reel_export", {})
    reel_dimensions = reel_export.get("reel_dimensions", []) if isinstance(reel_export, dict) else []
    reel_native = reel_path.exists() and (reel_dimensions == [1080, 1920] or not reel_dimensions)

    first_second_hook_score = _first_second_hook_score(reel_plan)
    scene_variety_score, repeated_similarity = _scene_variety(frame_paths)
    motion_quality_score = _motion_quality_score(metadata)
    text_minimalism_score = _text_minimalism_score(reel_plan, frame_paths)
    cover_quality_score = _cover_quality_score(cover_path, reel_plan)
    image_artifact_risk = _max_raw_artifact_risk(output_dir, reel_plan)
    ai_slideshow_risk_score = _ai_slideshow_risk_score(
        motion_quality_score=motion_quality_score,
        scene_variety_score=scene_variety_score,
        frame_dimensions_ok=frame_dimensions_ok,
        image_artifact_risk=image_artifact_risk,
        metadata=metadata,
    )
    voiceover_quality_score = _voiceover_quality_score(metadata, reel_plan, voiceover_requested)
    duration_sync_score = _duration_sync_score(metadata, voiceover_requested)
    subtitle_quality_score = _subtitle_quality_score(metadata, voiceover_requested)
    caption_sync_score = _caption_sync_score(metadata, voiceover_requested)
    kinetic_caption_score = _kinetic_caption_score(metadata, voiceover_requested)
    caption_readability_score = _caption_readability_score(metadata, voiceover_requested)
    caption_layout_score = _caption_layout_metric(metadata, "caption_layout_score", 100 if not voiceover_requested else 0)
    caption_collision_count = _caption_layout_metric(metadata, "caption_collision_count", 0)
    caption_background_alignment_score = _caption_layout_metric(
        metadata,
        "caption_background_alignment_score",
        100 if not voiceover_requested else 0,
    )
    caption_safe_zone_score = _caption_layout_metric(metadata, "caption_safe_zone_score", 100 if not voiceover_requested else 0)
    active_highlight_layout_stability_score = _caption_layout_metric(
        metadata,
        "active_highlight_layout_stability_score",
        100 if not voiceover_requested else 0,
    )
    duplicate_text_layer_detected = _duplicate_text_layer_detected(metadata)
    scene_cut_on_phrase_boundary_score = _scene_cut_on_phrase_boundary_score(metadata)
    edit_rhythm_score = _edit_rhythm_score(metadata)
    visual_motion_score = _visual_motion_score(metadata, motion_quality_score)
    motion_professionalism_score = visual_motion_score
    sanitizer_damage_score = _sanitizer_damage_score(metadata)
    sanitizer_damage_risk = str(metadata.get("sanitizer_visual_damage_risk", "low"))
    sanitizer_mode = str(metadata.get("sanitizer_mode", "targeted"))
    sanitizer_modified_area_ratio = float(
        metadata.get("sanitizer_modified_area_ratio", metadata.get("sanitizer_area_ratio", 0.0)) or 0.0
    )
    image_clarity_score = _image_clarity_score(frame_paths)
    visual_polish_score = round(
        cover_quality_score * 0.22
        + image_clarity_score * 0.12
        + text_minimalism_score * 0.12
        + visual_motion_score * 0.22
        + scene_variety_score * 0.16
        + caption_layout_score * 0.08
        + sanitizer_damage_score * 0.20
    )
    perceived_template_risk = _perceived_template_risk(ai_slideshow_risk_score, visual_motion_score, edit_rhythm_score)
    viral_readiness_score = round(
        first_second_hook_score * 0.18
        + visual_polish_score * 0.22
        + edit_rhythm_score * 0.18
        + motion_professionalism_score * 0.14
        + caption_sync_score * 0.14
        + kinetic_caption_score * 0.14
        - max(0, perceived_template_risk - 45) * 0.12
    )
    professional_edit_score = round(
        visual_polish_score * 0.34
        + edit_rhythm_score * 0.24
        + motion_professionalism_score * 0.20
        + caption_layout_score * 0.08
        + kinetic_caption_score * 0.08
        + caption_sync_score * 0.06
    )

    native_reel_score = round(
        first_second_hook_score * 0.18
        + scene_variety_score * 0.17
        + motion_quality_score * 0.18
        + text_minimalism_score * 0.14
        + cover_quality_score * 0.12
        + max(0, 100 - ai_slideshow_risk_score) * 0.13
        + voiceover_quality_score * 0.08
    )

    blockers: list[str] = []
    if native_reel_score < 75:
        blockers.append(f"native_reel_score is below 75: {native_reel_score}.")
    if first_second_hook_score < 75:
        blockers.append(f"first_second_hook_score is below 75: {first_second_hook_score}.")
    if scene_variety_score < 70:
        blockers.append(f"scene_variety_score is below 70: {scene_variety_score}.")
    if ai_slideshow_risk_score > 60:
        blockers.append(f"ai_slideshow_risk_score is above 60: {ai_slideshow_risk_score}.")
    if not cover_native:
        blockers.append("Cover is not native 1080x1920.")
    if not frame_dimensions_ok:
        blockers.append("One or more scene frames are not native 1080x1920.")
    if not reel_native:
        blockers.append("Video is missing or not confirmed as native 1080x1920.")
    if motion_quality_score < 75:
        blockers.append("No credible per-scene motion metadata found.")
    if text_minimalism_score < 75:
        blockers.append("On-screen text is too long or too visually dominant.")
    if image_artifact_risk >= 70:
        blockers.append(f"Obvious AI text/watermark risk remains: {image_artifact_risk:.1f}.")
    if voiceover_requested and duration_sync_score < 100:
        blockers.append("Voiceover is longer than the final video.")
    if voiceover_requested and subtitle_quality_score < 75:
        blockers.append("Burned-in subtitles are missing or incomplete.")
    if voiceover_requested and caption_sync_score < 80:
        blockers.append(f"caption_sync_score is below 80: {caption_sync_score}.")
    if voiceover_requested and kinetic_caption_score < 75:
        blockers.append(f"kinetic_caption_score is below 75: {kinetic_caption_score}.")
    if voiceover_requested and caption_readability_score < 75:
        blockers.append(f"caption_readability_score is below 75: {caption_readability_score}.")
    if voiceover_requested and caption_collision_count > 0:
        blockers.append(f"caption_collision_count is above 0: {caption_collision_count}.")
    if voiceover_requested and duplicate_text_layer_detected:
        blockers.append("duplicate_text_layer_detected is true.")
    if voiceover_requested and caption_background_alignment_score < 90:
        blockers.append(f"caption_background_alignment_score is below 90: {caption_background_alignment_score}.")
    if voiceover_requested and caption_safe_zone_score < 90:
        blockers.append(f"caption_safe_zone_score is below 90: {caption_safe_zone_score}.")
    if voiceover_requested and caption_layout_score < 85:
        blockers.append(f"caption_layout_score is below 85: {caption_layout_score}.")
    if voiceover_requested and not _captions_based_on_tts(metadata):
        blockers.append("Voiceover exists but captions are not based on TTS timing.")
    if voiceover_requested and scene_cut_on_phrase_boundary_score < 75:
        blockers.append("Scene cuts are not aligned to phrase boundaries.")
    if visual_polish_score < 75:
        blockers.append(f"visual_polish_score is below 75: {visual_polish_score}.")
    if visual_motion_score < 75:
        blockers.append(f"visual_motion_score is below 75: {visual_motion_score}.")
    if edit_rhythm_score < 75:
        blockers.append(f"edit_rhythm_score is below 75: {edit_rhythm_score}.")
    if perceived_template_risk > 60:
        blockers.append(f"perceived_template_risk is above 60: {perceived_template_risk}.")
    if viral_readiness_score < 75:
        blockers.append(f"viral_readiness_score is below 75: {viral_readiness_score}.")
    if professional_edit_score < 80:
        blockers.append(f"professional_edit_score is below 80: {professional_edit_score}.")
    if sanitizer_damage_risk == "high":
        blockers.append("Sanitizer visual damage risk is high.")

    publish_ready = not blockers
    report = {
        "publish_ready": publish_ready,
        "technical_score": int(metadata.get("post_quality_score", 0) or 0),
        "native_reel_score": native_reel_score,
        "first_second_hook_score": first_second_hook_score,
        "scene_variety_score": scene_variety_score,
        "motion_quality_score": motion_quality_score,
        "text_minimalism_score": text_minimalism_score,
        "ai_slideshow_risk_score": ai_slideshow_risk_score,
        "cover_quality_score": cover_quality_score,
        "voiceover_quality_score": voiceover_quality_score,
        "duration_sync_score": duration_sync_score,
        "subtitle_quality_score": subtitle_quality_score,
        "caption_sync_score": caption_sync_score,
        "kinetic_caption_score": kinetic_caption_score,
        "caption_readability_score": caption_readability_score,
        "caption_layout_score": caption_layout_score,
        "caption_collision_count": caption_collision_count,
        "caption_background_alignment_score": caption_background_alignment_score,
        "caption_safe_zone_score": caption_safe_zone_score,
        "active_highlight_layout_stability_score": active_highlight_layout_stability_score,
        "duplicate_text_layer_detected": duplicate_text_layer_detected,
        "active_word_highlight_used": _active_word_highlight_used(metadata),
        "caption_style": _caption_style(metadata),
        "scene_cut_on_phrase_boundary_score": scene_cut_on_phrase_boundary_score,
        "visual_motion_score": visual_motion_score,
        "sanitizer_mode": sanitizer_mode,
        "sanitizer_modified_area_ratio": round(sanitizer_modified_area_ratio, 4),
        "sanitizer_damage_risk": sanitizer_damage_risk,
        "edit_rhythm_score": edit_rhythm_score,
        "motion_professionalism_score": motion_professionalism_score,
        "transition_quality_score": scene_cut_on_phrase_boundary_score,
        "image_clarity_score": image_clarity_score,
        "visual_polish_score": visual_polish_score,
        "sanitizer_damage_score": sanitizer_damage_score,
        "perceived_template_risk": perceived_template_risk,
        "viral_readiness_score": viral_readiness_score,
        "professional_edit_score": professional_edit_score,
        "voiceover_requested": voiceover_requested,
        "voiceover_created": _voiceover_created(metadata),
        "duration_sync_ok": duration_sync_score == 100,
        "subtitles_required": voiceover_requested,
        "subtitles_created": _subtitles_created(metadata),
        "subtitles_burned_in": _subtitles_burned_in(metadata),
        "cover_native_1080x1920": cover_native,
        "reel_native_1080x1920": reel_native,
        "frames_native_1080x1920": frame_dimensions_ok,
        "video_is_carousel_pasted_into_9_16": _video_looks_carousel_pasted(metadata),
        "text_boxes_cover_too_much_screen": text_minimalism_score < 75,
        "no_motion": motion_quality_score < 75,
        "obvious_ai_text_or_watermark_risk": image_artifact_risk,
        "repeated_image_similarity": round(repeated_similarity, 3),
        "reel_path": str(reel_path),
        "cover_path": str(cover_path),
        "frame_paths": [str(path) for path in frame_paths],
        "blocking_issues": blockers,
        "recommended_action": "post" if publish_ready else "regenerate_bad_native_reel_assets",
    }
    write_native_reel_quality_report(output_dir, report)
    return report


def write_native_reel_quality_report(output_dir: Path, report: dict[str, Any]) -> None:
    (output_dir / "native_reel_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Native Reel Quality Report",
        "",
        f"- publish_ready: {str(report['publish_ready']).lower()}",
        f"- native_reel_score: {report['native_reel_score']}",
        f"- first_second_hook_score: {report['first_second_hook_score']}",
        f"- scene_variety_score: {report['scene_variety_score']}",
        f"- motion_quality_score: {report['motion_quality_score']}",
        f"- text_minimalism_score: {report['text_minimalism_score']}",
        f"- ai_slideshow_risk_score: {report['ai_slideshow_risk_score']}",
        f"- cover_quality_score: {report['cover_quality_score']}",
        f"- voiceover_quality_score: {report['voiceover_quality_score']}",
        f"- duration_sync_score: {report['duration_sync_score']}",
        f"- subtitle_quality_score: {report['subtitle_quality_score']}",
        f"- caption_sync_score: {report['caption_sync_score']}",
        f"- kinetic_caption_score: {report['kinetic_caption_score']}",
        f"- caption_readability_score: {report['caption_readability_score']}",
        f"- caption_layout_score: {report['caption_layout_score']}",
        f"- caption_collision_count: {report['caption_collision_count']}",
        f"- caption_background_alignment_score: {report['caption_background_alignment_score']}",
        f"- caption_safe_zone_score: {report['caption_safe_zone_score']}",
        f"- active_highlight_layout_stability_score: {report['active_highlight_layout_stability_score']}",
        f"- duplicate_text_layer_detected: {str(report['duplicate_text_layer_detected']).lower()}",
        f"- active_word_highlight_used: {str(report['active_word_highlight_used']).lower()}",
        f"- caption_style: {report['caption_style']}",
        f"- scene_cut_on_phrase_boundary_score: {report['scene_cut_on_phrase_boundary_score']}",
        f"- visual_motion_score: {report['visual_motion_score']}",
        f"- sanitizer_mode: {report['sanitizer_mode']}",
        f"- sanitizer_modified_area_ratio: {report['sanitizer_modified_area_ratio']}",
        f"- sanitizer_damage_risk: {report['sanitizer_damage_risk']}",
        f"- edit_rhythm_score: {report['edit_rhythm_score']}",
        f"- professional_edit_score: {report['professional_edit_score']}",
        f"- transition_quality_score: {report['transition_quality_score']}",
        f"- image_clarity_score: {report['image_clarity_score']}",
        f"- visual_polish_score: {report['visual_polish_score']}",
        f"- viral_readiness_score: {report['viral_readiness_score']}",
        f"- reel_path: {report['reel_path']}",
        f"- cover_path: {report['cover_path']}",
        "",
        "## Blocking Issues",
    ]
    blockers = report.get("blocking_issues", [])
    if blockers:
        lines.extend(f"- {issue}" for issue in blockers)
    else:
        lines.append("- None")
    (output_dir / "native_reel_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _first_second_hook_score(reel_plan: ReelPlan) -> int:
    first = reel_plan.scenes[0]
    text = first.on_screen_text.lower()
    voice = first.voiceover_line.lower()
    score = 72
    hook_terms = (
        "ocean",
        "oxygen",
        "moon",
        "gravity",
        "earth",
        "sun",
        "star",
        "planet",
        "black hole",
        "storm",
        "city",
        "ai",
        "robot",
    )
    if any(term in text or term in voice for term in hook_terms):
        score += 10
    if any(word in text for word in ("moves", "rose", "vanish", "fails", "changes", "breaks", "hits", "shifts")):
        score += 10
    if first.duration_seconds <= 2.2:
        score += 5
    if "what if" in voice:
        score += 5
    return min(100, score)


def _scene_variety(paths: list[Path]) -> tuple[int, float]:
    if len(paths) < 2:
        return 0, 1.0
    prepared: list[Image.Image] = []
    for path in paths:
        try:
            with Image.open(path) as image:
                crop = image.convert("L").crop((0, 120, image.width, int(image.height * 0.72)))
                prepared.append(crop.resize((72, 96), Image.Resampling.BILINEAR))
        except Exception:
            continue
    rmse_values: list[float] = []
    for first, second in zip(prepared, prepared[1:]):
        diff = ImageChops.difference(first, second)
        rmse_values.append(ImageStat.Stat(diff).rms[0])
    if not rmse_values:
        return 0, 1.0
    avg_rmse = sum(rmse_values) / len(rmse_values)
    score = round(max(0, min(100, 26 + avg_rmse * 2.6)))
    similarity = max(0.0, min(1.0, 1 - (avg_rmse / 58)))
    return score, similarity


def _motion_quality_score(metadata: dict[str, Any]) -> int:
    native = metadata.get("native_reel_render", {})
    if not isinstance(native, dict):
        return 0
    motion = str(native.get("motion", "")).lower()
    source = str(native.get("source", "")).lower()
    score = 54
    if "slow zoom" in motion and "pan" in motion:
        score += 32
    if "scene-specific" in motion and "micro-shake" in motion and "pull" in motion:
        score += 36
    if native.get("scene_count") == 5:
        score += 7
    if source == "native_fullscreen_scene_images":
        score += 7
    return min(100, score)


def _text_minimalism_score(reel_plan: ReelPlan, frame_paths: list[Path]) -> int:
    max_words = max(len(scene.on_screen_text.split()) for scene in reel_plan.scenes)
    score = 100 - max(0, max_words - 3) * 8
    dark_ratios = [_dark_area_ratio(path) for path in frame_paths if path.exists()]
    if dark_ratios and max(dark_ratios) > 0.58:
        score -= int((max(dark_ratios) - 0.58) * 90)
    return max(0, min(100, score))


def _cover_quality_score(cover_path: Path, reel_plan: ReelPlan) -> int:
    if not _image_is_size(cover_path, REEL_SIZE):
        return 0
    score = 86
    cover_words = reel_plan.cover_text.split()
    if any(word in reel_plan.cover_text.upper() for word in ("IF", "REAL", "FUTURE", "OCEAN")):
        score += 8
    if len(cover_words) <= 5:
        score += 6
    return min(100, score)


def _voiceover_quality_score(metadata: dict[str, Any], reel_plan: ReelPlan, requested: bool) -> int:
    voiceover = metadata.get("voiceover", {})
    if not requested:
        return 100
    if not isinstance(voiceover, dict) or not voiceover.get("script_created"):
        return 35
    words = len(reel_plan.voiceover_script.split())
    score = 72 if 25 <= words <= 45 else 55
    if voiceover.get("tts_created"):
        score += 20
    if voiceover.get("reel_with_voice_path"):
        score += 8
    return min(100, score)


def _duration_sync_score(metadata: dict[str, Any], requested: bool) -> int:
    if not requested:
        return 100
    voiceover = metadata.get("voiceover", {})
    native = metadata.get("native_reel_render", {})
    voice_dict = voiceover if isinstance(voiceover, dict) else {}
    native_dict = native if isinstance(native, dict) else {}
    duration_sync_ok = bool(voice_dict.get("duration_sync_ok") or native_dict.get("duration_sync_ok"))
    audio = float(voice_dict.get("voiceover_duration_seconds", native_dict.get("voiceover_duration_seconds", 0.0)) or 0.0)
    video = float(voice_dict.get("final_video_duration_seconds", native_dict.get("final_video_duration_seconds", 0.0)) or 0.0)
    if duration_sync_ok or (audio and video and video + 0.05 >= audio):
        return 100
    if audio and video:
        return max(0, round(100 - max(0.0, audio - video) * 18))
    return 35


def _subtitle_quality_score(metadata: dict[str, Any], requested: bool) -> int:
    if not requested:
        return 100
    voiceover = metadata.get("voiceover", {})
    voice_dict = voiceover if isinstance(voiceover, dict) else {}
    if voice_dict.get("kinetic_subtitles_created") or voice_dict.get("reel_with_voice_kinetic_subtitles_path"):
        return 96
    if _subtitles_burned_in(metadata):
        return 94
    if _subtitles_created(metadata):
        return 62
    return 0


def _caption_sync_score(metadata: dict[str, Any], requested: bool) -> int:
    if not requested:
        return 100
    voiceover = metadata.get("voiceover", {})
    native = metadata.get("native_reel_render", {})
    voice_dict = voiceover if isinstance(voiceover, dict) else {}
    native_dict = native if isinstance(native, dict) else {}
    for payload in (voice_dict, native_dict):
        if "caption_sync_score" in payload:
            return int(payload.get("caption_sync_score", 0) or 0)
    return 62 if _subtitles_created(metadata) else 0


def _kinetic_caption_score(metadata: dict[str, Any], requested: bool) -> int:
    if not requested:
        return 100
    voiceover = metadata.get("voiceover", {})
    native = metadata.get("native_reel_render", {})
    voice_dict = voiceover if isinstance(voiceover, dict) else {}
    native_dict = native if isinstance(native, dict) else {}
    for payload in (voice_dict, native_dict):
        if "kinetic_caption_score" in payload:
            return int(payload.get("kinetic_caption_score", 0) or 0)
    return 0


def _caption_readability_score(metadata: dict[str, Any], requested: bool) -> int:
    if not requested:
        return 100
    voiceover = metadata.get("voiceover", {})
    native = metadata.get("native_reel_render", {})
    voice_dict = voiceover if isinstance(voiceover, dict) else {}
    native_dict = native if isinstance(native, dict) else {}
    for payload in (voice_dict, native_dict):
        if "caption_readability_score" in payload:
            return int(payload.get("caption_readability_score", 0) or 0)
    return 0


def _caption_layout_metric(metadata: dict[str, Any], key: str, default: int) -> int:
    voiceover = metadata.get("voiceover", {})
    native = metadata.get("native_reel_render", {})
    for payload in (voiceover, native):
        if isinstance(payload, dict) and key in payload:
            return int(payload.get(key, default) or 0)
    return default


def _duplicate_text_layer_detected(metadata: dict[str, Any]) -> bool:
    voiceover = metadata.get("voiceover", {})
    native = metadata.get("native_reel_render", {})
    for payload in (voiceover, native):
        if isinstance(payload, dict) and "duplicate_text_layer_detected" in payload:
            return bool(payload.get("duplicate_text_layer_detected"))
    return bool(
        isinstance(native, dict)
        and native.get("subtitled_silent_path")
        and isinstance(voiceover, dict)
        and voiceover.get("kinetic_subtitles_created")
    )


def _active_word_highlight_used(metadata: dict[str, Any]) -> bool:
    voiceover = metadata.get("voiceover", {})
    native = metadata.get("native_reel_render", {})
    return (
        isinstance(voiceover, dict)
        and bool(voiceover.get("active_word_highlight_used"))
        or isinstance(native, dict)
        and bool(native.get("active_word_highlight_used"))
    )


def _caption_style(metadata: dict[str, Any]) -> str:
    voiceover = metadata.get("voiceover", {})
    native = metadata.get("native_reel_render", {})
    if isinstance(voiceover, dict) and voiceover.get("caption_style"):
        return str(voiceover.get("caption_style"))
    if isinstance(native, dict) and native.get("caption_style"):
        return str(native.get("caption_style"))
    return ""


def _captions_based_on_tts(metadata: dict[str, Any]) -> bool:
    voiceover = metadata.get("voiceover", {})
    native = metadata.get("native_reel_render", {})
    return (
        isinstance(voiceover, dict)
        and bool(voiceover.get("caption_timing_based_on_tts"))
        or isinstance(native, dict)
        and bool(native.get("caption_timing_based_on_tts"))
    )


def _scene_cut_on_phrase_boundary_score(metadata: dict[str, Any]) -> int:
    native = metadata.get("native_reel_render", {})
    native_dict = native if isinstance(native, dict) else {}
    return int(native_dict.get("scene_cut_on_phrase_boundary_score", 70) or 70)


def _visual_motion_score(metadata: dict[str, Any], fallback: int) -> int:
    native = metadata.get("native_reel_render", {})
    native_dict = native if isinstance(native, dict) else {}
    return int(native_dict.get("visual_motion_score", fallback) or fallback)


def _edit_rhythm_score(metadata: dict[str, Any]) -> int:
    native = metadata.get("native_reel_render", {})
    native_dict = native if isinstance(native, dict) else {}
    durations = native_dict.get("scene_durations", [])
    if not isinstance(durations, list) or not durations:
        return 62
    values = [float(value) for value in durations if float(value or 0) > 0]
    if not values:
        return 62
    score = 88
    if min(values) < 1.4:
        score -= 30
    if max(values) > 6.5:
        score -= 10
    if len(values) == 5:
        score += 6
    strategy = str(native_dict.get("scene_duration_strategy", ""))
    if "voiceover_word_count" in strategy:
        score += 6
    return max(0, min(100, score))


def _sanitizer_damage_score(metadata: dict[str, Any]) -> int:
    risk = str(metadata.get("sanitizer_visual_damage_risk", "low"))
    if risk == "high":
        return 30
    if risk == "medium":
        return 72
    return 96


def _perceived_template_risk(ai_slideshow_risk_score: int, motion_quality_score: int, edit_rhythm_score: int) -> int:
    risk = ai_slideshow_risk_score
    if motion_quality_score >= 90:
        risk -= 8
    if edit_rhythm_score >= 88:
        risk -= 8
    return max(0, min(100, risk))


def _ai_slideshow_risk_score(
    motion_quality_score: int,
    scene_variety_score: int,
    frame_dimensions_ok: bool,
    image_artifact_risk: float,
    metadata: dict[str, Any],
) -> int:
    risk = 52
    risk -= int(motion_quality_score * 0.34)
    risk -= int(scene_variety_score * 0.20)
    if frame_dimensions_ok:
        risk -= 10
    if _video_looks_carousel_pasted(metadata):
        risk += 48
    if image_artifact_risk >= 70:
        risk += 24
    elif image_artifact_risk >= 45:
        risk += 10
    return max(0, min(100, risk))


def _max_raw_artifact_risk(output_dir: Path, reel_plan: ReelPlan) -> float:
    raw_dir = output_dir / "raw_images"
    risks: list[float] = []
    for scene in reel_plan.scenes:
        path = raw_dir / f"slide_{scene.scene_number:02d}.jpg"
        if not path.exists():
            risks.append(100.0)
            continue
        risks.append(_fast_artifact_risk(path))
    return max(risks) if risks else 100.0


def _fast_artifact_risk(path: Path) -> float:
    try:
        with Image.open(path) as image:
            small = image.convert("L")
            small.thumbnail((540, 960))
            stat = ImageStat.Stat(small)
            brightness = stat.mean[0]
            contrast = stat.stddev[0]
            edges = small.filter(ImageFilter.FIND_EDGES)
            edge_mean = ImageStat.Stat(edges).mean[0]
            bottom = small.crop((0, int(small.height * 0.74), small.width, small.height))
            bottom_edge = ImageStat.Stat(bottom.filter(ImageFilter.FIND_EDGES)).mean[0]
    except Exception:
        return 100.0
    risk = 0.0
    if brightness < 22 or brightness > 240:
        risk += 12
    if contrast < 18:
        risk += 14
    if edge_mean > 46:
        risk += 18
    if bottom_edge > 54:
        risk += 30
    return min(100.0, risk)


def _image_clarity_score(paths: list[Path]) -> int:
    scores: list[int] = []
    for path in paths:
        try:
            with Image.open(path) as image:
                lum = image.convert("L")
                small = lum.resize((180, 320), Image.Resampling.BILINEAR)
                contrast = ImageStat.Stat(small).stddev[0]
                edge_mean = ImageStat.Stat(small.filter(ImageFilter.FIND_EDGES)).mean[0]
        except Exception:
            scores.append(35)
            continue
        score = 58 + min(24, int(contrast * 0.5)) + min(18, int(edge_mean * 0.7))
        scores.append(max(0, min(100, score)))
    return round(sum(scores) / len(scores)) if scores else 0


def _voiceover_created(metadata: dict[str, Any]) -> bool:
    voiceover = metadata.get("voiceover", {})
    return isinstance(voiceover, dict) and bool(voiceover.get("tts_created"))


def _subtitles_created(metadata: dict[str, Any]) -> bool:
    voiceover = metadata.get("voiceover", {})
    native = metadata.get("native_reel_render", {})
    return (
        isinstance(voiceover, dict)
        and bool(voiceover.get("subtitles_created"))
        or isinstance(native, dict)
        and bool(native.get("subtitles_created"))
    )


def _subtitles_burned_in(metadata: dict[str, Any]) -> bool:
    voiceover = metadata.get("voiceover", {})
    return isinstance(voiceover, dict) and bool(voiceover.get("subtitles_burned_in"))


def _video_looks_carousel_pasted(metadata: dict[str, Any]) -> bool:
    native = metadata.get("native_reel_render", {})
    if not isinstance(native, dict):
        return True
    return str(native.get("source", "")) != "native_fullscreen_scene_images"


def _image_is_size(path: Path, expected: tuple[int, int]) -> bool:
    try:
        with Image.open(path) as image:
            return image.size == expected
    except Exception:
        return False


def _dark_area_ratio(path: Path) -> float:
    try:
        with Image.open(path) as image:
            lum = image.convert("L")
            hist = lum.histogram()
            return sum(hist[:28]) / max(1, image.width * image.height)
    except Exception:
        return 1.0
