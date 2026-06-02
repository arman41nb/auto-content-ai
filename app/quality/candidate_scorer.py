"""Score native Reel candidates for batch comparison."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


WEIGHTS = {
    "first_second_hook_score": 0.20,
    "native_reel_score": 0.20,
    "scene_variety_score": 0.15,
    "voiceover_quality_score": 0.10,
    "cover_quality_score": 0.10,
    "topic_growth_score": 0.15,
    "technical_quality_score": 0.10,
}


def score_candidate_folder(candidate_dir: Path, voiceover_requested: bool = True) -> dict[str, Any]:
    metadata = _read_json(candidate_dir / "metadata.json")
    native = _read_json(candidate_dir / "native_reel_quality_report.json")
    post = _read_json(candidate_dir / "post_quality_report.json")
    plan = _read_json(candidate_dir / "carousel_plan.json")
    human_review = _read_json(candidate_dir / "human_review.json")

    native = _dict(native or metadata.get("native_reel_quality", {}))
    rejected = str(human_review.get("status", "")).lower() == "rejected" or bool(human_review.get("do_not_post", False))
    publish_ready = bool(post.get("publish_ready", False) and native.get("publish_ready", False)) and not rejected
    topic = str(metadata.get("topic") or plan.get("topic") or candidate_dir.name)
    lane = str(metadata.get("topic_discovery_lane") or _read_json(candidate_dir / "topic_discovery_selected.json").get("lane", "any"))
    reel_export = _dict(metadata.get("reel_export", {}))
    voiceover = _dict(metadata.get("voiceover", {}))

    native_reel_score = _int(native.get("native_reel_score"))
    first_second_hook_score = _int(native.get("first_second_hook_score"))
    scene_variety_score = _int(native.get("scene_variety_score"))
    voiceover_quality_score = _int(post.get("voiceover_quality_score", native.get("voiceover_quality_score", 100)))
    cover_quality_score = _int(native.get("cover_quality_score"))
    ai_slideshow_risk_score = _int(native.get("ai_slideshow_risk_score", 100))
    topic_growth_score = _topic_growth_score(metadata)
    technical_quality_score = _technical_quality_score(post, native, reel_export)
    caption_quality_score = _caption_quality_score(metadata, plan)
    duration_fit_score = _duration_fit_score(candidate_dir)
    audio_stream_present = bool(post.get("voiceover_audio_stream_present", False))
    artifact_risk = _artifact_risk(metadata, native)

    weighted = (
        first_second_hook_score * WEIGHTS["first_second_hook_score"]
        + native_reel_score * WEIGHTS["native_reel_score"]
        + scene_variety_score * WEIGHTS["scene_variety_score"]
        + voiceover_quality_score * WEIGHTS["voiceover_quality_score"]
        + cover_quality_score * WEIGHTS["cover_quality_score"]
        + topic_growth_score * WEIGHTS["topic_growth_score"]
        + technical_quality_score * WEIGHTS["technical_quality_score"]
    )
    bonus_adjustment = (caption_quality_score - 80) * 0.03 + (duration_fit_score - 80) * 0.02
    candidate_score = round(max(0, min(100, weighted + bonus_adjustment)))

    warnings: list[str] = []
    if rejected:
        candidate_score = 0
        warnings.append("human_review=rejected caps candidate_score at 0.")
    if not publish_ready:
        candidate_score = min(candidate_score, 60)
        warnings.append("publish_ready=false caps candidate_score at 60.")
    if voiceover_requested and not audio_stream_present:
        candidate_score = min(candidate_score, 50)
        warnings.append("voiceover requested but reel_with_voice has no confirmed audio stream.")
    if artifact_risk >= 70:
        candidate_score = min(candidate_score, 50)
        warnings.append(f"visible artifact risk is high ({artifact_risk:.1f}).")
    if ai_slideshow_risk_score > 60:
        candidate_score = min(candidate_score, 55)
        warnings.append(f"ai_slideshow_risk_score is above 60 ({ai_slideshow_risk_score}).")

    weaknesses = _weaknesses(
        post=post,
        native=native,
        audio_stream_present=audio_stream_present,
        artifact_risk=artifact_risk,
        caption_quality_score=caption_quality_score,
        warnings=warnings,
    )
    reel_with_voice_path = str(
        post.get("reel_with_voice_path")
        or voiceover.get("reel_with_voice_path")
        or candidate_dir / "final_reel" / "reel_with_voice.mp4"
    )
    cover_path = str(native.get("cover_path") or reel_export.get("cover_path") or candidate_dir / "final_reel" / "cover.jpg")

    return {
        "topic": topic,
        "lane": lane,
        "output_folder": str(candidate_dir),
        "publish_ready": publish_ready,
        "candidate_score": candidate_score,
        "native_reel_score": native_reel_score,
        "first_second_hook_score": first_second_hook_score,
        "scene_variety_score": scene_variety_score,
        "voiceover_quality_score": voiceover_quality_score,
        "cover_quality_score": cover_quality_score,
        "topic_growth_score": topic_growth_score,
        "technical_quality_score": technical_quality_score,
        "duration_fit_score": duration_fit_score,
        "audio_stream_present": audio_stream_present,
        "caption_quality_score": caption_quality_score,
        "ai_slideshow_risk_score": ai_slideshow_risk_score,
        "artifact_risk_score": round(artifact_risk, 2),
        "reel_with_voice_path": reel_with_voice_path,
        "reel_path": str(reel_export.get("reel_path") or native.get("reel_path") or candidate_dir / "final_reel" / "reel.mp4"),
        "cover_path": cover_path,
        "caption_path": str(candidate_dir / "caption.txt"),
        "hashtags_path": str(candidate_dir / "hashtags.txt"),
        "main_weaknesses": weaknesses,
        "reasons": _reasons(native_reel_score, first_second_hook_score, scene_variety_score, topic_growth_score),
        "warnings": warnings,
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _topic_growth_score(metadata: dict[str, Any]) -> int:
    direct = _int(metadata.get("topic_discovery_score"), 0)
    if direct:
        return max(0, min(100, direct))
    scores = _dict(metadata.get("topic_discovery_growth_scores", {}))
    values = [_int(value, 0) for value in scores.values()]
    values = [value for value in values if value > 0]
    return round(sum(values) / len(values)) if values else 70


def _technical_quality_score(post: dict[str, Any], native: dict[str, Any], reel_export: dict[str, Any]) -> int:
    base = _int(post.get("score"), _int(native.get("technical_score"), 0))
    if base <= 0:
        base = 65
    if not reel_export.get("created_video", False):
        base -= 15
    if not native.get("cover_native_1080x1920", False):
        base -= 10
    if not native.get("reel_native_1080x1920", False):
        base -= 10
    return max(0, min(100, base))


def _caption_quality_score(metadata: dict[str, Any], plan: dict[str, Any]) -> int:
    score = _int(metadata.get("caption_alignment_score"), 100)
    caption = str(plan.get("caption", ""))
    if len(caption.split()) < 20:
        score -= 12
    warnings = metadata.get("caption_quality_warnings", [])
    if isinstance(warnings, list):
        score -= min(25, len(warnings) * 5)
    return max(0, min(100, score))


def _duration_fit_score(candidate_dir: Path) -> int:
    reel_plan = _read_json(candidate_dir / "reel_plan.json")
    scenes = reel_plan.get("scenes", [])
    if not isinstance(scenes, list):
        return 70
    total = 0.0
    for scene in scenes:
        if isinstance(scene, dict):
            try:
                total += float(scene.get("duration_seconds", 0))
            except (TypeError, ValueError):
                pass
    if 8.0 <= total <= 12.0:
        return 100
    if 6.0 <= total <= 15.0:
        return 75
    return 40


def _artifact_risk(metadata: dict[str, Any], native: dict[str, Any]) -> float:
    native_risk = native.get("obvious_ai_text_or_watermark_risk")
    try:
        risk = float(native_risk)
    except (TypeError, ValueError):
        risk = 0.0
    scores = metadata.get("artifact_risk_score_per_slide", {})
    if isinstance(scores, dict):
        for value in scores.values():
            try:
                risk = max(risk, float(value))
            except (TypeError, ValueError):
                continue
    return risk


def _weaknesses(
    post: dict[str, Any],
    native: dict[str, Any],
    audio_stream_present: bool,
    artifact_risk: float,
    caption_quality_score: int,
    warnings: list[str],
) -> list[str]:
    weaknesses: list[str] = []
    for source in (post.get("blocking_issues", []), native.get("blocking_issues", [])):
        if isinstance(source, list):
            weaknesses.extend(str(item) for item in source[:4])
    if not audio_stream_present:
        weaknesses.append("No confirmed audio stream in reel_with_voice.")
    if artifact_risk >= 70:
        weaknesses.append("High visible artifact risk.")
    if caption_quality_score < 70:
        weaknesses.append("Caption quality or alignment is weak.")
    weaknesses.extend(warnings)
    return _dedupe(weaknesses)[:8]


def _reasons(
    native_reel_score: int,
    first_second_hook_score: int,
    scene_variety_score: int,
    topic_growth_score: int,
) -> list[str]:
    reasons: list[str] = []
    if first_second_hook_score >= 85:
        reasons.append("Strong first-second hook.")
    if native_reel_score >= 80:
        reasons.append("Strong native Reel quality score.")
    if scene_variety_score >= 75:
        reasons.append("Good scene variety.")
    if topic_growth_score >= 80:
        reasons.append("High topic growth score.")
    return reasons or ["Highest weighted batch score."]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = value.strip().lower()
        if key and key not in seen:
            result.append(value)
            seen.add(key)
    return result
