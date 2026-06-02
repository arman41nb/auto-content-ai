"""Mascot production asset checks."""

from __future__ import annotations

from pathlib import Path

from app.image.pollinations_client import PollinationsClient
from app.mascot.mascot_asset_manager import ensure_production_mascot_assets, mascot_asset_status
from app.mascot.mascot_profile import MascotProfile


def ensure_mascot_reference_assets(
    project_root: Path,
    profile: MascotProfile,
    stable_seed: int = 4107,
    image_client: PollinationsClient | None = None,
) -> dict[str, object]:
    return ensure_production_mascot_assets(
        project_root=project_root,
        profile=profile,
        image_client=image_client,
        stable_seed=stable_seed,
    )


def mascot_consistency_report(project_root: Path, profile: MascotProfile) -> dict[str, object]:
    return mascot_asset_status(project_root, profile)
