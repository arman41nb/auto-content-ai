"""CSV manifest helpers for weekly queues."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


MANIFEST_FIELDS = [
    "day",
    "topic",
    "lane",
    "candidate_score",
    "publish_ready",
    "output_folder",
    "reel_with_voice_path",
    "cover_path",
    "caption_path",
    "hashtags_path",
]


def write_upload_manifest(queue_dir: Path, day_results: list[dict[str, Any]]) -> Path:
    path = queue_dir / "upload_manifest.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for result in day_results:
            best = result.get("best_candidate", {})
            best_dict = best if isinstance(best, dict) else {}
            writer.writerow(
                {
                    "day": result.get("day", ""),
                    "topic": best_dict.get("topic", ""),
                    "lane": best_dict.get("lane", ""),
                    "candidate_score": best_dict.get("candidate_score", 0),
                    "publish_ready": best_dict.get("publish_ready", False),
                    "output_folder": best_dict.get("output_folder", ""),
                    "reel_with_voice_path": best_dict.get("reel_with_voice_path", ""),
                    "cover_path": best_dict.get("cover_path", ""),
                    "caption_path": best_dict.get("caption_path", ""),
                    "hashtags_path": best_dict.get("hashtags_path", ""),
                }
            )
    return path

