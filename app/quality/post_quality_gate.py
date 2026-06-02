"""Final publish-readiness gate for a generated carousel package."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat

from app.content.schemas import CarouselPlan
from app.render.carousel_renderer import CANVAS_SIZE


ARTIFACT_BLOCK_THRESHOLD = 70.0


@dataclass(frozen=True)
class PostQualityReport:
    publish_ready: bool
    score: int
    blocking_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommended_action: str = "reject"
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "publish_ready": self.publish_ready,
            "score": self.score,
            "blocking_issues": self.blocking_issues,
            "warnings": self.warnings,
            "recommended_action": self.recommended_action,
            **self.details,
        }


def run_post_quality_gate(output_dir: Path, plan: CarouselPlan, metadata: dict[str, Any]) -> PostQualityReport:
    blocking: list[str] = []
    warnings: list[str] = []
    score = 100

    final_dir = output_dir / "final_slides"
    final_slide_paths = [final_dir / f"slide_{slide.slide_number:02d}.jpg" for slide in plan.slides]
    missing_final = [path.name for path in final_slide_paths if not path.exists()]
    if missing_final:
        blocking.append("Missing final slide(s): " + ", ".join(missing_final) + ".")
        score -= min(45, 12 * len(missing_final))

    existing_final = [path for path in final_slide_paths if path.exists()]
    if len(existing_final) != len(plan.slides):
        blocking.append(f"Expected {len(plan.slides)} final slide(s), found {len(existing_final)}.")

    dimension_warnings = _dimension_warnings(existing_final)
    if dimension_warnings:
        blocking.extend(dimension_warnings)
        score -= min(30, 8 * len(dimension_warnings))

    artifact_scores = _dict_of_numbers(metadata.get("artifact_risk_score_per_slide", {}))
    artifact_scope = str(metadata.get("artifact_detection_scope", "raw") or "raw")
    high_artifact_slides = [
        slide_key for slide_key, risk in artifact_scores.items() if risk >= ARTIFACT_BLOCK_THRESHOLD
    ]
    failed_quality_slides = _string_list(metadata.get("failed_quality_slides", []))
    if high_artifact_slides:
        blocking.append(
            f"High image artifact risk on: {', '.join(sorted(high_artifact_slides))} "
            f"(scope: {artifact_scope})."
        )
        score -= min(45, 15 * len(high_artifact_slides))
    if failed_quality_slides:
        blocking.append("Failed image quality slide(s): " + ", ".join(sorted(failed_quality_slides)) + ".")
        score -= min(35, 12 * len(failed_quality_slides))

    publish_blocking_image_warnings = _string_list(metadata.get("publish_blocking_image_warnings", []))
    if publish_blocking_image_warnings:
        warnings.extend(publish_blocking_image_warnings)
        score -= min(20, 5 * len(publish_blocking_image_warnings))

    image_quality_warnings = metadata.get("image_quality_warnings", {})
    if isinstance(image_quality_warnings, dict):
        warning_count = sum(len(value) for value in image_quality_warnings.values() if isinstance(value, list))
        if warning_count:
            warnings.append(f"Image QA produced {warning_count} warning(s).")
            score -= min(12, warning_count)

    caption_alignment_score = int(metadata.get("caption_alignment_score", 100) or 0)
    caption_quality_warnings = _string_list(metadata.get("caption_quality_warnings", []))
    caption_mismatch_warnings = [
        item
        for item in caption_quality_warnings
        if "mismatch" in item.lower() or "unrelated concept" in item.lower()
    ]
    if caption_alignment_score and caption_alignment_score < 70:
        blocking.append(f"Caption-topic alignment score is too low: {caption_alignment_score}.")
        score -= 30
    if caption_mismatch_warnings:
        blocking.append("Caption-topic mismatch warning exists.")
        warnings.extend(caption_mismatch_warnings)
        score -= 25
    elif caption_quality_warnings:
        warnings.extend(caption_quality_warnings)
        score -= min(10, len(caption_quality_warnings) * 2)

    cta_warning = _cta_warning(plan)
    if cta_warning:
        warnings.append(cta_warning)
        score -= 6

    reel_export = metadata.get("reel_export", {})
    if isinstance(reel_export, dict) and reel_export.get("requested") and not reel_export.get("created_video"):
        blocking.append("Reel video was requested but final_reel/reel.mp4 was not created.")
        score -= 20

    voiceover_check = _voiceover_quality_report(output_dir, metadata)
    warnings.extend(voiceover_check["voiceover_warnings"])
    if voiceover_check["voiceover_blocking_issues"]:
        blocking.extend(voiceover_check["voiceover_blocking_issues"])
        score -= min(35, 12 * len(voiceover_check["voiceover_blocking_issues"]))

    native_reel_quality = metadata.get("native_reel_quality", {})
    if isinstance(native_reel_quality, dict) and native_reel_quality:
        native_reel_score = int(native_reel_quality.get("native_reel_score", 0) or 0)
        first_second_hook_score = int(native_reel_quality.get("first_second_hook_score", 0) or 0)
        scene_variety_score = int(native_reel_quality.get("scene_variety_score", 0) or 0)
        ai_slideshow_risk_score = int(native_reel_quality.get("ai_slideshow_risk_score", 100))
        visual_polish_score = int(native_reel_quality.get("visual_polish_score", 100) or 0)
        edit_rhythm_score = int(native_reel_quality.get("edit_rhythm_score", 100) or 0)
        caption_sync_score = int(native_reel_quality.get("caption_sync_score", 100) or 0)
        kinetic_caption_score = int(native_reel_quality.get("kinetic_caption_score", 100) or 0)
        caption_readability_score = int(native_reel_quality.get("caption_readability_score", 100) or 0)
        caption_layout_score = int(native_reel_quality.get("caption_layout_score", 100) or 0)
        caption_collision_count = int(native_reel_quality.get("caption_collision_count", 0) or 0)
        caption_background_alignment_score = int(native_reel_quality.get("caption_background_alignment_score", 100) or 0)
        caption_safe_zone_score = int(native_reel_quality.get("caption_safe_zone_score", 100) or 0)
        duplicate_text_layer_detected = bool(native_reel_quality.get("duplicate_text_layer_detected", False))
        scene_cut_on_phrase_boundary_score = int(native_reel_quality.get("scene_cut_on_phrase_boundary_score", 100) or 0)
        visual_motion_score = int(native_reel_quality.get("visual_motion_score", 100) or 0)
        professional_edit_score = int(native_reel_quality.get("professional_edit_score", 100) or 0)
        sanitizer_damage_risk = str(native_reel_quality.get("sanitizer_damage_risk", metadata.get("sanitizer_visual_damage_risk", "low")))
        perceived_template_risk = int(native_reel_quality.get("perceived_template_risk", ai_slideshow_risk_score) or 0)
        viral_readiness_score = int(native_reel_quality.get("viral_readiness_score", native_reel_score) or 0)
        if native_reel_score < 75:
            blocking.append(f"Native Reel score is below publish threshold: {native_reel_score}.")
            score -= 18
        if first_second_hook_score < 75:
            blocking.append(f"First-second hook score is below publish threshold: {first_second_hook_score}.")
            score -= 12
        if scene_variety_score < 70:
            blocking.append(f"Scene variety score is below publish threshold: {scene_variety_score}.")
            score -= 12
        if ai_slideshow_risk_score > 60:
            blocking.append(f"AI slideshow risk is too high: {ai_slideshow_risk_score}.")
            score -= 16
        if visual_polish_score < 75:
            blocking.append(f"Native Reel visual polish score is below publish threshold: {visual_polish_score}.")
            score -= 8
        if edit_rhythm_score < 75:
            blocking.append(f"Native Reel edit rhythm score is below publish threshold: {edit_rhythm_score}.")
            score -= 8
        if caption_sync_score < 80:
            blocking.append(f"Native Reel caption sync score is below publish threshold: {caption_sync_score}.")
            score -= 12
        if kinetic_caption_score < 75:
            blocking.append(f"Native Reel kinetic caption score is below publish threshold: {kinetic_caption_score}.")
            score -= 10
        if caption_readability_score < 75:
            blocking.append(f"Native Reel caption readability score is below publish threshold: {caption_readability_score}.")
            score -= 8
        if caption_collision_count > 0:
            blocking.append(f"Native Reel caption collision count is above 0: {caption_collision_count}.")
            score -= 16
        if duplicate_text_layer_detected:
            blocking.append("Native Reel duplicate text layer was detected.")
            score -= 16
        if caption_background_alignment_score < 90:
            blocking.append(f"Native Reel caption background alignment score is below threshold: {caption_background_alignment_score}.")
            score -= 12
        if caption_safe_zone_score < 90:
            blocking.append(f"Native Reel caption safe-zone score is below threshold: {caption_safe_zone_score}.")
            score -= 12
        if caption_layout_score < 85:
            blocking.append(f"Native Reel caption layout score is below threshold: {caption_layout_score}.")
            score -= 12
        if scene_cut_on_phrase_boundary_score < 75:
            blocking.append("Native Reel scene cuts are not aligned to phrase boundaries.")
            score -= 8
        if visual_motion_score < 75:
            blocking.append(f"Native Reel visual motion score is below threshold: {visual_motion_score}.")
            score -= 8
        if professional_edit_score < 80:
            blocking.append(f"Native Reel professional edit score is below threshold: {professional_edit_score}.")
            score -= 8
        if sanitizer_damage_risk == "high":
            blocking.append("Native Reel sanitizer damage risk is high.")
            score -= 12
        if perceived_template_risk > 60:
            blocking.append(f"Native Reel perceived template risk is too high: {perceived_template_risk}.")
            score -= 8
        if viral_readiness_score < 75:
            blocking.append(f"Native Reel viral readiness score is below publish threshold: {viral_readiness_score}.")
            score -= 8
        for issue in _string_list(native_reel_quality.get("blocking_issues", [])):
            blocking.append(issue)

    design = _design_quality_report(output_dir, existing_final, metadata)
    warnings.extend(design["amateur_template_warnings"])
    if design["design_score"] < 70:
        blocking.append(f"Design score is below publish threshold: {design['design_score']}.")
    if isinstance(reel_export, dict) and reel_export.get("requested"):
        if not design["cover_native_9_16"]:
            blocking.append("Reel cover is not native 1080x1920.")
        if not design["reel_native_9_16"]:
            blocking.append("Reel video is not native 1080x1920.")

    score = max(0, min(100, score))
    if score < 70:
        blocking.append(f"Quality score is below publish threshold: {score}.")

    publish_ready = not blocking and score >= 70
    recommended_action = _recommended_action(blocking, high_artifact_slides, failed_quality_slides)
    report = PostQualityReport(
        publish_ready=publish_ready,
        score=score,
        blocking_issues=_dedupe(blocking),
        warnings=_dedupe(warnings),
        recommended_action=recommended_action,
        details={
            "artifact_detection_scope": artifact_scope,
            "raw_image_artifact_risk": metadata.get("raw_artifact_risk_score_per_slide", {}),
            "raw_artifact_risk_score_per_slide": metadata.get("raw_artifact_risk_score_per_slide", {}),
            "rendered_overlay_ignored_regions": metadata.get("rendered_overlay_ignored_regions", {}),
            "intentional_overlay_text_present": bool(metadata.get("intentional_overlay_text_present", False)),
            "publish_blocking_image_warnings": publish_blocking_image_warnings,
            "native_reel_quality": native_reel_quality if isinstance(native_reel_quality, dict) else {},
            "native_reel_score": native_reel_quality.get("native_reel_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "first_second_hook_score": native_reel_quality.get("first_second_hook_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "scene_variety_score": native_reel_quality.get("scene_variety_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "ai_slideshow_risk_score": native_reel_quality.get("ai_slideshow_risk_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "cover_quality_score": native_reel_quality.get("cover_quality_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "professional_edit_score": native_reel_quality.get("professional_edit_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "viral_readiness_score": native_reel_quality.get("viral_readiness_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "visual_polish_score": native_reel_quality.get("visual_polish_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "edit_rhythm_score": native_reel_quality.get("edit_rhythm_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "caption_sync_score": native_reel_quality.get("caption_sync_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "kinetic_caption_score": native_reel_quality.get("kinetic_caption_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "caption_readability_score": native_reel_quality.get("caption_readability_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "caption_layout_score": native_reel_quality.get("caption_layout_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "caption_collision_count": native_reel_quality.get("caption_collision_count", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "caption_background_alignment_score": native_reel_quality.get("caption_background_alignment_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "caption_safe_zone_score": native_reel_quality.get("caption_safe_zone_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "active_highlight_layout_stability_score": native_reel_quality.get("active_highlight_layout_stability_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "duplicate_text_layer_detected": native_reel_quality.get("duplicate_text_layer_detected", False)
            if isinstance(native_reel_quality, dict)
            else False,
            "active_word_highlight_used": native_reel_quality.get("active_word_highlight_used", False)
            if isinstance(native_reel_quality, dict)
            else False,
            "caption_style": native_reel_quality.get("caption_style", "")
            if isinstance(native_reel_quality, dict)
            else "",
            "scene_cut_on_phrase_boundary_score": native_reel_quality.get("scene_cut_on_phrase_boundary_score", 0)
            if isinstance(native_reel_quality, dict)
            else 0,
            "sanitizer_damage_risk": native_reel_quality.get("sanitizer_damage_risk", metadata.get("sanitizer_visual_damage_risk", "low"))
            if isinstance(native_reel_quality, dict)
            else metadata.get("sanitizer_visual_damage_risk", "low"),
            **voiceover_check,
            **design,
        },
    )
    write_post_quality_report(output_dir, report)
    return report


def write_post_quality_report(output_dir: Path, report: PostQualityReport) -> None:
    (output_dir / "post_quality_report.json").write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Post Quality Report",
        "",
        f"- publish_ready: {str(report.publish_ready).lower()}",
        f"- score: {report.score}",
        f"- design_score: {report.details.get('design_score', 0)}",
        f"- reel_design_score: {report.details.get('reel_design_score', 0)}",
        f"- carousel_design_score: {report.details.get('carousel_design_score', 0)}",
        f"- visual_variety_score: {report.details.get('visual_variety_score', 0)}",
        f"- native_reel_score: {report.details.get('native_reel_score', 0)}",
        f"- first_second_hook_score: {report.details.get('first_second_hook_score', 0)}",
        f"- scene_variety_score: {report.details.get('scene_variety_score', 0)}",
        f"- ai_slideshow_risk_score: {report.details.get('ai_slideshow_risk_score', 0)}",
        f"- cover_quality_score: {report.details.get('cover_quality_score', 0)}",
        f"- caption_sync_score: {report.details.get('caption_sync_score', 0)}",
        f"- kinetic_caption_score: {report.details.get('kinetic_caption_score', 0)}",
        f"- caption_readability_score: {report.details.get('caption_readability_score', 0)}",
        f"- caption_layout_score: {report.details.get('caption_layout_score', 0)}",
        f"- caption_collision_count: {report.details.get('caption_collision_count', 0)}",
        f"- caption_background_alignment_score: {report.details.get('caption_background_alignment_score', 0)}",
        f"- caption_safe_zone_score: {report.details.get('caption_safe_zone_score', 0)}",
        f"- duplicate_text_layer_detected: {str(report.details.get('duplicate_text_layer_detected', False)).lower()}",
        f"- active_word_highlight_used: {str(report.details.get('active_word_highlight_used', False)).lower()}",
        f"- caption_style: {report.details.get('caption_style', '')}",
        f"- voiceover_requested: {str(report.details.get('voiceover_requested', False)).lower()}",
        f"- voiceover_ready: {str(report.details.get('voiceover_ready', False)).lower()}",
        f"- voiceover_audio_stream_present: {str(report.details.get('voiceover_audio_stream_present', False)).lower()}",
        f"- voiceover_duration_seconds: {report.details.get('voiceover_duration_seconds', 0)}",
        f"- recommended_action: {report.recommended_action}",
        f"- artifact_detection_scope: {report.details.get('artifact_detection_scope', 'raw')}",
        "",
        "## Blocking Issues",
    ]
    if report.blocking_issues:
        lines.extend(f"- {issue}" for issue in report.blocking_issues)
    else:
        lines.append("- None")
    lines.extend(["", "## Warnings"])
    if report.warnings:
        lines.extend(f"- {warning}" for warning in report.warnings)
    else:
        lines.append("- None")
    lines.extend(["", "## Voiceover Checks"])
    lines.append(f"- reel_with_voice_path: {report.details.get('reel_with_voice_path', '')}")
    lines.append(f"- voiceover_quality_score: {report.details.get('voiceover_quality_score', 100)}")
    voiceover_blockers = report.details.get("voiceover_blocking_issues", [])
    if isinstance(voiceover_blockers, list) and voiceover_blockers:
        lines.extend(f"- {issue}" for issue in voiceover_blockers)
    else:
        lines.append("- None")
    lines.extend(["", "## Design Checks"])
    lines.append(f"- excessive_black_area_ratio: {report.details.get('excessive_black_area_ratio', 0)}")
    lines.append(f"- lower_black_area_ratio: {report.details.get('lower_black_area_ratio', 0)}")
    lines.append(f"- text_box_area_ratio: {report.details.get('text_box_area_ratio', 0)}")
    lines.append(f"- repeated_image_similarity: {report.details.get('repeated_image_similarity', 0)}")
    lines.append(f"- cover_native_9_16: {str(report.details.get('cover_native_9_16', False)).lower()}")
    lines.append(f"- reel_first_ready: {str(report.details.get('reel_first_ready', False)).lower()}")
    (output_dir / "post_quality_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _design_quality_report(output_dir: Path, final_paths: list[Path], metadata: dict[str, Any]) -> dict[str, Any]:
    black_ratios: list[float] = []
    lower_black_ratios: list[float] = []
    for path in final_paths:
        black, lower_black = _black_area_ratios(path)
        black_ratios.append(black)
        lower_black_ratios.append(lower_black)

    avg_black = _average(black_ratios)
    avg_lower_black = _average(lower_black_ratios)
    text_box_ratio = _max_text_box_area_ratio(metadata)
    visual_variety_score, repeated_similarity = _visual_variety(final_paths)
    reel_export = metadata.get("reel_export", {})
    reel_requested = isinstance(reel_export, dict) and bool(reel_export.get("requested"))
    cover_native = (not reel_requested) or _image_is_size(output_dir / "final_reel" / "cover.jpg", (1080, 1920))
    reel_dims = []
    if isinstance(reel_export, dict):
        reel_dims = reel_export.get("reel_dimensions", [])
    reel_native = (not reel_requested) or reel_dims == [1080, 1920] or (not reel_dims and not (output_dir / "final_reel" / "reel.mp4").exists())

    amateur_warnings: list[str] = []
    carousel_penalty = 0
    if avg_black > 0.54:
        amateur_warnings.append(f"Excessive black area across carousel slides ({avg_black:.2f}).")
        carousel_penalty += int((avg_black - 0.54) * 120)
    if avg_lower_black > 0.86:
        amateur_warnings.append(f"Lower slide area is too dark/empty ({avg_lower_black:.2f}).")
        carousel_penalty += int((avg_lower_black - 0.86) * 140)
    if text_box_ratio > 0.34:
        amateur_warnings.append(f"Text overlay regions cover too much image area ({text_box_ratio:.2f}).")
        carousel_penalty += int((text_box_ratio - 0.34) * 160)
    if visual_variety_score < 55:
        amateur_warnings.append("Slides have low visual variety; compositions may look repeated.")
        carousel_penalty += 12

    carousel_design_score = max(0, min(100, 92 - carousel_penalty + int((visual_variety_score - 70) * 0.12)))

    reel_penalty = 0
    if not cover_native:
        amateur_warnings.append("Reel cover is not a native 1080x1920 frame.")
        reel_penalty += 35
    if not reel_native:
        amateur_warnings.append("Reel video is not native 1080x1920.")
        reel_penalty += 35
    reel_penalty += max(0, int((avg_black - 0.58) * 90))
    reel_design_score = max(0, min(100, 94 - reel_penalty))

    design_score = round((carousel_design_score * 0.48) + (reel_design_score * 0.42) + (visual_variety_score * 0.10))
    layout_professionalism_score = max(0, min(100, 96 - carousel_penalty - (8 if text_box_ratio > 0.28 else 0)))
    reel_first_ready = design_score >= 70 and cover_native and reel_native and text_box_ratio <= 0.34

    if not reel_first_ready and design_score >= 70:
        amateur_warnings.append("Package is visually acceptable but not fully Reel-first ready.")

    recommended = "post" if reel_first_ready else "rerender_with_cinematic_reel_editorial"
    if design_score < 70:
        recommended = "regenerate_or_redesign_visuals"

    return {
        "design_score": design_score,
        "reel_design_score": reel_design_score,
        "carousel_design_score": carousel_design_score,
        "visual_variety_score": visual_variety_score,
        "layout_professionalism_score": layout_professionalism_score,
        "excessive_black_area_ratio": round(avg_black, 3),
        "lower_black_area_ratio": round(avg_lower_black, 3),
        "text_box_area_ratio": round(text_box_ratio, 3),
        "repeated_image_similarity": round(repeated_similarity, 3),
        "cover_native_9_16": cover_native,
        "reel_native_9_16": reel_native,
        "reel_first_ready": reel_first_ready,
        "amateur_template_warnings": _dedupe(amateur_warnings),
        "design_recommended_action": recommended,
    }


def _voiceover_quality_report(output_dir: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    voiceover = metadata.get("voiceover", {})
    voiceover_dict = voiceover if isinstance(voiceover, dict) else {}
    native_reel_quality = metadata.get("native_reel_quality", {})
    native_dict = native_reel_quality if isinstance(native_reel_quality, dict) else {}
    requested = bool(metadata.get("voiceover_requested", False) or native_dict.get("voiceover_requested", False))

    script_path = Path(str(voiceover_dict.get("script_path") or output_dir / "voiceover" / "voiceover_script.txt"))
    tts_path = Path(str(voiceover_dict.get("tts_path") or output_dir / "voiceover" / "voiceover.mp3"))
    reel_with_voice_path = Path(
        str(voiceover_dict.get("reel_with_voice_path") or output_dir / "final_reel" / "reel_with_voice.mp4")
    )
    subtitled_path = Path(
        str(
            voiceover_dict.get("reel_with_voice_subtitled_path")
            or voiceover_dict.get("subtitled_video_path")
            or output_dir / "final_reel" / "reel_with_voice_subtitled.mp4"
        )
    )
    kinetic_path = Path(
        str(
            voiceover_dict.get("reel_with_voice_kinetic_subtitles_path")
            or output_dir / "final_reel" / "reel_with_voice_kinetic_subtitles.mp4"
        )
    )
    srt_path = Path(str(voiceover_dict.get("subtitles_srt_path") or output_dir / "voiceover" / "subtitles.srt"))
    ass_path = Path(str(voiceover_dict.get("subtitles_ass_path") or output_dir / "voiceover" / "subtitles.ass"))

    mux_probe = _ffprobe_stream_summary(reel_with_voice_path)
    tts_probe = _ffprobe_stream_summary(tts_path)
    audio_stream = mux_probe["audio_stream"]
    video_stream = mux_probe["video_stream"]
    audio_duration = float(tts_probe["audio_duration_seconds"] or audio_stream.get("duration_seconds", 0.0) or 0.0)
    video_duration = float(video_stream.get("duration_seconds", 0.0) or mux_probe.get("format_duration_seconds", 0.0) or 0.0)
    audio_codec = str(audio_stream.get("codec_name", ""))
    has_audio_stream = bool(audio_stream)
    subtitled_probe = _ffprobe_stream_summary(subtitled_path)
    subtitled_has_audio = bool(subtitled_probe.get("audio_stream", {}))
    subtitles_created = srt_path.exists() and ass_path.exists()

    warnings: list[str] = []
    blockers: list[str] = []
    if requested:
        if not script_path.exists():
            blockers.append("Voiceover was requested but voiceover_script.txt is missing.")
        if not tts_path.exists():
            blockers.append("Voiceover was requested but voiceover audio is missing.")
        if not reel_with_voice_path.exists():
            blockers.append("Voiceover was requested but reel_with_voice.mp4 is missing.")
        if reel_with_voice_path.exists() and not has_audio_stream:
            blockers.append("Voiceover was requested but reel_with_voice.mp4 has no audio stream.")
        if tts_path.exists() and audio_duration <= 0.2:
            blockers.append("Voiceover audio duration is empty or near-zero.")
        elif audio_duration and not 3.0 <= audio_duration <= 25.0:
            warnings.append(f"Voiceover duration may be unusual: {audio_duration:.2f}s.")
        if audio_duration and video_duration and video_duration + 0.05 < audio_duration:
            blockers.append(
                f"Voiceover is longer than video ({audio_duration:.2f}s audio vs {video_duration:.2f}s video)."
            )
        if not subtitles_created:
            blockers.append("Voiceover was requested but subtitle files are missing.")
        if not subtitled_path.exists():
            blockers.append("Voiceover was requested but reel_with_voice_subtitled.mp4 is missing.")
        elif not subtitled_has_audio:
            blockers.append("Voiceover was requested but subtitled Reel has no audio stream.")
        if voiceover_dict.get("kinetic_subtitles_created") and not kinetic_path.exists():
            blockers.append("Kinetic subtitle output was expected but is missing.")

    score = 100
    if requested:
        score = 100 - min(70, 18 * len(blockers)) - min(20, 5 * len(warnings))
        if script_path.exists():
            score += 3
        if tts_path.exists():
            score += 3
        if has_audio_stream:
            score += 4
        score = max(0, min(100, score))

    return {
        "voiceover_requested": requested,
        "voiceover_ready": requested and not blockers and script_path.exists() and tts_path.exists() and has_audio_stream,
        "voiceover_script_path": str(script_path),
        "voiceover_audio_path": str(tts_path),
        "voiceover_audio_exists": tts_path.exists(),
        "voiceover_audio_stream_present": has_audio_stream,
        "voiceover_audio_codec": audio_codec,
        "voiceover_duration_seconds": round(audio_duration, 3),
        "voiceover_video_duration_seconds": round(video_duration, 3),
        "duration_sync_ok": not requested or not audio_duration or (video_duration + 0.05 >= audio_duration),
        "duration_mismatch_seconds": round(max(0.0, audio_duration - video_duration), 3),
        "reel_with_voice_path": str(reel_with_voice_path),
        "reel_with_voice_subtitled_path": str(subtitled_path),
        "reel_with_voice_kinetic_subtitles_path": str(kinetic_path),
        "kinetic_subtitles_created": kinetic_path.exists(),
        "subtitles_created": subtitles_created,
        "subtitles_burned_in": subtitled_path.exists() and subtitled_has_audio,
        "subtitle_sync_ok": subtitles_created and subtitled_path.exists() and (not audio_duration or video_duration + 0.05 >= audio_duration),
        "voiceover_quality_score": score,
        "voiceover_warnings": _dedupe(warnings),
        "voiceover_blocking_issues": _dedupe(blockers),
    }


def _ffprobe_stream_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"video_stream": {}, "audio_stream": {}, "format_duration_seconds": 0.0, "audio_duration_seconds": 0.0}
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"video_stream": {}, "audio_stream": {}, "format_duration_seconds": 0.0, "audio_duration_seconds": 0.0}
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return {"video_stream": {}, "audio_stream": {}, "format_duration_seconds": 0.0, "audio_duration_seconds": 0.0}
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {"video_stream": {}, "audio_stream": {}, "format_duration_seconds": 0.0, "audio_duration_seconds": 0.0}

    video_stream: dict[str, Any] = {}
    audio_stream: dict[str, Any] = {}
    for stream in payload.get("streams", []):
        if not isinstance(stream, dict):
            continue
        if stream.get("codec_type") == "video" and not video_stream:
            video_stream = {
                "codec_name": stream.get("codec_name", ""),
                "width": int(stream.get("width", 0) or 0),
                "height": int(stream.get("height", 0) or 0),
                "duration_seconds": _float_or_zero(stream.get("duration")),
            }
        if stream.get("codec_type") == "audio" and not audio_stream:
            audio_stream = {
                "codec_name": stream.get("codec_name", ""),
                "duration_seconds": _float_or_zero(stream.get("duration")),
            }
    format_payload = payload.get("format", {})
    format_duration = _float_or_zero(format_payload.get("duration")) if isinstance(format_payload, dict) else 0.0
    audio_duration = float(audio_stream.get("duration_seconds", 0.0) or format_duration if audio_stream else 0.0)
    return {
        "video_stream": video_stream,
        "audio_stream": audio_stream,
        "format_duration_seconds": format_duration,
        "audio_duration_seconds": audio_duration,
    }


def _black_area_ratios(path: Path) -> tuple[float, float]:
    try:
        with Image.open(path) as image:
            lum = image.convert("L")
            width, height = lum.size
            black = _pixel_ratio_below(lum, 28)
            lower = lum.crop((0, int(height * 0.62), width, height))
            lower_black = _pixel_ratio_below(lower, 35)
            return black, lower_black
    except Exception:
        return 1.0, 1.0


def _pixel_ratio_below(image: Image.Image, threshold: int) -> float:
    histogram = image.histogram()
    dark_pixels = sum(histogram[:threshold])
    total = max(1, image.width * image.height)
    return dark_pixels / total


def _max_text_box_area_ratio(metadata: dict[str, Any]) -> float:
    regions = metadata.get("rendered_overlay_ignored_regions", {})
    if not isinstance(regions, dict):
        return 0.0
    max_ratio = 0.0
    total_area = CANVAS_SIZE[0] * CANVAS_SIZE[1]
    for slide_regions in regions.values():
        if not isinstance(slide_regions, list):
            continue
        area = 0
        for region in slide_regions:
            if not isinstance(region, dict):
                continue
            name = str(region.get("name", "")).lower()
            if "headline" not in name and "cta" not in name:
                continue
            box = region.get("box", [])
            if not isinstance(box, list) or len(box) != 4:
                continue
            left, top, right, bottom = [int(value) for value in box]
            area += max(0, right - left) * max(0, bottom - top)
        max_ratio = max(max_ratio, area / total_area)
    return max_ratio


def _visual_variety(paths: list[Path]) -> tuple[int, float]:
    if len(paths) < 2:
        return 80, 0.0
    rmse_values: list[float] = []
    prepared: list[Image.Image] = []
    for path in paths:
        try:
            image = Image.open(path).convert("L")
            width, height = image.size
            crop = image.crop((0, int(height * 0.08), width, int(height * 0.62)))
            prepared.append(crop.resize((72, 72), Image.Resampling.BILINEAR))
        except Exception:
            continue
    for first, second in zip(prepared, prepared[1:]):
        diff = ImageChops.difference(first, second)
        stat = ImageStat.Stat(diff)
        rmse_values.append(stat.rms[0])
    if not rmse_values:
        return 45, 1.0
    avg_rmse = _average(rmse_values)
    score = round(max(0, min(100, 24 + avg_rmse * 2.4)))
    similarity = max(0.0, min(1.0, 1 - (avg_rmse / 58)))
    return score, similarity


def _image_is_size(path: Path, expected: tuple[int, int]) -> bool:
    try:
        with Image.open(path) as image:
            return image.size == expected
    except Exception:
        return False


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _dimension_warnings(paths: list[Path]) -> list[str]:
    warnings: list[str] = []
    for path in paths:
        try:
            with Image.open(path) as image:
                if image.size != CANVAS_SIZE:
                    warnings.append(f"{path.name} has dimensions {image.width}x{image.height}, expected 1080x1350.")
        except Exception as exc:
            warnings.append(f"{path.name} could not be inspected: {exc}.")
    return warnings


def _recommended_action(
    blocking: list[str],
    high_artifact_slides: list[str],
    failed_quality_slides: list[str],
) -> str:
    if not blocking:
        return "post"
    if high_artifact_slides or failed_quality_slides:
        return "regenerate_bad_slides"
    if any("design score" in issue.lower() or "reel cover" in issue.lower() or "reel video" in issue.lower() for issue in blocking):
        return "regenerate_or_redesign_visuals"
    if any("final slide" in issue.lower() or "dimension" in issue.lower() for issue in blocking):
        return "rerender"
    return "reject"


def _cta_warning(plan: CarouselPlan) -> str:
    if not plan.slides:
        return "No CTA slide is available."
    final_slide = plan.slides[-1]
    text = f"{final_slide.headline} {final_slide.subtext}".lower()
    if final_slide.role not in {"CTA", "final"}:
        return "Final slide is not marked as CTA/final."
    if not any(term in text for term in ("save", "follow", "comment", "share", "would", "which", "?")):
        return "Final CTA slide may be weak or unclear."
    return ""


def _dict_of_numbers(value: object) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, float] = {}
    for key, raw in value.items():
        try:
            result[str(key)] = float(raw)
        except (TypeError, ValueError):
            continue
    return result


def _float_or_zero(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            result.append(value)
            seen.add(key)
    return result
