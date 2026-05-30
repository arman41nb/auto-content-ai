"""Slug helpers for output folder names."""

from __future__ import annotations

import re


def slugify(value: str, max_length: int = 80) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        value = "post"
    return value[:max_length].strip("_") or "post"

