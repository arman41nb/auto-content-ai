"""Render native 1080x1920 cinematic Reel stories."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from app.content.reel_schemas import ReelPlan, ReelScene
from app.render.fonts import load_font
from app.render.layout import text_size, wrap_text


REEL_SIZE = (1080, 1920)
FPS = 24


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
) -> NativeReelRenderResult:
    """Render final_reel/reel.mp4, cover.jpg, and scene frames from native scene images."""

    reel_dir = output_dir / "final_reel"
    frames_dir = reel_dir / "frames"
    temp_dir = reel_dir / "_native_motion_frames"
    reel_path = reel_dir / "reel.mp4"
    cover_path = reel_dir / "cover.jpg"
    warnings: list[str] = []
    frame_paths: list[Path] = []
    reel_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)

    scene_image_paths = [_scene_image_path(image_dir, scene.scene_number) for scene in reel_plan.scenes]
    missing = [path.name for path in scene_image_paths if not path.exists()]
    if missing:
        warning = "Native Reel render skipped because scene image(s) are missing: " + ", ".join(missing) + "."
        (reel_dir / "README_TODO.txt").write_text(warning + "\n", encoding="utf-8")
        return NativeReelRenderResult(reel_dir, reel_path, cover_path, frame_paths, False, [warning])

    cover = _compose_cover(scene_image_paths[0], reel_plan.cover_text, handle)
    cover.save(cover_path, "JPEG", quality=95, optimize=True)

    for scene, image_path in zip(reel_plan.scenes, scene_image_paths):
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

    temp_dir.mkdir(parents=True, exist_ok=True)
    frame_index = 0
    for index, scene in enumerate(reel_plan.scenes):
        image_path = scene_image_paths[index]
        next_image_path = scene_image_paths[index + 1] if index + 1 < len(scene_image_paths) else None
        next_scene = reel_plan.scenes[index + 1] if index + 1 < len(reel_plan.scenes) else None
        scene_frames = max(1, int(scene.duration_seconds * FPS))
        for local_frame in range(scene_frames):
            progress = local_frame / max(1, scene_frames - 1)
            frame = _compose_scene_frame(
                image_path=image_path,
                scene=scene,
                progress=progress,
                pan_direction=1 if scene.scene_number % 2 else -1,
                handle=handle,
            )
            if scene.transition == "fade" and next_image_path is not None and next_scene is not None and progress > 0.88:
                blend = min(1.0, (progress - 0.88) / 0.12)
                next_frame = _compose_scene_frame(
                    image_path=next_image_path,
                    scene=next_scene,
                    progress=0.0,
                    pan_direction=1 if next_scene.scene_number % 2 else -1,
                    handle=handle,
                )
                frame = Image.blend(frame, next_frame, blend * 0.72)
            frame.save(temp_dir / f"frame_{frame_index:05d}.jpg", "JPEG", quality=91)
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
        str(reel_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    shutil.rmtree(temp_dir, ignore_errors=True)
    if completed.returncode != 0 or not reel_path.exists():
        warning = "FFmpeg failed while creating native reel.mp4. See final_reel/ffmpeg_error.txt."
        (reel_dir / "ffmpeg_error.txt").write_text(
            (completed.stderr or completed.stdout or "Unknown FFmpeg error").strip() + "\n",
            encoding="utf-8",
        )
        return NativeReelRenderResult(reel_dir, reel_path, cover_path, frame_paths, False, [warning])

    metadata = {
        "renderer": "native_reel_story",
        "canvas_size": [REEL_SIZE[0], REEL_SIZE[1]],
        "fps": FPS,
        "duration_seconds": round(sum(scene.duration_seconds for scene in reel_plan.scenes), 2),
        "scene_count": len(reel_plan.scenes),
        "motion": "per-scene slow zoom 100-108 percent with 2-4 percent pan",
        "source": "native_fullscreen_scene_images",
        "text_style": "minimal shadowed kinetic captions, no black boxes",
        "frame_paths": [str(path) for path in frame_paths],
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
) -> Image.Image:
    canvas = _motion_background(image_path, progress=progress, pan_direction=pan_direction)
    canvas = Image.alpha_composite(canvas, _gradient_overlay(strength=0.86))
    canvas = canvas.filter(ImageFilter.UnsharpMask(radius=0.65, percent=105, threshold=5))
    draw = ImageDraw.Draw(canvas, "RGBA")
    _draw_caption(draw, scene, progress)
    _draw_micro_scene_number(draw, scene.scene_number)
    _draw_handle(draw, handle)
    return canvas.convert("RGB")


def _motion_background(image_path: Path, progress: float, pan_direction: int) -> Image.Image:
    with Image.open(image_path) as source:
        base = _cover_crop(source.convert("RGB"), REEL_SIZE)
    zoom = 1.0 + 0.08 * max(0.0, min(1.0, progress))
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
        alpha = int((116 * bottom + 34 * top) * strength)
        draw.line([(0, y_pos), (REEL_SIZE[0], y_pos)], fill=(0, 0, 0, min(150, alpha)))
    return gradient


def _draw_caption(draw: ImageDraw.ImageDraw, scene: ReelScene, progress: float) -> None:
    margin = 78
    max_width = REEL_SIZE[0] - margin * 2
    font = load_font(size=68, bold=True, warnings=[])
    lines = wrap_text(draw, scene.on_screen_text.upper(), font, max_width)[:2]
    if len(lines) == 2:
        font = load_font(size=62, bold=True, warnings=[])
        lines = wrap_text(draw, scene.on_screen_text.upper(), font, max_width)[:2]
    y = REEL_SIZE[1] - 348
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
