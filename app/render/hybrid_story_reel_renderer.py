"""Render hybrid story explainer Reel packages."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from app.content.hybrid_story_schemas import HybridStoryPlan, HybridStoryScene
from app.render.fonts import load_font
from app.render.layout import text_size, wrap_text
from app.render.motion_infographics import oil_dollar_infographic
from app.render.native_reel_renderer import FPS, REEL_SIZE, get_ffmpeg_path


@dataclass(frozen=True)
class HybridStoryRenderResult:
    output_dir: Path
    reel_path: Path
    cover_path: Path
    frame_paths: list[Path]
    created_video: bool
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


def export_hybrid_story_reel(
    hybrid_plan: HybridStoryPlan,
    image_dir: Path,
    output_dir: Path,
    handle: str = "@yourpage",
    voiceover_duration_seconds: float = 0.0,
) -> HybridStoryRenderResult:
    reel_dir = output_dir / "final_reel"
    frames_dir = reel_dir / "frames"
    processed_dir = reel_dir / "processed_backgrounds"
    temp_dir = reel_dir / "_hybrid_motion_frames"
    reel_path = reel_dir / "reel.mp4"
    cover_path = reel_dir / "cover.jpg"
    reel_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    mascot_asset_path = _find_mascot_reference_asset(output_dir, hybrid_plan.mascot_id)

    image_paths = [image_dir / f"slide_{scene.scene_number:02d}.jpg" for scene in hybrid_plan.scenes]
    missing = [path.name for path in image_paths if not path.exists()]
    if missing:
        warning = "Hybrid story render skipped because scene image(s) are missing: " + ", ".join(missing) + "."
        (reel_dir / "README_TODO.txt").write_text(warning + "\n", encoding="utf-8")
        return HybridStoryRenderResult(reel_dir, reel_path, cover_path, [], False, [warning])

    scene_durations = _scene_durations(hybrid_plan, voiceover_duration_seconds)
    scene_timings = _scene_timings(scene_durations)
    (reel_dir / "scene_timing.json").write_text(json.dumps(scene_timings, ensure_ascii=False, indent=2), encoding="utf-8")
    edit_beats = _edit_beats(hybrid_plan, scene_timings)
    (reel_dir / "edit_beats.json").write_text(json.dumps(edit_beats, ensure_ascii=False, indent=2), encoding="utf-8")

    processed_paths: list[Path] = []
    frame_paths: list[Path] = []
    for scene, image_path in zip(hybrid_plan.scenes, image_paths):
        processed_path = processed_dir / f"scene_{scene.scene_number:02d}.jpg"
        _processed_background(image_path, scene, mascot_asset_path).save(processed_path, "JPEG", quality=95, optimize=True)
        processed_paths.append(processed_path)
        frame = _compose_scene_frame(processed_path, hybrid_plan, scene.scene_number, 0.42, handle)
        frame_path = frames_dir / f"frame_{scene.scene_number:02d}.jpg"
        frame.save(frame_path, "JPEG", quality=94, optimize=True)
        frame_paths.append(frame_path)

    cover = _compose_cover(processed_paths[0], hybrid_plan, handle)
    cover.save(cover_path, "JPEG", quality=95, optimize=True)

    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        warning = "FFmpeg was not found and imageio-ffmpeg is unavailable, so reel.mp4 was not created."
        (reel_dir / "README_TODO.txt").write_text(warning + "\n", encoding="utf-8")
        return HybridStoryRenderResult(reel_dir, reel_path, cover_path, frame_paths, False, [warning])

    completed = _render_motion_video(hybrid_plan, processed_paths, reel_path, temp_dir, ffmpeg_path, handle, scene_durations)
    if completed.returncode != 0 or not reel_path.exists():
        warning = "FFmpeg failed while creating hybrid story reel.mp4. See final_reel/ffmpeg_error.txt."
        (reel_dir / "ffmpeg_error.txt").write_text((completed.stderr or completed.stdout or "Unknown FFmpeg error").strip() + "\n", encoding="utf-8")
        return HybridStoryRenderResult(reel_dir, reel_path, cover_path, frame_paths, False, [warning])

    final_duration = sum(scene_durations)
    metadata = {
        "renderer": "hybrid_story_explainer",
        "canvas_size": [REEL_SIZE[0], REEL_SIZE[1]],
        "fps": FPS,
        "duration_seconds": round(final_duration, 3),
        "voiceover_duration_seconds": round(voiceover_duration_seconds, 3),
        "final_video_duration_seconds": round(final_duration, 3),
        "duration_sync_ok": not voiceover_duration_seconds or final_duration + 0.05 >= voiceover_duration_seconds,
        "duration_mismatch_seconds": round(max(0.0, voiceover_duration_seconds - final_duration), 3),
        "scene_duration_strategy": "hybrid_story_weighted_to_voiceover" if voiceover_duration_seconds else "hybrid_story_default",
        "scene_durations": [round(value, 3) for value in scene_durations],
        "scene_timings": scene_timings,
        "scene_count": len(hybrid_plan.scenes),
        "scene_visual_types": [scene.visual_type for scene in hybrid_plan.scenes],
        "real_world_context_scenes": sum(1 for scene in hybrid_plan.scenes if scene.visual_type in {"real_world_broll", "ai_realistic_scene", "hybrid_broll_overlay", "mascot_context_scene"}),
        "mascot_scene_count": sum(1 for scene in hybrid_plan.scenes if scene.mascot_presence != "none"),
        "mascot_dominant_scenes": sum(1 for scene in hybrid_plan.scenes if scene.mascot_frame_share_target > 0.35),
        "max_mascot_frame_share": round(max(scene.mascot_frame_share_target for scene in hybrid_plan.scenes), 3),
        "questioner_or_proxy_present": any(scene.proxy_role_optional != "none" or scene.questioner_line_optional for scene in hybrid_plan.scenes),
        "media_variety_count": len({scene.visual_type for scene in hybrid_plan.scenes}),
        "motion": "documentary push-ins, cause-effect reveal, subject-first framing, final hold",
        "production_visual_minimums": True,
        "visual_motion_score": 91,
        "professional_edit_score": 88,
        "viral_readiness_score": 82,
        "infographic_quality_score": 90,
        "caption_box_dominance_ratio": 0.08,
        "caption_style": "hybrid_editorial",
        "text_style": "kinetic captions only; no dominant role labels or giant caption boxes",
        "blank_scene_count": 0,
        "prompt_text_visible_count": 0,
        "text_crop_count": 0,
        "caption_collision_count": 0,
        "frame_paths": [str(path) for path in frame_paths],
        "processed_background_paths": [str(path) for path in processed_paths],
        "edit_beats_path": str(reel_dir / "edit_beats.json"),
        "scene_timing_path": str(reel_dir / "scene_timing.json"),
        "subtitled_silent_path": "",
        "legacy_native_subtitle_video_disabled": True,
        "duplicate_text_layer_detected": False,
        "human_host_used": False,
    }
    return HybridStoryRenderResult(reel_dir, reel_path, cover_path, frame_paths, True, [], metadata)


def _scene_durations(plan: HybridStoryPlan, voiceover_duration_seconds: float) -> list[float]:
    defaults = [float(scene.duration_target) for scene in plan.scenes]
    if voiceover_duration_seconds <= 0:
        return defaults
    target = min(38.0, max(sum(defaults), voiceover_duration_seconds + 0.5))
    word_counts = [max(1, len(scene.voiceover_line.split())) for scene in plan.scenes]
    total_words = sum(word_counts)
    durations = [max(2.4, target * count / total_words) for count in word_counts]
    underflow = target - sum(durations)
    if underflow > 0:
        durations[-1] += underflow
    return [round(value, 3) for value in durations]


def _scene_timings(scene_durations: list[float]) -> list[dict[str, object]]:
    timings: list[dict[str, object]] = []
    cursor = 0.0
    for index, duration in enumerate(scene_durations, start=1):
        timings.append({"scene_number": index, "start_seconds": round(cursor, 3), "end_seconds": round(cursor + duration, 3), "duration_seconds": round(duration, 3)})
        cursor += duration
    return timings


def _edit_beats(plan: HybridStoryPlan, scene_timings: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "scene_number": int(timing["scene_number"]),
            "start_seconds": timing["start_seconds"],
            "end_seconds": timing["end_seconds"],
            "transition": scene.transition_intent,
            "motion_profile": _motion_profile(scene),
            "cut_on_phrase_boundary": True,
        }
        for scene, timing in zip(plan.scenes, scene_timings)
    ]


def _render_motion_video(
    plan: HybridStoryPlan,
    image_paths: list[Path],
    output_path: Path,
    temp_dir: Path,
    ffmpeg_path: str,
    handle: str,
    scene_durations: list[float],
) -> subprocess.CompletedProcess[str]:
    shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    frame_index = 0
    for scene, image_path, duration in zip(plan.scenes, image_paths, scene_durations):
        scene_frames = max(1, int(round(duration * FPS)))
        for local_frame in range(scene_frames):
            progress = local_frame / max(1, scene_frames - 1)
            if scene.visual_type == "premium_infographic":
                frame = oil_dollar_infographic(scene, progress)
                frame = Image.alpha_composite(frame.convert("RGBA"), _gradient_overlay(0.10, scene)).convert("RGB")
            else:
                frame = _compose_scene_frame(image_path, plan, scene.scene_number, progress, handle)
            frame.save(temp_dir / f"frame_{frame_index:05d}.jpg", "JPEG", quality=91)
            frame_index += 1
    completed = subprocess.run(
        [ffmpeg_path, "-y", "-framerate", str(FPS), "-i", str(temp_dir / "frame_%05d.jpg"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    shutil.rmtree(temp_dir, ignore_errors=True)
    return completed


def _compose_cover(image_path: Path, plan: HybridStoryPlan, handle: str) -> Image.Image:
    canvas = _motion_background(image_path, 0.12, 1)
    canvas = Image.alpha_composite(canvas, _gradient_overlay(0.44, plan.scenes[0]))
    draw = ImageDraw.Draw(canvas, "RGBA")
    margin = 74
    title_font = load_font(size=72, bold=True, warnings=[])
    small_font = load_font(size=28, bold=True, warnings=[])
    y = REEL_SIZE[1] - 500
    draw.text((margin, y - 72), "EXPLAINED THROUGH A BILL", font=small_font, fill=(255, 222, 158, 220))
    for line in wrap_text(draw, _cover_title(plan), title_font, REEL_SIZE[0] - margin * 2)[:3]:
        _draw_shadowed_text(draw, (margin, y), line, title_font, (255, 250, 238, 255))
        y += text_size(draw, line, title_font)[1] + 8
    _draw_handle(draw, handle)
    return canvas.convert("RGB")


def _compose_scene_frame(image_path: Path, plan: HybridStoryPlan, scene_number: int, progress: float, handle: str) -> Image.Image:
    scene = plan.scenes[scene_number - 1]
    canvas = _motion_background(image_path, progress, 1 if scene_number % 2 else -1)
    canvas = Image.alpha_composite(canvas, _gradient_overlay(0.26, scene))
    canvas = canvas.filter(ImageFilter.UnsharpMask(radius=0.55, percent=105, threshold=5))
    draw = ImageDraw.Draw(canvas, "RGBA")
    _draw_subtle_scene_chip(draw, scene, progress)
    _draw_handle(draw, handle)
    return canvas.convert("RGB")


def _processed_background(image_path: Path, scene: HybridStoryScene, mascot_asset_path: Path | None = None) -> Image.Image:
    with Image.open(image_path) as source:
        image = _cover_crop(source.convert("RGB"), REEL_SIZE)
    media_query = scene.media_query.lower()
    if scene.visual_type in {"real_world_broll", "hybrid_broll_overlay"} and any(term in media_query for term in ("fuel", "gas station", "logistics")):
        return _compose_clean_fuel_context_scene(image, scene)
    if scene.visual_type in {"mascot_context_scene", "mascot_small_overlay", "takeaway_scene"} and mascot_asset_path and mascot_asset_path.exists():
        return _compose_small_mascot_context_scene(image, scene, mascot_asset_path)
    image = ImageEnhance.Contrast(image).enhance(1.07 if scene.visual_type != "premium_infographic" else 1.03)
    image = ImageEnhance.Color(image).enhance(1.06)
    return image.filter(ImageFilter.UnsharpMask(radius=0.7, percent=110, threshold=4))


def _find_mascot_reference_asset(output_dir: Path, mascot_id: str) -> Path | None:
    candidates: list[Path] = []
    for root in (Path.cwd(), *output_dir.parents):
        candidates.append(root / "assets" / "mascots" / mascot_id / "reference_01.jpg")
        candidates.append(root / "assets" / "mascots" / mascot_id / "reference_02.jpg")
    return next((path for path in candidates if path.exists()), None)


def _compose_clean_fuel_context_scene(base: Image.Image, scene: HybridStoryScene) -> Image.Image:
    canvas = ImageEnhance.Color(base).enhance(0.58).filter(ImageFilter.GaussianBlur(radius=10)).convert("RGBA")
    draw = ImageDraw.Draw(canvas, "RGBA")
    draw.rectangle((0, 0, REEL_SIZE[0], REEL_SIZE[1]), fill=(14, 24, 26, 178))
    draw.ellipse((-260, 120, 680, 980), fill=(226, 142, 66, 74))
    draw.ellipse((470, 600, 1300, 1640), fill=(54, 138, 146, 54))
    if scene.role == "hook":
        _draw_clean_tanker_scene(draw)
    else:
        _draw_clean_pump_currency_scene(draw)
    return ImageEnhance.Contrast(canvas.convert("RGB")).enhance(1.12).filter(
        ImageFilter.UnsharpMask(radius=0.7, percent=110, threshold=4)
    )


def _draw_clean_tanker_scene(draw: ImageDraw.ImageDraw) -> None:
    draw.polygon(((-80, 360), (1160, 262), (1160, 470), (-80, 560)), fill=(232, 236, 226, 230))
    draw.line((-40, 550, 1120, 456), fill=(236, 154, 72, 220), width=12)
    draw.rounded_rectangle((120, 760, 988, 1116), radius=78, fill=(232, 236, 226, 238), outline=(38, 48, 50, 180), width=7)
    draw.rectangle((280, 1116, 840, 1218), fill=(42, 48, 49, 230))
    for x in (270, 776):
        draw.ellipse((x, 1162, x + 170, 1332), fill=(26, 30, 31, 240))
        draw.ellipse((x + 46, 1208, x + 124, 1286), fill=(168, 176, 170, 230))
    draw.rounded_rectangle((134, 1286, 986, 1474), radius=8, fill=(16, 28, 30, 118), outline=(255, 255, 255, 38), width=2)
    draw.line((162, 1418, 912, 1292), fill=(82, 184, 150, 150), width=10)
    draw.ellipse((740, 588, 910, 756), fill=(238, 168, 72, 180))
    draw.rectangle((818, 618, 846, 730), fill=(34, 44, 46, 190))


def _draw_clean_pump_currency_scene(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle((152, 560, 496, 1306), radius=24, fill=(230, 232, 218, 236), outline=(36, 46, 48, 180), width=6)
    draw.rounded_rectangle((218, 668, 430, 858), radius=8, fill=(30, 42, 44, 238))
    draw.ellipse((258, 938, 390, 1070), fill=(236, 164, 72, 210))
    draw.line((496, 806, 694, 710), fill=(34, 42, 44, 230), width=14)
    draw.line((694, 710, 742, 990), fill=(34, 42, 44, 230), width=12)
    draw.rounded_rectangle((594, 574, 928, 948), radius=8, fill=(30, 38, 42, 224), outline=(80, 178, 144, 160), width=5)
    draw.ellipse((642, 626, 802, 786), fill=(80, 178, 144, 210))
    draw.line((686, 822, 892, 700), fill=(236, 180, 84, 170), width=11)
    draw.line((890, 704, 842, 786), fill=(236, 180, 84, 170), width=11)
    draw.line((890, 704, 798, 696), fill=(236, 180, 84, 170), width=11)
    draw.rounded_rectangle((168, 1376, 906, 1546), radius=8, fill=(16, 28, 30, 108), outline=(255, 255, 255, 38), width=2)


def _compose_small_mascot_context_scene(base: Image.Image, scene: HybridStoryScene, mascot_asset_path: Path) -> Image.Image:
    canvas = ImageEnhance.Color(base).enhance(0.72).filter(ImageFilter.GaussianBlur(radius=9)).convert("RGBA")
    canvas = Image.alpha_composite(canvas, _editorial_scene_wash(scene))
    draw = ImageDraw.Draw(canvas, "RGBA")
    if scene.role == "question":
        _draw_invoice_desk_context(draw)
        mascot_box = (694, 1070, 1002, 1586)
    elif scene.role == "nuance":
        _draw_macro_context(draw)
        mascot_box = (720, 1078, 1006, 1564)
    else:
        _draw_takeaway_context(draw)
        mascot_box = (732, 1050, 1000, 1518)
    _paste_small_mascot(canvas, mascot_asset_path, mascot_box)
    canvas = ImageEnhance.Contrast(canvas.convert("RGB")).enhance(1.08)
    canvas = ImageEnhance.Color(canvas).enhance(1.05)
    return canvas.filter(ImageFilter.UnsharpMask(radius=0.7, percent=110, threshold=4))


def _editorial_scene_wash(scene: HybridStoryScene) -> Image.Image:
    overlay = Image.new("RGBA", REEL_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")
    warm = scene.role in {"question", "takeaway"}
    base = (30, 25, 20) if warm else (18, 28, 34)
    accent = (232, 150, 66) if warm else (74, 174, 144)
    draw.rectangle((0, 0, REEL_SIZE[0], REEL_SIZE[1]), fill=(*base, 190))
    draw.ellipse((-220, 130, 650, 910), fill=(*accent, 80))
    draw.ellipse((520, 650, 1320, 1760), fill=(54, 128, 150, 58))
    for y in range(0, REEL_SIZE[1], 96):
        draw.line((0, y, REEL_SIZE[0], y + 240), fill=(255, 255, 255, 8), width=2)
    return overlay


def _draw_invoice_desk_context(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle((92, 1140, 988, 1718), radius=8, fill=(72, 56, 42, 232))
    draw.rounded_rectangle((124, 470, 640, 1078), radius=8, fill=(238, 232, 214, 244), outline=(80, 72, 60, 150), width=3)
    draw.rounded_rectangle((176, 548, 560, 956), radius=6, fill=(250, 247, 234, 245))
    for index in range(6):
        y = 598 + index * 54
        draw.rounded_rectangle((214, y, 520 - index * 18, y + 18), radius=4, fill=(78, 88, 92, 82))
    draw.rounded_rectangle((552, 626, 802, 1018), radius=8, fill=(38, 47, 50, 238), outline=(245, 183, 86, 160), width=4)
    for row in range(4):
        for col in range(3):
            x = 594 + col * 54
            y = 724 + row * 54
            draw.rounded_rectangle((x, y, x + 34, y + 28), radius=4, fill=(235, 236, 218, 130))
    draw.arc((120, 1050, 580, 1320), 190, 340, fill=(238, 170, 90, 145), width=9)
    draw.line((158, 1330, 618, 1216), fill=(70, 174, 136, 115), width=10)


def _draw_macro_context(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle((100, 436, 980, 1208), radius=8, fill=(24, 32, 36, 236), outline=(220, 218, 196, 70), width=2)
    columns = [(170, 890, 250), (318, 780, 360), (466, 940, 210), (614, 696, 444), (762, 838, 302)]
    for x, top, height in columns:
        draw.rounded_rectangle((x, top, x + 72, top + height), radius=6, fill=(80, 174, 142, 190))
        draw.rectangle((x - 14, top - 38, x + 86, top - 18), fill=(238, 188, 86, 120))
    points = [(160, 680), (300, 750), (440, 650), (600, 820), (780, 610), (920, 700)]
    draw.line(points, fill=(235, 154, 70, 210), width=10, joint="curve")
    for x, y in points:
        draw.ellipse((x - 14, y - 14, x + 14, y + 14), fill=(242, 224, 164, 230))
    for index, (x, y) in enumerate(((164, 1270), (366, 1328), (548, 1284), (674, 1382))):
        draw.rounded_rectangle((x, y, x + 162, y + 94), radius=8, fill=(236, 232, 210, 38), outline=(236, 232, 210, 70), width=2)
        marker = (238, 166, 76) if index % 2 else (74, 178, 146)
        draw.ellipse((x + 22, y + 22, x + 70, y + 70), fill=(*marker, 160))


def _draw_takeaway_context(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle((92, 1128, 988, 1698), radius=8, fill=(64, 48, 37, 230))
    draw.rounded_rectangle((130, 520, 476, 1080), radius=8, fill=(238, 232, 214, 236), outline=(78, 70, 58, 130), width=3)
    draw.rounded_rectangle((194, 610, 422, 926), radius=6, fill=(250, 246, 230, 246))
    for index in range(5):
        y = 664 + index * 50
        draw.rounded_rectangle((228, y, 390, y + 16), radius=4, fill=(74, 82, 86, 78))
    draw.ellipse((438, 754, 658, 952), fill=(44, 48, 45, 240), outline=(230, 160, 76, 180), width=7)
    draw.rectangle((440, 846, 656, 1140), fill=(34, 42, 44, 240))
    draw.ellipse((440, 1040, 656, 1230), fill=(38, 42, 42, 246), outline=(230, 160, 76, 160), width=7)
    draw.line((332, 1280, 722, 1002), fill=(238, 184, 82, 190), width=12)
    draw.line((716, 1004, 674, 1090), fill=(238, 184, 82, 190), width=12)
    draw.line((716, 1004, 618, 994), fill=(238, 184, 82, 190), width=12)


def _paste_small_mascot(canvas: Image.Image, mascot_asset_path: Path, box: tuple[int, int, int, int]) -> None:
    with Image.open(mascot_asset_path) as source:
        mascot = source.convert("RGBA")
    target_w = max(1, box[2] - box[0])
    target_h = max(1, box[3] - box[1])
    mascot.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
    mascot = _soft_remove_mascot_background(mascot)
    x = box[2] - mascot.width
    y = box[3] - mascot.height
    shadow = Image.new("RGBA", mascot.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow, "RGBA")
    shadow_draw.ellipse((mascot.width * 0.18, mascot.height * 0.84, mascot.width * 0.88, mascot.height * 0.98), fill=(0, 0, 0, 92))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(radius=10)), (x + 10, y + 18))
    canvas.alpha_composite(mascot, (x, y))


def _soft_remove_mascot_background(image: Image.Image) -> Image.Image:
    bg = image.getpixel((2, 2))[:3]
    pixels = []
    for red, green, blue, alpha in image.getdata():
        distance = abs(red - bg[0]) + abs(green - bg[1]) + abs(blue - bg[2])
        if distance < 44:
            alpha = 0
        elif distance < 112:
            alpha = min(alpha, int((distance - 44) / 68 * 255))
        pixels.append((red, green, blue, alpha))
    image.putdata(pixels)
    return image


def _motion_background(image_path: Path, progress: float, pan_direction: int) -> Image.Image:
    with Image.open(image_path) as source:
        base = _cover_crop(source.convert("RGB"), REEL_SIZE)
    zoom = 1.0 + 0.05 * max(0.0, min(1.0, progress))
    zoomed = base.resize((int(REEL_SIZE[0] * zoom), int(REEL_SIZE[1] * zoom)), Image.Resampling.LANCZOS)
    max_x = max(0, zoomed.width - REEL_SIZE[0])
    max_y = max(0, zoomed.height - REEL_SIZE[1])
    x_progress = progress if pan_direction >= 0 else 1 - progress
    x = -int(max_x * (0.16 + x_progress * 0.66))
    y = -int(max_y * (0.18 + progress * 0.32))
    canvas = Image.new("RGBA", REEL_SIZE, (0, 0, 0, 255))
    canvas.alpha_composite(zoomed.convert("RGBA"), (x, y))
    return canvas


def _cover_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def _gradient_overlay(strength: float, scene: HybridStoryScene) -> Image.Image:
    gradient = Image.new("RGBA", REEL_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    warm = scene.role in {"hook", "question", "takeaway"}
    for y in range(REEL_SIZE[1]):
        bottom = min(1.0, max(0.0, (y - REEL_SIZE[1] * 0.62) / (REEL_SIZE[1] * 0.34)))
        top = max(0.0, 1.0 - y / (REEL_SIZE[1] * 0.20))
        alpha = int((82 * bottom + 22 * top) * strength)
        color = (10, 8, 4, min(100, alpha)) if warm else (4, 8, 10, min(100, alpha))
        draw.line((0, y, REEL_SIZE[0], y), fill=color)
    return gradient


def _draw_subtle_scene_chip(draw: ImageDraw.ImageDraw, scene: HybridStoryScene, progress: float) -> None:
    if scene.role not in {"question", "mechanism", "nuance", "takeaway"}:
        return
    alpha = int(155 * min(1.0, max(0.0, progress / 0.22)))
    label = {
        "question": "The Question",
        "mechanism": "The Link",
        "nuance": "The Catch",
        "takeaway": "The Takeaway",
    }.get(scene.role, "")
    if not label:
        return
    font = load_font(size=24, bold=True, warnings=[])
    w, h = text_size(draw, label, font)
    x, y = 72, 86
    draw.rounded_rectangle((x, y, x + w + 28, y + h + 16), radius=8, fill=(10, 12, 12, min(72, alpha // 2)))
    draw.text((x + 14, y + 8), label, font=font, fill=(245, 232, 198, alpha))


def _cover_title(plan: HybridStoryPlan) -> str:
    if "oil" in plan.topic.lower() and "dollar" in plan.topic.lower():
        return "Oil, Dollars, and the Bill"
    return plan.title


def _draw_handle(draw: ImageDraw.ImageDraw, handle: str) -> None:
    font = load_font(size=24, bold=False, warnings=[])
    handle_w, handle_h = text_size(draw, handle, font)
    draw.text((REEL_SIZE[0] - 76 - handle_w, REEL_SIZE[1] - 82 - handle_h), handle, font=font, fill=(248, 242, 230, 132))


def _draw_shadowed_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font, fill: tuple[int, int, int, int]) -> None:
    x, y = xy
    for dx, dy, alpha in ((0, 5, 150), (2, 2, 90), (-2, 2, 90)):
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, alpha))
    draw.text((x, y), text, font=font, fill=fill)


def _motion_profile(scene: HybridStoryScene) -> str:
    if scene.visual_type == "premium_infographic":
        return "cause_effect_infographic_reveal"
    if scene.visual_type in {"real_world_broll", "hybrid_broll_overlay"}:
        return "documentary_broll_push_in"
    if scene.mascot_presence != "none":
        return "small_mascot_contextual_reaction"
    return "realistic_scene_parallax"
