"""Create weekly queue contact sheets."""

from __future__ import annotations

from pathlib import Path

from app.quality.contact_sheet import create_batch_contact_sheet


def create_queue_contact_sheet(day_results: list[dict[str, object]], output_path: Path) -> Path:
    candidates: list[dict[str, object]] = []
    for result in day_results:
        best = result.get("best_candidate", {})
        if isinstance(best, dict) and best:
            candidate = dict(best)
            candidate["topic"] = f"Day {result.get('day', '')}: {candidate.get('topic', '')}".strip()
            candidates.append(candidate)
    return create_batch_contact_sheet(candidates, output_path)

