"""Render native 1080x1920 cinematic Reel stories."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from app.content.reel_schemas import ReelPlan, ReelScene
from app.render.fonts import load_font
from app.render.layout import text_size, wrap_text
from app.render.subtitles import build_subtitle_cues, write_subtitle_files


REEL_SIZE = (1080, 1920)
FPS = 30


@dataclass(frozen=True)
class NativeReelRenderResult:
    output_dir: Path
    reel_path: Path
    cover_path: Path
    frame_paths: list[Path]
    created_video: bool
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


def get_ffmpeg_path() -> str | None:
    """Return system FFmpeg or the imageio-ffmpeg bundled executable."""

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        return ffmpeg
    try:
        import imageio_ffmpeg  # type: ignore[import-not-found]

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        return bundled if Path(bundled).exists() else None
    except Exception:
        return None


def export_native_reel_story(
    reel_plan: ReelPlan,
    image_dir: Path,
    output_dir: Path,
    handle: str = "@yourpage",
    voiceover_duration_seconds: float = 0.0,
    create_subtitles: bool = False,
) -> NativeReelRenderResult:
    """Render final_reel/reel.mp4, cover.jpg, and scene frames from native scene images."""

    reel_dir = output_dir / "final_reel"
    frames_dir = reel_dir / "frames"
    processed_dir = reel_dir / "processed_backgrounds"
    temp_dir = reel_dir / "_native_motion_frames"
    reel_path = reel_dir / "reel.mp4"
    subtitled_silent_path = reel_dir / "reel_subtitled_silent.mp4"
    cover_path = reel_dir / "cover.jpg"
    warnings: list[str] = []
    frame_paths: list[Path] = []
    reel_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)

    scene_image_paths = [_scene_image_path(image_dir, scene.scene_number) for scene in reel_plan.scenes]
    missing = [path.name for path in scene_image_paths if not path.exists()]
    if missing:
        warning = "Native Reel render skipped because scene image(s) are missing: " + ", ".join(missing) + "."
        (reel_dir / "README_TODO.txt").write_text(warning + "\n", encoding="utf-8")
        return NativeReelRenderResult(reel_dir, reel_path, cover_path, frame_paths, False, [warning])

    scene_durations = _scene_durations_for_voiceover(reel_plan, voiceover_duration_seconds)
    scene_timings = _scene_timings(scene_durations)
    processed_paths: list[Path] = []
    for scene, image_path in zip(reel_plan.scenes, scene_image_paths):
        processed_path = processed_dir / f"scene_{scene.scene_number:02d}.jpg"
        _processed_background(image_path).save(processed_path, "JPEG", quality=95, optimize=True)
        processed_paths.append(processed_path)

    cues = build_subtitle_cues(reel_plan, scene_timings)
    subtitle_metadata: dict[str, object] = {}
    if create_subtitles:
        subtitle_metadata = write_subtitle_files(output_dir / "voiceover", cues)

    cover = _compose_cover(processed_paths[0], reel_plan.cover_text, handle)
    cover.save(cover_path, "JPEG", quality=95, optimize=True)

    for scene, image_path in zip(reel_plan.scenes, processed_paths):
        frame = _compose_scene_frame(
            image_path=image_path,
            scene=scene,
            progress=0.34,
            pan_direction=1 if scene.scene_number % 2 else -1,
            handle=handle,
        )
        frame_path = frames_dir / f"frame_{scene.scene_number:02d}.jpg"
        frame.save(frame_path, "JPEG", quality=94, optimize=True)
        frame_paths.append(frame_path)

    ffmpeg_path = get_ffmpeg_path()
    if not ffmpeg_path:
        warning = "FFmpeg was not found and imageio-ffmpeg is unavailable, so reel.mp4 was not created."
        (reel_dir / "README_TODO.txt").write_text(warning + "\n", encoding="utf-8")
        return NativeReelRenderResult(reel_dir, reel_path, cover_path, frame_paths, False, [warning])

    completed = _render_motion_video(
        reel_plan=reel_plan,
        image_paths=processed_paths,
        output_path=reel_path,
        temp_dir=temp_dir,
        ffmpeg_path=ffmpeg_path,
        handle=handle,
        scene_durations=scene_durations,
        cues=[],
    )
    if completed.returncode != 0 or not reel_path.exists():
        warning = "FFmpeg failed while creating native reel.mp4. See final_reel/ffmpeg_error.txt."
        (reel_dir / "ffmpeg_error.txt").write_text(
            (completed.stderr or completed.stdout or "Unknown FFmpeg error").strip() + "\n",
            encoding="utf-8",
        )
        return NativeReelRenderResult(reel_dir, reel_path, cover_path, frame_paths, False, [warning])

    if create_subtitles:
        subtitle_completed = _render_motion_video(
            reel_plan=reel_plan,
            image_paths=processed_paths,
            output_path=subtitled_silent_path,
            temp_dir=temp_dir,
            ffmpeg_path=ffmpeg_path,
            handle=handle,
            scene_durations=scene_durations,
            cues=cues,
        )
        if subtitle_completed.returncode != 0 or not subtitled_silent_path.exists():
            warnings.append("FFmpeg failed while creating the silent burned-subtitle Reel.")
            (reel_dir / "ffmpeg_subtitled_error.txt").write_text(
                (subtitle_completed.stderr or subtitle_completed.stdout or "Unknown FFmpeg subtitle error").strip()
                + "\n",
                encoding="utf-8",
            )

    default_duration = sum(scene.duration_seconds for scene in reel_plan.scenes)
    final_duration = sum(scene_durations)
    duration_mismatch = max(0.0, voiceover_duration_seconds - final_duration)
    metadata = {
        "renderer": "native_reel_story",
        "canvas_size": [REEL_SIZE[0], REEL_SIZE[1]],
        "fps": FPS,
        "duration_seconds": round(final_duration, 3),
        "default_scene_total_seconds": round(default_duration, 3),
        "voiceover_duration_seconds": round(voiceover_duration_seconds, 3),
        "final_video_duration_seconds": round(final_duration, 3),
        "duration_sync_ok": not voiceover_duration_seconds or final_duration + 0.05 >= voiceover_duration_seconds,
        "duration_mismatch_seconds": round(duration_mismatch, 3),
        "scene_duration_strategy": "voiceover_word_count_weighted_min_1.4s"
        if voiceover_duration_seconds
        else "plan_default_scene_durations",
        "scene_durations": [round(value, 3) for value in scene_durations],
        "scene_timings": scene_timings,
        "scene_count": len(reel_plan.scenes),
        "motion": "per-scene slow zoom 100-109 percent with subtle 2-4 percent pan and micro motion",
        "source": "native_fullscreen_scene_images",
        "text_style": "minimal shadowed kinetic captions, no black boxes",
        "frame_paths": [str(path) for path in frame_paths],
        "processed_background_paths": [str(path) for path in processed_paths],
        "subtitled_silent_path": str(subtitled_silent_path) if subtitled_silent_path.exists() else "",
        **subtitle_metadata,
    }
    return NativeReelRenderResult(reel_dir, reel_path, cover_path, frame_paths, True, warnings, metadata)


def _scene_image_path(image_dir: Path, scene_number: int) -> Path:
    return image_dir / f"slide_{scene_number:02d}.jpg"


def _compose_cover(image_path: Path, cover_text: str, handle: str) -> Image.Image:
    canvas = _motion_background(image_path, progress=0.22, pan_direction=1)
    canvas = Image.alpha_composite(canvas, _gradient_overlay(strength=1.1))
    draw = ImageDraw.Draw(canvas, "RGBA")
    margin = 78
    max_width = REEL_SIZE[0] - margin * 2
    label_font = load_font(size=24, bold=True, warnings=[])
    title_font = load_font(size=78, bold=True, warnings=[])
    y = REEL_SIZE[1] - 455
    draw.text((margin, y - 74), "UNREAL SCIENCE", font=label_font, fill=(232, 229, 218, 224))
    draw.line((margin, y - 32, margin + 88, y - 32), fill=(222, 178, 102, 235), width=3)
    for line in wrap_text(draw, cover_text.upper(), title_font, max_width)[:3]:
        _draw_shadowed_text(draw, (margin, y), line, title_font, (250, 249, 244, 255), shadow_alpha=180)
        y += text_size(draw, line, title_font)[1] + 8
    _draw_handle(draw, handle)
    return canvas.convert("RGB")


def _compose_scene_frame(
    image_path: Path,
    scene: ReelScene,
    progress: float,
    pan_direction: int,
    handle: str,
    subtitle_text: str = "",
    subtitle_progress: float = 1.0,
) -> Image.Image:
    canvas = _motion_background(image_path, progress=progress, pan_direction=pan_direction)
    canvas = Image.alpha_composite(canvas, _gradient_overlay(strength=0.72))
    canvas = canvas.filter(ImageFilter.UnsharpMask(radius=0.65, percent=105, threshold=5))
    draw = ImageDraw.Draw(canvas, "RGBA")
    _draw_caption(draw, scene, progress)
    if subtitle_text:
        _draw_voiceover_subtitle(draw, subtitle_text, subtitle_progress)
    _draw_micro_scene_number(draw, scene.scene_number)
    _draw_handle(draw, handle)
    return canvas.convert("RGB")


def _motion_background(image_path: Path, progress: float, pan_direction: int) -> Image.Image:
    with Image.open(image_path) as source:
        base = _cover_crop(source.convert("RGB"), REEL_SIZE)
    zoom = 1.0 + 0.09 * max(0.0, min(1.0, progress))
    zoomed = base.resize((int(REEL_SIZE[0] * zoom), int(REEL_SIZE[1] * zoom)), Image.Resampling.LANCZOS)
    max_x_shift = max(0, zoomed.width - REEL_SIZE[0])
    max_y_shift = max(0, zoomed.height - REEL_SIZE[1])
    x_progress = progress if pan_direction >= 0 else 1 - progress
    x = -int(max_x_shift * (0.18 + x_progress * 0.64))
    y = -int(max_y_shift * (0.30 + progress * 0.30))
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


def _gradient_overlay(strength: float) -> Image.Image:
    gradient = Image.new("RGBA", REEL_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    for y_pos in range(REEL_SIZE[1]):
        bottom = min(1.0, max(0.0, (y_pos - REEL_SIZE[1] * 0.56) / (REEL_SIZE[1] * 0.44)))
        top = max(0.0, 1.0 - y_pos / (REEL_SIZE[1] * 0.28))
        alpha = int((72 * bottom + 26 * top) * strength)
        draw.line([(0, y_pos), (REEL_SIZE[0], y_pos)], fill=(0, 0, 0, min(104, alpha)))
    return gradient


def _draw_caption(draw: ImageDraw.ImageDraw, scene: ReelScene, progress: float) -> None:
    margin = 78
    max_width = REEL_SIZE[0] - margin * 2
    font = load_font(size=54, bold=True, warnings=[])
    lines = wrap_text(draw, scene.on_screen_text.upper(), font, max_width)[:2]
    if len(lines) == 2:
        font = load_font(size=48, bold=True, warnings=[])
        lines = wrap_text(draw, scene.on_screen_text.upper(), font, max_width)[:2]
    y = 1080
    intro = min(1.0, max(0.0, progress / 0.18))
    y_offset = int((1.0 - intro) * 22)
    alpha = int(255 * intro)
    draw.line((margin, y - 34 + y_offset, margin + 76, y - 34 + y_offset), fill=(224, 178, 102, int(220 * intro)), width=3)
    for line in lines:
        _draw_shadowed_text(draw, (margin, y + y_offset), line, font, (250, 249, 244, alpha), shadow_alpha=int(178 * intro))
        y += text_size(draw, line, font)[1] + 8


def _draw_shadowed_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font,
    fill: tuple[int, int, int, int],
    shadow_alpha: int = 160,
) -> None:
    x, y = xy
    for dx, dy, alpha in ((0, 5, shadow_alpha), (2, 2, shadow_alpha // 2), (-2, 2, shadow_alpha // 2)):
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, alpha))
    draw.text((x, y), text, font=font, fill=fill)


def _draw_micro_scene_number(draw: ImageDraw.ImageDraw, scene_number: int) -> None:
    font = load_font(size=22, bold=False, warnings=[])
    draw.text((78, 72), f"{scene_number:02d}/05", font=font, fill=(238, 236, 230, 118))


def _draw_handle(draw: ImageDraw.ImageDraw, handle: str) -> None:
    font = load_font(size=24, bold=False, warnings=[])
    handle_w, handle_h = text_size(draw, handle, font)
    draw.text(
        (REEL_SIZE[0] - 78 - handle_w, REEL_SIZE[1] - 82 - handle_h),
        handle,
        font=font,
        fill=(238, 236, 230, 132),
    )


def _processed_background(image_path: Path) -> Image.Image:
    with Image.open(image_path) as source:
        image = _cover_crop(source.convert("RGB"), REEL_SIZE)
    image = ImageEnhance.Contrast(image).enhance(1.07)
    image = ImageEnhance.Color(image).enhance(1.05)
    image = image.filter(ImageFilter.UnsharpMask(radius=0.7, percent=118, threshold=4))
    return image


def _scene_durations_for_voiceover(reel_plan: ReelPlan, voiceover_duration_seconds: float) -> list[float]:
    default = [float(scene.duration_seconds) for scene in reel_plan.scenes]
    default_total = sum(default)
    if voiceover_duration_seconds <= 0:
        return default
    target_total = max(default_total, float(voiceover_duration_seconds) + 0.5)
    word_counts = [max(1, len(scene.voiceover_line.split())) for scene in reel_plan.scenes]
    total_words = sum(word_counts)
    durations = [max(1.4, target_total * count / total_words) for count in word_counts]
    overflow = sum(durations) - target_total
    if overflow > 0:
        adjustable = [index for index, value in enumerate(durations) if value > 1.4]
        for index in adjustable:
            if overflow <= 0:
                break
            reduction = min(overflow, durations[index] - 1.4)
            durations[index] -= reduction
            overflow -= reduction
    underflow = target_total - sum(durations)
    if underflow > 0:
        durations[-1] += underflow
    return [round(value, 3) for value in durations]


def _scene_timings(scene_durations: list[float]) -> list[dict[str, object]]:
    timings: list[dict[str, object]] = []
    cursor = 0.0
    for index, duration in enumerate(scene_durations, start=1):
        start = cursor
        end = cursor + duration
        timings.append(
            {
                "scene_number": index,
                "start_seconds": round(start, 3),
                "end_seconds": round(end, 3),
                "duration_seconds": round(duration, 3),
            }
        )
        cursor = end
    return timings


def _render_motion_video(
    reel_plan: ReelPlan,
    image_paths: list[Path],
    output_path: Path,
    temp_dir: Path,
    ffmpeg_path: str,
    handle: str,
    scene_durations: list[float],
    cues: list[dict[str, object]],
) -> subprocess.CompletedProcess[str]:
    shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    cue_by_scene = {int(cue.get("index", 0) or 0): str(cue.get("text", "")) for cue in cues}
    frame_index = 0
    transition_frames = 5
    for index, scene in enumerate(reel_plan.scenes):
        image_path = image_paths[index]
        next_image_path = image_paths[index + 1] if index + 1 < len(image_paths) else None
        next_scene = reel_plan.scenes[index + 1] if index + 1 < len(reel_plan.scenes) else None
        scene_frames = max(1, int(round(scene_durations[index] * FPS)))
        for local_frame in range(scene_frames):
            progress = local_frame / max(1, scene_frames - 1)
            subtitle_progress = min(1.0, max(0.0, local_frame / max(1, int(FPS * 0.16))))
            frame = _compose_scene_frame(
                image_path=image_path,
                scene=scene,
                progress=progress,
                pan_direction=1 if scene.scene_number % 2 else -1,
                handle=handle,
                subtitle_text=cue_by_scene.get(scene.scene_number, ""),
                subtitle_progress=subtitle_progress,
            )
            if (
                scene.transition == "fade"
                and next_image_path is not None
                and next_scene is not None
                and local_frame >= scene_frames - transition_frames
            ):
                blend = (local_frame - (scene_frames - transition_frames)) / max(1, transition_frames - 1)
                next_frame = _compose_scene_frame(
                    image_path=next_image_path,
                    scene=next_scene,
                    progress=0.0,
                    pan_direction=1 if next_scene.scene_number % 2 else -1,
                    handle=handle,
                    subtitle_text="",
                )
                frame = Image.blend(frame, next_frame, min(0.45, blend * 0.45))
            frame.save(temp_dir / f"frame_{frame_index:05d}.jpg", "JPEG", quality=92)
            frame_index += 1

    command = [
        ffmpeg_path,
        "-y",
        "-framerate",
        str(FPS),
        "-i",
        str(temp_dir / "frame_%05d.jpg"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    shutil.rmtree(temp_dir, ignore_errors=True)
    return completed


def _draw_voiceover_subtitle(draw: ImageDraw.ImageDraw, text: str, progress: float) -> None:
    margin = 112
    max_width = REEL_SIZE[0] - margin * 2
    font = load_font(size=48, bold=True, warnings=[])
    lines = wrap_text(draw, text, font, max_width)[:2]
    if len(lines) > 1:
        font = load_font(size=44, bold=True, warnings=[])
        lines = wrap_text(draw, text, font, max_width)[:2]
    line_heights = [text_size(draw, line, font)[1] for line in lines]
    block_h = sum(line_heights) + max(0, len(lines) - 1) * 8
    y = 1300 - block_h // 2
    alpha = int(255 * min(1.0, max(0.0, progress)))

    for line in lines:
        width, height = text_size(draw, line, font)
        x = (REEL_SIZE[0] - width) // 2
        for dx, dy, shadow_alpha in ((0, 4, 180), (2, 2, 130), (-2, 2, 130), (0, 0, 220)):
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0, int(shadow_alpha * alpha / 255)))
        draw.text((x, y), line, font=font, fill=(255, 255, 255, alpha))
        y += height + 8
