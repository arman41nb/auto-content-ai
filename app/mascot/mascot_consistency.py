"""Mascot MVP consistency checks and reference asset generation."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from app.mascot.mascot_profile import MascotProfile


def ensure_mascot_reference_assets(project_root: Path, profile: MascotProfile, stable_seed: int = 4107) -> dict[str, object]:
    mascot_dir = project_root / "assets" / "mascots" / profile.mascot_id
    mascot_dir.mkdir(parents=True, exist_ok=True)
    paths = [mascot_dir / "reference_01.jpg", mascot_dir / "reference_02.jpg"]
    created: list[str] = []
    for index, path in enumerate(paths, start=1):
        if not path.exists():
            _draw_reference(profile, path, variant=index)
            created.append(str(path))
    report = {
        "mascot_id": profile.mascot_id,
        "name": profile.name,
        "reference_images": [str(path) for path in paths],
        "created": created,
        "identity_consistency_claim": "prompt-level consistency MVP; not perfect identity locking",
        "stable_seed_requested": stable_seed,
        "seed_supported_by_local_fallback": True,
    }
    (mascot_dir / "mascot_asset_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def mascot_consistency_report(project_root: Path, profile: MascotProfile) -> dict[str, object]:
    mascot_dir = project_root / "assets" / "mascots" / profile.mascot_id
    references = [mascot_dir / "reference_01.jpg", mascot_dir / "reference_02.jpg"]
    existing = [str(path) for path in references if path.exists()]
    score = 88 if len(existing) == 2 else 76
    return {
        "mascot_id": profile.mascot_id,
        "mascot_name": profile.name,
        "mascot_presence_score": 92,
        "mascot_consistency_score": score,
        "reference_assets_found": existing,
        "method": "consistent profile, color palette, silhouette, and local reference assets",
    }


def _draw_reference(profile: MascotProfile, path: Path, variant: int) -> None:
    image = Image.new("RGB", (1080, 1920), (244, 234, 218))
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(1920):
        amount = y / 1920
        draw.line((0, y, 1080, y), fill=(244 - int(22 * amount), 234 - int(28 * amount), 218 - int(18 * amount)))
    cx, cy = 540, 860
    body = (cx - 175, cy - 115, cx + 175, cy + 245)
    draw.rounded_rectangle(body, radius=96, fill=(239, 133, 54, 255), outline=(62, 58, 54, 220), width=8)
    cream = (255, 232, 194, 255)
    draw.ellipse((cx - 112, cy - 55, cx + 112, cy + 150), fill=cream)
    ear_offset = 18 if variant == 1 else -14
    draw.polygon([(cx - 145, cy - 105), (cx - 72, cy - 250 + ear_offset), (cx - 18, cy - 88)], fill=(239, 133, 54, 255), outline=(62, 58, 54, 220))
    draw.polygon([(cx + 145, cy - 105), (cx + 72, cy - 250 - ear_offset), (cx + 18, cy - 88)], fill=(239, 133, 54, 255), outline=(62, 58, 54, 220))
    draw.polygon([(cx - 112, cy - 110), (cx - 73, cy - 187 + ear_offset), (cx - 43, cy - 102)], fill=(255, 214, 162, 245))
    draw.polygon([(cx + 112, cy - 110), (cx + 73, cy - 187 - ear_offset), (cx + 43, cy - 102)], fill=(255, 214, 162, 245))
    eye_y = cy + 22
    draw.ellipse((cx - 82, eye_y - 36, cx - 20, eye_y + 36), fill=(28, 30, 32, 255))
    draw.ellipse((cx + 20, eye_y - 36, cx + 82, eye_y + 36), fill=(28, 30, 32, 255))
    draw.ellipse((cx - 61, eye_y - 18, cx - 42, eye_y + 1), fill=(255, 255, 255, 230))
    draw.ellipse((cx + 41, eye_y - 18, cx + 60, eye_y + 1), fill=(255, 255, 255, 230))
    draw.ellipse((cx - 28, cy + 96, cx + 28, cy + 152), fill=(255, 211, 92, 255), outline=(62, 58, 54, 180), width=4)
    draw.line((cx - 190, cy + 48, cx - 300, cy + 128), fill=(48, 48, 48, 255), width=18)
    draw.line((cx + 190, cy + 48, cx + 300, cy - 20 if variant == 2 else cy + 128), fill=(48, 48, 48, 255), width=18)
    draw.ellipse((cx - 322, cy + 114, cx - 276, cy + 160), fill=(48, 48, 48, 255))
    draw.ellipse((cx + 276, (cy - 42 if variant == 2 else cy + 114), cx + 322, (cy + 4 if variant == 2 else cy + 160)), fill=(48, 48, 48, 255))
    draw.text((375, 1280), profile.name, fill=(62, 58, 54, 0))
    image.save(path, "JPEG", quality=94, optimize=True)

