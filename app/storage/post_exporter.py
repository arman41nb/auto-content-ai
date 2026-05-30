"""Export generated carousel packages to disk."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.content.schemas import CarouselPlan
from app.storage.slug import slugify


class PostExporter:
    def __init__(self, outputs_root: Path) -> None:
        self.outputs_root = outputs_root

    def create_output_dir(self, topic: str, created_at: datetime) -> Path:
        base_name = f"{created_at:%Y-%m-%d}_{slugify(topic)}"
        self.outputs_root.mkdir(parents=True, exist_ok=True)
        candidate = self.outputs_root / base_name
        suffix = 2
        while candidate.exists():
            candidate = self.outputs_root / f"{base_name}_{suffix}"
            suffix += 1
        candidate.mkdir(parents=True)
        return candidate

    def save_plan(self, output_dir: Path, plan: CarouselPlan) -> None:
        self._write_json(output_dir / "carousel_plan.json", plan.model_dump())
        (output_dir / "caption.txt").write_text(plan.caption.strip() + "\n", encoding="utf-8")
        hashtags = " ".join(f"#{tag}" for tag in plan.hashtags)
        (output_dir / "hashtags.txt").write_text(hashtags + "\n", encoding="utf-8")

    def save_metadata(self, output_dir: Path, metadata: dict[str, Any]) -> None:
        self._write_json(output_dir / "metadata.json", metadata)

    def save_image_selection_report(self, output_dir: Path, report: dict[str, Any]) -> None:
        self._write_json(output_dir / "image_selection_report.json", report)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
