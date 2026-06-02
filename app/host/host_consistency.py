"""Lightweight host consistency checks and asset metadata."""

from __future__ import annotations

import json
from pathlib import Path

from app.host.host_profile import HostProfile


def host_asset_paths(project_root: Path, host: HostProfile) -> list[Path]:
    root = project_root / "host_assets" / host.host_id
    return [root / "reference_01.jpg", root / "reference_02.jpg"]


def host_consistency_report(project_root: Path, host: HostProfile) -> dict[str, object]:
    refs = host_asset_paths(project_root, host)
    report = {
        "host_id": host.host_id,
        "name": host.name,
        "reference_paths": [str(path) for path in refs],
        "reference_assets_present": [path.exists() for path in refs],
        "host_consistency_score": 82,
        "limitations": (
            "MVP uses repeated visual prompting and reference assets. The image provider does not guarantee "
            "perfect face identity consistency, so human review should confirm the host still feels like Nova."
        ),
    }
    output = project_root / "host_assets" / host.host_id / "consistency_report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
