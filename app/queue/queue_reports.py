"""Report writers for weekly queues."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.discovery.schemas import TopicCandidate


def write_queue_plan_preview(queue_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    json_path = queue_dir / "queue_plan_preview.json"
    md_path = queue_dir / "queue_plan_preview.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Weekly Queue Plan Preview",
        "",
        f"- queue folder: {payload.get('queue_dir', '')}",
        f"- niche: {payload.get('niche', '')}",
        f"- lane: {payload.get('lane', '')}",
        f"- days: {payload.get('days', 0)}",
        f"- candidates per day: {payload.get('candidates_per_day', 0)}",
        f"- dry run: {str(payload.get('dry_run', False)).lower()}",
        "",
        "## Days",
    ]
    for day in payload.get("days_plan", []):
        if not isinstance(day, dict):
            continue
        lines.append("")
        lines.append(f"### Day {day.get('day', '')}")
        topics = day.get("topics", [])
        if isinstance(topics, list):
            for index, topic in enumerate(topics, start=1):
                if isinstance(topic, dict):
                    lines.append(
                        f"{index}. {topic.get('topic', '')} | lane={topic.get('lane', '')} | score={topic.get('score', 0)}"
                    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def write_day_report(day_dir: Path, day: int, candidates: list[dict[str, Any]], best: dict[str, Any]) -> tuple[Path, Path]:
    payload = {
        "day": day,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "best_candidate": best,
    }
    json_path = day_dir / "day_report.json"
    md_path = day_dir / "day_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"# Day {day:02d} Report",
        "",
        f"- candidate count: {len(candidates)}",
        f"- best topic: {best.get('topic', '')}",
        f"- best score: {best.get('candidate_score', 0)}",
        "",
        "## Candidates",
    ]
    for candidate in candidates:
        lines.append(
            f"- {candidate.get('topic', '')} | score={candidate.get('candidate_score', 0)} | "
            f"publish_ready={str(candidate.get('publish_ready', False)).lower()}"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def write_weekly_queue_report(queue_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    json_path = queue_dir / "weekly_queue_report.json"
    md_path = queue_dir / "weekly_queue_report.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Weekly Queue Report",
        "",
        f"- queue folder: {payload.get('queue_dir', '')}",
        f"- generated days: {payload.get('generated_days', 0)}",
        f"- upload manifest: {payload.get('upload_manifest_path', '')}",
        f"- contact sheet: {payload.get('queue_contact_sheet_path', '')}",
        "",
        "## Selected Posts",
    ]
    for result in payload.get("days", []):
        if not isinstance(result, dict):
            continue
        best = result.get("best_candidate", {})
        best_dict = best if isinstance(best, dict) else {}
        lines.append(
            f"- day {result.get('day', '')}: {best_dict.get('topic', '')} "
            f"(score={best_dict.get('candidate_score', 0)}, ready={str(best_dict.get('publish_ready', False)).lower()})"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def write_review_checklist(queue_dir: Path, day_results: list[dict[str, Any]]) -> Path:
    path = queue_dir / "review_checklist.md"
    lines = [
        "# Review Checklist",
        "",
        "- Confirm each cover is readable at phone size.",
        "- Watch each reel_with_voice file before upload.",
        "- Check captions and hashtags for topic alignment.",
        "- Confirm no visible AI text artifacts or watermarks.",
        "- Confirm upload order matches upload_manifest.csv.",
        "",
        "## Days",
    ]
    for result in day_results:
        best = result.get("best_candidate", {})
        best_dict = best if isinstance(best, dict) else {}
        lines.append(f"- [ ] Day {result.get('day', '')}: {best_dict.get('topic', '')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def topic_payload(candidate: TopicCandidate) -> dict[str, Any]:
    return candidate.model_dump()

