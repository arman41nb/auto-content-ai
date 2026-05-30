"""Discovery orchestration and report writing."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

from app.discovery.schemas import DiscoveryLane, TopicCandidate
from app.discovery.sources.base import DiscoverySource
from app.discovery.sources.gdelt_source import GdeltSource
from app.discovery.sources.nasa_source import NasaSource
from app.discovery.sources.static_seed_source import StaticSeedSource
from app.discovery.sources.wikipedia_source import WikipediaSource
from app.discovery.topic_scorer import score_candidates
from app.discovery.topic_selector import select_top_topics


SOURCE_FACTORIES = {
    "static": StaticSeedSource,
    "nasa": NasaSource,
    "wikipedia": WikipediaSource,
    "gdelt": GdeltSource,
}


class DiscoveryPipeline:
    def __init__(self, sources: list[DiscoverySource]) -> None:
        self.sources = sources
        self.warnings: list[str] = []

    @classmethod
    def from_names(cls, source_names: list[str]) -> "DiscoveryPipeline":
        sources: list[DiscoverySource] = []
        for name in source_names:
            normalized = name.strip().lower()
            factory = SOURCE_FACTORIES.get(normalized)
            if factory is None:
                raise ValueError(f"Unknown discovery source '{name}'. Use static,nasa,wikipedia,gdelt.")
            sources.append(factory())
        return cls(sources)

    def discover(
        self,
        niche: str,
        count: int,
        query: str | None = None,
        lane: DiscoveryLane = "any",
    ) -> list[TopicCandidate]:
        niche = niche.strip().lower()
        lane = lane.strip().lower()  # type: ignore[assignment]
        raw_candidates: list[TopicCandidate] = []
        per_source_count = max(count * 3 if lane == "any" else count, 5)
        self.warnings = []

        for source in self.sources:
            try:
                candidates = source.fetch(niche=niche, count=per_source_count, query=query, lane=lane)
                raw_candidates.extend(candidates)
            except Exception as exc:
                warning = f"{source.name} source failed: {exc}"
                self.warnings.append(warning)
                print(f"Warning: {warning}", file=sys.stderr)

        if not raw_candidates and not any(source.name == "static" for source in self.sources):
            try:
                fallback = StaticSeedSource().fetch(niche=niche, count=per_source_count, query=query, lane=lane)
                raw_candidates.extend(fallback)
                self.warnings.append("Used StaticSeedSource fallback because external sources returned no candidates.")
            except Exception as exc:
                self.warnings.append(f"Static fallback failed: {exc}")

        scored = score_candidates(raw_candidates)
        return select_top_topics(scored, count)


def write_discovery_reports(
    candidates: list[TopicCandidate],
    output_dir: Path,
    niche: str,
    lane: DiscoveryLane = "any",
    report_date: date | None = None,
    warnings: list[str] | None = None,
) -> tuple[Path, Path]:
    report_date = report_date or date.today()
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"{report_date:%Y-%m-%d}_{niche}_{lane}_topics"
    json_path = output_dir / f"{base_name}.json"
    md_path = output_dir / f"{base_name}.md"

    payload = {
        "date": report_date.isoformat(),
        "niche": niche,
        "lane": lane,
        "warnings": warnings or [],
        "candidates": [candidate.model_dump() for candidate in candidates],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(candidates, niche=niche, lane=lane, warnings=warnings or []), encoding="utf-8")
    return json_path, md_path


def _build_markdown(candidates: list[TopicCandidate], niche: str, lane: str, warnings: list[str]) -> str:
    lines = [f"# Topic Discovery: {niche} / {lane}", ""]
    if warnings:
        lines.append("## Warnings")
        lines.extend(f"- {warning}" for warning in warnings)
        lines.append("")
    lines.append("## Ranked Topics")
    lines.append("")
    for index, candidate in enumerate(candidates, start=1):
        lines.extend(
            [
                f"### {index}. {candidate.topic}",
                f"- Score: {candidate.score}",
                f"- Lane: {candidate.lane}",
                f"- Visual shock: {candidate.visual_shock_score}",
                f"- Curiosity gap: {candidate.curiosity_gap_score}",
                f"- DM share potential: {candidate.dm_share_potential}",
                f"- Watch retention potential: {candidate.watch_retention_potential}",
                f"- Cold audience fit: {candidate.cold_audience_fit}",
                f"- Angle: {candidate.angle}",
                f"- Source: {candidate.source}",
                f"- Reasons: {'; '.join(candidate.reasons) if candidate.reasons else 'none'}",
                f"- Warnings: {'; '.join(candidate.warnings) if candidate.warnings else 'none'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"
