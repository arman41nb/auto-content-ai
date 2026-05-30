"""Load local research packs for grounded carousel planning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResearchPackResult:
    context: str
    path: Path | None
    warnings: list[str]

    @property
    def used(self) -> bool:
        return bool(self.context.strip()) and self.path is not None


def load_research_pack(topic: str, niche: str, research_root: Path) -> ResearchPackResult:
    """Return matching local markdown research context without crashing on misses."""

    filename = match_research_pack_filename(topic=topic, niche=niche)
    if filename is None:
        return ResearchPackResult(
            context="",
            path=None,
            warnings=[f"No matching research pack for niche '{niche}' and topic '{topic}'."],
        )

    path = research_root / filename
    if not path.exists():
        return ResearchPackResult(
            context="",
            path=path,
            warnings=[f"Matched research pack is missing: {path}"],
        )

    try:
        return ResearchPackResult(context=path.read_text(encoding="utf-8"), path=path, warnings=[])
    except OSError as exc:
        return ResearchPackResult(
            context="",
            path=path,
            warnings=[f"Could not read research pack {path}: {exc}"],
        )


def match_research_pack_filename(topic: str, niche: str) -> str | None:
    topic_lower = topic.lower()
    niche_lower = niche.lower()

    if niche_lower == "history" and ("rome" in topic_lower or "ancient rome" in topic_lower):
        return "history_ancient_rome_daily_life.md"
    if niche_lower == "science" and any(
        keyword in topic_lower for keyword in ("space", "planet", "star", "galaxy")
    ):
        return "science_space_weird_facts.md"
    if niche_lower == "future" or "what if" in topic_lower:
        return "future_what_if_scenarios.md"
    return None

