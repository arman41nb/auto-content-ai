"""Weekly queue command implementation."""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from app.config import load_config
from app.discovery.discovery_pipeline import DiscoveryPipeline
from app.discovery.schemas import TopicCandidate
from app.quality.candidate_scorer import score_candidate_folder
from app.queue.queue_contact_sheet import create_queue_contact_sheet
from app.queue.queue_manifest import write_upload_manifest
from app.queue.queue_reports import (
    topic_payload,
    write_day_report,
    write_queue_plan_preview,
    write_review_checklist,
    write_weekly_queue_report,
)


BatchRunner = Callable[[argparse.Namespace], int]


def run_weekly_queue(args: argparse.Namespace, batch_runner: BatchRunner) -> int:
    days = int(getattr(args, "days", 0) or 0)
    candidates_per_day = int(getattr(args, "candidates_per_day", 0) or 0)
    if days < 1:
        raise ValueError("--days must be at least 1.")
    if candidates_per_day < 1:
        raise ValueError("--candidates-per-day must be at least 1.")
    if str(getattr(args, "template", "") or "") != "native_reel_story":
        raise ValueError("weekly-queue MVP requires --template native_reel_story.")

    config = load_config()
    queue_dir = resolve_queue_dir(config.project_root, getattr(args, "queue_dir", None))

    if getattr(args, "score_only", False):
        if not getattr(args, "queue_dir", None):
            raise ValueError("--score-only requires --queue-dir.")
        if not queue_dir.exists():
            raise ValueError(f"Queue directory not found: {queue_dir}")
        write_queue_config(queue_dir, args)
        payload = score_existing_queue(queue_dir=queue_dir, args=args)
        print(f"weekly queue report: {payload.get('weekly_queue_report_path', '')}")
        return 0

    queue_dir.mkdir(parents=True, exist_ok=True)
    write_queue_config(queue_dir, args)

    total_generations = days * candidates_per_day
    max_full = getattr(args, "max_full_generations", None)
    if not getattr(args, "dry_run", False):
        if max_full is None:
            raise ValueError(
                "--max-full-generations is required for real weekly queues. "
                f"This run would generate {total_generations} candidate(s)."
            )
        if total_generations > int(max_full):
            raise ValueError(
                f"Refusing to generate {total_generations} candidate(s); "
                f"--max-full-generations is {max_full}."
            )

    selected = discover_weekly_topics(args, total_generations)
    if len(selected) < total_generations:
        raise ValueError(f"Only found {len(selected)} unique topic(s) for requested {total_generations}.")
    days_plan = assign_topics_to_days(selected, days=days, candidates_per_day=candidates_per_day)
    preview_payload = build_preview_payload(queue_dir, args, days_plan)
    preview_json, preview_md = write_queue_plan_preview(queue_dir, preview_payload)

    if getattr(args, "dry_run", False):
        print(f"weekly queue dry run: {preview_json}")
        print(f"weekly queue dry run markdown: {preview_md}")
        return 0

    day_results: list[dict[str, Any]] = []
    for day_plan in days_plan:
        day = int(day_plan["day"])
        day_dir = queue_dir / f"day_{day:02d}"
        day_dir.mkdir(parents=True, exist_ok=True)
        result = run_day_generation(day_dir=day_dir, day_plan=day_plan, args=args, batch_runner=batch_runner)
        day_results.append(result)

    payload = finalize_queue_reports(queue_dir=queue_dir, args=args, day_results=day_results)
    print(f"weekly queue report: {payload.get('weekly_queue_report_path', '')}")
    return 0


def resolve_queue_dir(project_root: Path, value: object) -> Path:
    if value:
        path = Path(str(value))
        return path if path.is_absolute() else project_root / path
    root = project_root / "outputs" / "queues"
    base = f"{date.today():%Y-%m-%d}_weekly_queue"
    index = 1
    while True:
        candidate = root / f"{base}_{index:02d}"
        if not candidate.exists():
            return candidate
        index += 1


def discover_weekly_topics(args: argparse.Namespace, count: int) -> list[TopicCandidate]:
    sources = [item.strip() for item in str(args.sources).split(",") if item.strip()]
    if not sources:
        raise ValueError("--sources must include at least one source.")
    if str(args.lane) != "any":
        pipeline = DiscoveryPipeline.from_names(sources)
        candidates = pipeline.discover(niche=args.niche, count=max(count * 4, count), lane=args.lane)
        return diverse_weekly_selection(candidates, count)

    by_lane: dict[str, list[TopicCandidate]] = {}
    for lane in ("what_if_disaster", "extreme_science", "future_scenario"):
        pipeline = DiscoveryPipeline.from_names(sources)
        by_lane[lane] = pipeline.discover(niche=args.niche, count=max(count * 2, 10), lane=lane)
    pool: list[TopicCandidate] = []
    max_len = max((len(items) for items in by_lane.values()), default=0)
    for index in range(max_len):
        for lane in ("what_if_disaster", "extreme_science", "future_scenario"):
            items = by_lane.get(lane, [])
            if index < len(items):
                pool.append(items[index])
    return diverse_weekly_selection(pool, count)


def diverse_weekly_selection(candidates: list[TopicCandidate], count: int) -> list[TopicCandidate]:
    selected: list[TopicCandidate] = []
    seen_topics: set[str] = set()
    flood_like_count = 0
    for candidate in candidates:
        key = normalize_topic_key(candidate.topic)
        if key in seen_topics:
            continue
        flood_like = topic_is_flood_like(candidate)
        if flood_like and flood_like_count >= 2:
            continue
        selected.append(candidate)
        seen_topics.add(key)
        if flood_like:
            flood_like_count += 1
        if len(selected) == count:
            return selected

    for candidate in candidates:
        key = normalize_topic_key(candidate.topic)
        if key in seen_topics:
            continue
        selected.append(candidate)
        seen_topics.add(key)
        if len(selected) == count:
            break
    return selected


def assign_topics_to_days(
    selected: list[TopicCandidate],
    days: int,
    candidates_per_day: int,
) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    for day in range(1, days + 1):
        start = (day - 1) * candidates_per_day
        topics = selected[start : start + candidates_per_day]
        plans.append({"day": day, "topics": topics})
    return plans


def build_preview_payload(queue_dir: Path, args: argparse.Namespace, days_plan: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "queue_dir": str(queue_dir),
        "created_at": datetime.now().astimezone().isoformat(),
        "niche": args.niche,
        "lane": args.lane,
        "days": int(args.days),
        "candidates_per_day": int(args.candidates_per_day),
        "sources": args.sources,
        "dry_run": bool(getattr(args, "dry_run", False)),
        "llm_called": False,
        "pollinations_called": False,
        "videos_rendered": False,
        "days_plan": [
            {
                "day": item["day"],
                "topics": [topic_payload(candidate) for candidate in item["topics"]],
            }
            for item in days_plan
        ],
    }


def run_day_generation(
    day_dir: Path,
    day_plan: dict[str, Any],
    args: argparse.Namespace,
    batch_runner: BatchRunner,
) -> dict[str, Any]:
    topics = day_plan["topics"]
    write_day_topics(day_dir, topics)
    batch_args = argparse.Namespace(
        command="batch-reels",
        niche=args.niche,
        lane=args.lane,
        count=len(topics),
        sources=args.sources,
        handle=args.handle,
        image_variants=args.image_variants,
        rate_limit=args.rate_limit,
        llm_provider=args.llm_provider,
        template="native_reel_story",
        voiceover=bool(getattr(args, "voiceover", False)),
        tts_provider=args.tts_provider,
        voice=args.voice,
        voice_rate=args.voice_rate,
        batch_dir=str(day_dir),
        score_only=False,
        command_used=command_text(args),
        weekly_queue_topics=topics,
    )
    result = batch_runner(batch_args)
    if result != 0:
        raise ValueError(f"day_{int(day_plan['day']):02d} generation returned exit code {result}.")
    return score_day(day_dir=day_dir, day=int(day_plan["day"]), args=args)


def score_existing_queue(queue_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    day_results: list[dict[str, Any]] = []
    for day_dir in sorted(path for path in queue_dir.glob("day_*") if path.is_dir()):
        try:
            day = int(day_dir.name.split("_", 1)[1])
        except (IndexError, ValueError):
            continue
        day_results.append(score_day(day_dir=day_dir, day=day, args=args))
    return finalize_queue_reports(queue_dir=queue_dir, args=args, day_results=day_results)


def score_day(day_dir: Path, day: int, args: argparse.Namespace) -> dict[str, Any]:
    candidate_dirs = sorted(path for path in day_dir.glob("candidate_*") if path.is_dir())
    candidates = [
        score_candidate_folder(candidate_dir, voiceover_requested=bool(getattr(args, "voiceover", True)))
        for candidate_dir in candidate_dirs
        if (candidate_dir / "metadata.json").exists()
    ]
    candidates.sort(key=lambda item: (int(item.get("candidate_score", 0)), int(item.get("native_reel_score", 0))), reverse=True)
    best = candidates[0] if candidates else empty_best_candidate()
    (day_dir / "best_candidate.json").write_text(json.dumps(best, ensure_ascii=False, indent=2), encoding="utf-8")
    write_day_report(day_dir, day=day, candidates=candidates, best=best)
    return {"day": day, "day_dir": str(day_dir), "candidates": candidates, "best_candidate": best}


def finalize_queue_reports(queue_dir: Path, args: argparse.Namespace, day_results: list[dict[str, Any]]) -> dict[str, Any]:
    manifest_path = write_upload_manifest(queue_dir, day_results)
    checklist_path = write_review_checklist(queue_dir, day_results)
    contact_sheet_path = create_queue_contact_sheet(day_results, queue_dir / "queue_contact_sheet.jpg")
    payload = {
        "queue_dir": str(queue_dir),
        "created_at": datetime.now().astimezone().isoformat(),
        "command_used": command_text(args),
        "generated_days": len(day_results),
        "days": day_results,
        "upload_manifest_path": str(manifest_path),
        "review_checklist_path": str(checklist_path),
        "queue_contact_sheet_path": str(contact_sheet_path),
        "ready_for_fully_automatic_posting": False,
    }
    report_json, report_md = write_weekly_queue_report(queue_dir, payload)
    payload["weekly_queue_report_path"] = str(report_md)
    payload["weekly_queue_report_json_path"] = str(report_json)
    report_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def write_queue_config(queue_dir: Path, args: argparse.Namespace) -> Path:
    payload = {
        "niche": args.niche,
        "lane": args.lane,
        "days": int(args.days),
        "candidates_per_day": int(args.candidates_per_day),
        "sources": args.sources,
        "handle": args.handle,
        "image_variants": int(args.image_variants),
        "rate_limit": args.rate_limit,
        "llm_provider": args.llm_provider,
        "template": args.template,
        "voiceover": bool(getattr(args, "voiceover", False)),
        "dry_run": bool(getattr(args, "dry_run", False)),
        "score_only": bool(getattr(args, "score_only", False)),
        "max_full_generations": getattr(args, "max_full_generations", None),
    }
    path = queue_dir / "queue_config.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_day_topics(day_dir: Path, topics: list[TopicCandidate]) -> None:
    payload = {"candidates": [topic_payload(candidate) for candidate in topics]}
    (day_dir / "batch_topics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Batch Topics", ""]
    for index, candidate in enumerate(topics, start=1):
        lines.append(f"{index}. {candidate.topic} | lane={candidate.lane} | score={candidate.score}")
    (day_dir / "batch_topics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def empty_best_candidate() -> dict[str, Any]:
    return {
        "topic": "",
        "lane": "",
        "output_folder": "",
        "reel_with_voice_path": "",
        "cover_path": "",
        "caption_path": "",
        "hashtags_path": "",
        "candidate_score": 0,
        "publish_ready": False,
        "reasons": [],
        "warnings": ["No candidates were available to score."],
    }


def normalize_topic_key(topic: str) -> str:
    return " ".join(topic.lower().strip().split())


def topic_is_flood_like(candidate: TopicCandidate) -> bool:
    text = " ".join([candidate.topic, candidate.angle, " ".join(candidate.keywords)]).lower()
    return any(term in text for term in ("ocean", "flood", "tsunami", "tide", "water", "iceberg"))


def command_text(args: argparse.Namespace) -> str:
    existing = getattr(args, "command_used", "")
    if existing:
        return str(existing)
    return "python -m app.main weekly-queue"
