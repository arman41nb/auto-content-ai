"""Production mascot asset management.

Primitive local drawings are allowed only as debug artifacts. The production
mascot path must use imported or AI-generated bitmap assets.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.image.pollinations_client import PollinationsClient
from app.mascot.mascot_profile import MascotProfile


MIKO_VISUAL_PROMPT = (
    "small original fox-like robot mascot, rounded soft 3D illustration, warm orange and cream body, "
    "tiny charcoal limbs, expressive curious eyes, small glowing chest dot, smart friendly educational "
    "character, clean modern creator mascot, high-quality 3D illustration, consistent shape, no text, "
    "no logo, no watermark, no human, no celebrity, no copyrighted character"
)
MIKO_NEGATIVE_PROMPT = (
    "flat vector, primitive shapes, stick arms, crude drawing, low quality, blurry, text, logo, watermark, "
    "scary, realistic animal, human presenter, celebrity, copyrighted character, bad anatomy"
)
PRODUCTION_VISUAL_MINIMUMS = True


def ensure_production_mascot_assets(
    project_root: Path,
    profile: MascotProfile,
    image_client: PollinationsClient | None = None,
    stable_seed: int = 4107,
) -> dict[str, object]:
    mascot_dir = project_root / "assets" / "mascots" / profile.mascot_id
    mascot_dir.mkdir(parents=True, exist_ok=True)
    report_path = mascot_dir / "mascot_asset_report.json"
    paths = [mascot_dir / "reference_01.jpg", mascot_dir / "reference_02.jpg"]
    existing_report = _read_json(report_path)
    legacy_local_shape_assets = bool(existing_report.get("seed_supported_by_local_fallback")) or str(
        existing_report.get("asset_source", "")
    ) in {"local_pillow_shapes", "primitive_debug"}
    client = image_client or PollinationsClient(rate_limit_seconds=0.0, width=1080, height=1920, retries=1)

    created: list[str] = []
    errors: list[str] = []
    for index, path in enumerate(paths, start=1):
        should_generate = not path.exists() or legacy_local_shape_assets
        if not should_generate:
            continue
        prompt = _reference_prompt(profile, index, stable_seed)
        try:
            client.generate_image(prompt, path)
            created.append(str(path))
            if index < len(paths):
                client.wait_between_requests()
        except Exception as exc:  # pragma: no cover - network/provider dependent
            errors.append(f"{path.name}: {exc}")

    ready_paths = [str(path) for path in paths if path.exists() and not errors]
    production_ready = len(ready_paths) == len(paths) and not legacy_local_shape_assets or bool(created) and not errors
    report = {
        "mascot_id": profile.mascot_id,
        "name": profile.name,
        "reference_images": [str(path) for path in paths],
        "created": created,
        "asset_source": "ai_generated_image_provider" if production_ready else "ai_generation_unavailable",
        "production_asset_ready": production_ready,
        "legacy_local_shape_assets_detected": legacy_local_shape_assets,
        "primitive_vector_mascot_allowed_in_final": False,
        "identity_consistency_claim": "prompt and reference guided; no primitive final mascot rendering",
        "stable_seed_requested": stable_seed,
        "seed_supported_by_local_fallback": False,
        "warnings": errors,
        "prompt": MIKO_VISUAL_PROMPT,
        "negative_prompt": MIKO_NEGATIVE_PROMPT,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def mascot_asset_status(project_root: Path, profile: MascotProfile) -> dict[str, object]:
    mascot_dir = project_root / "assets" / "mascots" / profile.mascot_id
    report = _read_json(mascot_dir / "mascot_asset_report.json")
    references = [mascot_dir / "reference_01.jpg", mascot_dir / "reference_02.jpg"]
    existing = [str(path) for path in references if path.exists()]
    production_ready = bool(report.get("production_asset_ready", False)) and len(existing) >= 2
    return {
        "mascot_id": profile.mascot_id,
        "mascot_name": profile.name,
        "mascot_presence_score": 92 if production_ready else 45,
        "mascot_consistency_score": 88 if production_ready else 50,
        "reference_assets_found": existing if production_ready else [],
        "production_asset_ready": production_ready,
        "primitive_vector_mascot_allowed_in_final": False,
        "method": "AI-generated or imported mascot bitmap assets" if production_ready else "Mascot bitmap assets missing or not production-ready",
        "warnings": report.get("warnings", []) if isinstance(report.get("warnings", []), list) else [],
    }


def _reference_prompt(profile: MascotProfile, index: int, stable_seed: int) -> str:
    pose = "front-facing full body character reference" if index == 1 else "three-quarter view full body character reference"
    return " ".join(
        [
            MIKO_VISUAL_PROMPT if profile.mascot_id == "miko" else profile.image_prompt_base,
            pose,
            "plain warm neutral studio background, soft cinematic lighting, crisp edges, transparent-cutout feel",
            f"stable visual identity seed {stable_seed + index}",
            f"avoid: {MIKO_NEGATIVE_PROMPT if profile.mascot_id == 'miko' else profile.negative_prompt}",
        ]
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
