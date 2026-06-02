"""Load and validate mascot profiles."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MascotProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mascot_id: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=80)
    species_type: str = Field(..., min_length=1, max_length=160)
    visual_description: str = Field(..., min_length=1, max_length=600)
    colors: list[str] = Field(default_factory=list, max_length=12)
    personality: list[str] = Field(default_factory=list, max_length=12)
    educational_role: str = Field(..., min_length=1, max_length=500)
    image_prompt_base: str = Field(..., min_length=1, max_length=900)
    negative_prompt: str = Field(..., min_length=1, max_length=900)
    consistency_rules: list[str] = Field(default_factory=list, max_length=20)
    allowed_emotions: list[str] = Field(default_factory=list, max_length=20)
    allowed_poses: list[str] = Field(default_factory=list, max_length=20)
    forbidden_traits: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("*", mode="before")
    @classmethod
    def normalize_strings(cls, value):
        if isinstance(value, str):
            return " ".join(value.strip().split())
        if isinstance(value, list):
            return [" ".join(str(item).strip().split()) for item in value if str(item).strip()]
        return value


def load_mascot_profile(mascot_id: str = "miko", data_root: Path | None = None) -> MascotProfile:
    root = data_root or Path(__file__).resolve().parents[2] / "data" / "mascots"
    path = root / f"{mascot_id.strip().lower()}.json"
    if not path.exists():
        raise FileNotFoundError(f"Mascot profile not found: {path}")
    return MascotProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))

