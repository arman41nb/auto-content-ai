"""Load reusable Instagram carousel content patterns."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PatternSelection:
    patterns: list[dict[str, Any]]
    path: Path
    warnings: list[str]

    @property
    def used(self) -> bool:
        return bool(self.patterns)

    @property
    def names(self) -> list[str]:
        return [str(pattern.get("name", "Unnamed Pattern")) for pattern in self.patterns]


def load_relevant_patterns(niche: str, patterns_path: Path, limit: int = 3) -> PatternSelection:
    warnings: list[str] = []
    if not patterns_path.exists():
        return PatternSelection(
            patterns=[],
            path=patterns_path,
            warnings=[f"Pattern library is missing: {patterns_path}"],
        )

    try:
        payload = json.loads(patterns_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return PatternSelection(
            patterns=[],
            path=patterns_path,
            warnings=[f"Could not load pattern library {patterns_path}: {exc}"],
        )

    all_patterns = payload if isinstance(payload, list) else payload.get("patterns", [])
    if not isinstance(all_patterns, list):
        return PatternSelection(
            patterns=[],
            path=patterns_path,
            warnings=[f"Pattern library must be a list or contain a 'patterns' list: {patterns_path}"],
        )

    niche_lower = niche.lower()
    matching = [
        pattern
        for pattern in all_patterns
        if niche_lower in [str(item).lower() for item in pattern.get("works_for", [])]
    ]
    if not matching:
        matching = all_patterns
        warnings.append(f"No patterns matched niche '{niche}'. Using general patterns.")

    return PatternSelection(patterns=matching[:limit], path=patterns_path, warnings=warnings)
