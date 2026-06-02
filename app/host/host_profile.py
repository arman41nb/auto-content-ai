"""Load and validate fictional host profiles."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HostProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    host_id: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=80)
    role: str = Field(..., min_length=1, max_length=240)
    visual_description: str = Field(..., min_length=1, max_length=800)
    personality: str = Field(..., min_length=1, max_length=400)
    voice_style: str = Field(..., min_length=1, max_length=300)
    allowed_topics: list[str] = Field(..., min_length=1, max_length=20)
    image_prompt_base: str = Field(..., min_length=1, max_length=1200)
    negative_prompt: str = Field(..., min_length=1, max_length=800)
    consistency_notes: str = Field(..., min_length=1, max_length=800)

    @field_validator(
        "host_id",
        "name",
        "role",
        "visual_description",
        "personality",
        "voice_style",
        "image_prompt_base",
        "negative_prompt",
        "consistency_notes",
    )
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return " ".join(value.strip().split())


def load_host_profile(host_id: str = "nova", data_root: Path | None = None) -> HostProfile:
    root = data_root or Path(__file__).resolve().parents[2] / "data" / "hosts"
    path = root / f"{host_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return HostProfile.model_validate(payload)
