"""Lightweight explainer research pack loader.

This module intentionally avoids scraping arbitrary pages. It only reads local
research packs so factual grounding is explicit and reviewable.
"""

from __future__ import annotations

from pathlib import Path


def load_explainer_research_pack(topic: str, niche: str, research_root: Path) -> dict[str, object]:
    lower = f"{topic} {niche}".lower()
    if "oil" in lower and "dollar" in lower:
        path = research_root / "economy_oil_dollar_relationship.md"
    else:
        path = research_root / f"{niche}_explainer_basics.md"
    if not path.exists():
        return {"used": False, "path": "", "context": "", "warnings": ["No local explainer research pack found."]}
    return {"used": True, "path": str(path), "context": path.read_text(encoding="utf-8"), "warnings": []}
