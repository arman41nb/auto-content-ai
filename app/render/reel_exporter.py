"""Create a native vertical Reel package from generated post images."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from app.content.schemas import CarouselPlan, CarouselSlide
from app.image.sanitizer import preferred_image_dir
from app.render.fonts import load_font
from app.render.layout import multiline_height, text_size, wrap_text


REEL_SIZE = (1080, 1920)
FPS = 24
DEFAULT_DURATION_SECONDS = 10


@dataclass(frozen=True)
class ReelExportResult:
    output_dir: Path
    reel_path: Path
    cover_path: Path
    created_video: bool
    warnings: list[str] = field(default_factory=list)


def export_reel_package(
    plan: CarouselPlan,
    final_dir: Path,
    raw_dir: Path,
    output_dir: Path,
    duration_seconds: int = DEFAULT_DURATION_SECONDS,
    handle: str = "@yourpage",
) -> ReelExportResult:
    """Export final_reel/reel.mp4, cover.jpg, and scene key frames."""

    reel_dir = output_dir / "final_reel"
    key_frames_dir = reel_dir / "reel_frames"
    temp_frames_dir = reel_dir / "_motion_frames"
    reel_path = reel_dir / "reel.mp4"
    cover_path = reel_dir / "cover.jpg"
    warnings: list[str] = []
    reel_dir.mkdir(parents=True, exist_ok=True)
    key_frames_dir.mkdir(parents=True, exist_ok=True)

    image_source_dir = preferred_image_dir(output_dir, raw_dir)
    image_paths = _collect_image_paths(image_source_dir) or _collect_image_paths(raw_dir) or _collect_image_paths(final_dir)
    if not image_paths:
        warning = "Reel package skipped because no slide images or raw images were available."
        (reel_dir / "README_TODO.txt").write_text(warning + "\n", encoding="utf-8")
        return ReelExportResult(reel_dir, reel_path, cover_path, created_video=False, warnings=[warning])

    scenes = _build_scenes(plan, image_paths)
    cover = _compose_reel_frame(
        image_path=scenes[0][0],
        slide=scenes[0][1],
        progress=0.0,
        pan_direction=1,
        handle=handle,
        cover_title=_cover_title(plan),
        is_cover=True,
    )
    cover.save(cover_path, "JPEG", quality=94, optimize=True)

    for index, (image_path, slide) in enumerate(scenes, start=1):
        key_frame = _compose_reel_frame(
            image_path=image_path,
            slide=slide,
            progress=0.35,
            pan_direction=1 if index % 2 else -1,
            handle=handle,
            cover_title="",
            is_cover=False,
        )
        key_frame.save(key_frames_dir / f"frame_{index:02d}.jpg", "JPEG", quality=92, optimize=True)

    scene_durations = _scene_durations(len(scenes), duration_seconds)
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        pyav_warning = _export_with_pyav(
            scenes=scenes,
            scene_durations=scene_durations,
            reel_path=reel_path,
            handle=handle,
        )
        if not pyav_warning:
            todo_path = reel_dir / "README_TODO.txt"
            if todo_path.exists():
                todo_path.unlink()
            warnings.append("FFmpeg was not found; reel.mp4 was created with PyAV/libx264 fallback.")
            return ReelExportResult(reel_dir, reel_path, cover_path, created_video=True, warnings=warnings)

        warning = "FFmpeg was not found and PyAV fallback failed, so reel.mp4 was not created."
        (reel_dir / "README_TODO.txt").write_text(warning + "\n", encoding="utf-8")
        (reel_dir / "pyav_error.txt").write_text(pyav_warning + "\n", encoding="utf-8")
        return ReelExportResult(reel_dir, reel_path, cover_path, created_video=False, warnings=[warning])

    temp_frames_dir.mkdir(parents=True, exist_ok=True)
    frame_index = 0
    for scene_index, ((image_path, slide), duration) in enumerate(zip(scenes, scene_durations), start=1):
        scene_frames = max(1, int(duration * FPS))
        for local_frame in range(scene_frames):
            progress = local_frame / max(1, scene_frames - 1)
            frame = _compose_reel_frame(
                image_path=image_path,
                slide=slide,
                progress=progress,
                pan_direction=1 if scene_index % 2 else -1,
                handle=handle,
                cover_title="",
                is_cover=False,
            )
            frame.save(temp_frames_dir / f"frame_{frame_index:04d}.jpg", "JPEG", quality=90)
            frame_index += 1

    command = [
        ffmpeg_path,
        "-y",
        "-framerate",
        str(FPS),
        "-i",
        str(temp_frames_dir / "frame_%04d.jpg"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(reel_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    shutil.rmtree(temp_frames_dir, ignore_errors=True)
    if completed.returncode != 0:
        warning = "FFmpeg failed while creating reel.mp4. See final_reel/ffmpeg_error.txt."
        (reel_dir / "ffmpeg_error.txt").write_text(
            (completed.stderr or completed.stdout or "Unknown FFmpeg error").strip() + "\n",
            encoding="utf-8",
        )
        return ReelExportResult(reel_dir, reel_path, cover_path, created_video=False, warnings=[warning])

    return ReelExportResult(reel_dir, reel_path, cover_path, created_video=True, warnings=warnings)


def _export_with_pyav(
    scenes: list[tuple[Path, CarouselSlide]],
    scene_durations: list[float],
    reel_path: Path,
    handle: str,
) -> str:
    try:
        import av  # type: ignore[import-not-found]
    except Exception as exc:
        return f"PyAV is not available: {exc}"

    try:
        container = av.open(str(reel_path), mode="w")
        stream = container.add_stream("libx264", rate=FPS)
        stream.width = REEL_SIZE[0]
        stream.height = REEL_SIZE[1]
        stream.pix_fmt = "yuv420p"
        for scene_index, ((image_path, slide), duration) in enumerate(zip(scenes, scene_durations), start=1):
            scene_frames = max(1, int(duration * FPS))
            for local_frame in range(scene_frames):
                progress = local_frame / max(1, scene_frames - 1)
                image = _compose_reel_frame(
                    image_path=image_path,
                    slide=slide,
                    progress=progress,
                    pan_direction=1 if scene_index % 2 else -1,
                    handle=handle,
                    cover_title="",
                    is_cover=False,
                )
                frame = av.VideoFrame.from_image(image)
                for packet in stream.encode(frame):
                    container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
        container.close()
        return ""
    except Exception as exc:
        try:
            container.close()  # type: ignore[name-defined]
        except Exception:
            pass
        return str(exc)


def _collect_image_paths(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(path for path in directory.glob("slide_*.jpg") if path.is_file() and "_variant_" not in path.name)


def _build_scenes(plan: CarouselPlan, image_paths: list[Path]) -> list[tuple[Path, CarouselSlide]]:
    slides = plan.slides or []
    scenes: list[tuple[Path, CarouselSlide]] = []
    for index, image_path in enumerate(image_paths[: max(1, len(slides))]):
        if slides:
            slide = slides[min(index, len(slides) - 1)]
        else:
            continue
        scenes.append((image_path, slide))
    return scenes or [(image_paths[0], slides[0])]


def _scene_durations(scene_count: int, duration_seconds: int) -> list[float]:
    if scene_count <= 0:
        return []
    minimum_total = scene_count * 1.6
    target_total = max(float(duration_seconds), minimum_total)
    base = max(1.6, min(2.2, target_total / scene_count))
    return [base for _ in range(scene_count)]


def _compose_reel_frame(
    image_path: Path,
    slide: CarouselSlide,
    progress: float,
    pan_direction: int,
    handle: str,
    cover_title: str,
    is_cover: bool,
) -> Image.Image:
    source = Image.open(image_path).convert("RGB")
    base = _cover_crop(source, REEL_SIZE)
    zoom = 1.035 + (0.055 * progress)
    zoomed = base.resize((int(REEL_SIZE[0] * zoom), int(REEL_SIZE[1] * zoom)), Image.Resampling.LANCZOS)
    max_x_shift = max(0, zoomed.width - REEL_SIZE[0])
    max_y_shift = max(0, zoomed.height - REEL_SIZE[1])
    x = -int(max_x_shift * progress) if pan_direction >= 0 else -int(max_x_shift * (1 - progress))
    y = -int(max_y_shift * (0.25 + 0.18 * progress))
    canvas = Image.new("RGBA", REEL_SIZE, (0, 0, 0, 255))
    canvas.alpha_composite(zoomed.convert("RGBA"), (x, y))
    canvas = Image.alpha_composite(canvas, Image.new("RGBA", REEL_SIZE, (0, 0, 0, 28)))
    canvas = Image.alpha_composite(canvas, _reel_gradient())

    if is_cover:
        _draw_cover_text(canvas, cover_title or slide.headline, slide.subtext, handle)
    else:
        _draw_scene_caption(canvas, slide, handle)
    return canvas.convert("RGB")


def _cover_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    scale = max(target_w / image.width, target_h / image.height)
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
    left = max(0, (resized.width - target_w) // 2)
    top = max(0, (resized.height - target_h) // 2)
    return resized.crop((left, top, left + target_w, top + target_h))


def _reel_gradient() -> Image.Image:
    gradient = Image.new("RGBA", REEL_SIZE, (0, 0, 0, 0))
    draw = ImageDraw.Draw(gradient)
    for y_pos in range(REEL_SIZE[1]):
        bottom = min(1, max(0, (y_pos - REEL_SIZE[1] * 0.54) / (REEL_SIZE[1] * 0.46)))
        top = max(0, 1 - y_pos / (REEL_SIZE[1] * 0.34))
        alpha = int(132 * bottom + 46 * top)
        draw.line([(0, y_pos), (REEL_SIZE[0], y_pos)], fill=(0, 0, 0, min(154, alpha)))
    return gradient


def _draw_cover_text(canvas: Image.Image, title: str, subtext: str, handle: str) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    margin = 78
    max_width = REEL_SIZE[0] - margin * 2
    label_font = load_font(size=24, bold=True, warnings=[])
    title_font = load_font(size=74, bold=True, warnings=[])
    subtext_font = load_font(size=32, bold=False, warnings=[])
    y = REEL_SIZE[1] - 520
    draw.rounded_rectangle((margin, y - 82, margin + 210, y - 42), radius=5, fill=(10, 10, 10, 82))
    draw.text((margin + 14, y - 75), "UNREAL SCIENCE", font=label_font, fill=(245, 242, 232, 224))
    draw.line((margin, y - 24, margin + 94, y - 24), fill=(216, 174, 102, 220), width=3)
    title_lines = wrap_text(draw, _title_case(title), title_font, max_width)[:3]
    for line in title_lines:
        _draw_shadowed_text(draw, (margin, y), line, title_font, (248, 248, 246, 255))
        y += text_size(draw, line, title_font)[1] + 10
    if subtext:
        y += 14
        for line in wrap_text(draw, subtext, subtext_font, max_width)[:2]:
            _draw_shadowed_text(draw, (margin, y), line, subtext_font, (229, 226, 218, 220), shadow_alpha=120)
            y += text_size(draw, line, subtext_font)[1] + 8
    _draw_handle(draw, handle)


def _draw_scene_caption(canvas: Image.Image, slide: CarouselSlide, handle: str) -> None:
    draw = ImageDraw.Draw(canvas, "RGBA")
    margin = 78
    max_width = REEL_SIZE[0] - margin * 2
    label_font = load_font(size=23, bold=True, warnings=[])
    headline_font = load_font(size=62, bold=True, warnings=[])
    subtext_font = load_font(size=30, bold=False, warnings=[])
    label = slide.tag.upper()
    y = REEL_SIZE[1] - 430
    draw.rounded_rectangle((margin, y - 70, margin + min(360, 24 + len(label) * 13), y - 32), radius=5, fill=(10, 10, 10, 76))
    draw.text((margin + 12, y - 64), label, font=label_font, fill=(245, 242, 232, 218))
    draw.line((margin, y - 15, margin + 82, y - 15), fill=(216, 174, 102, 210), width=3)

    headline_lines = wrap_text(draw, _title_case(slide.headline), headline_font, max_width)[:2]
    block_height = multiline_height(draw, headline_lines, headline_font, 8)
    if block_height > 150:
        headline_font = load_font(size=54, bold=True, warnings=[])
        headline_lines = wrap_text(draw, _title_case(slide.headline), headline_font, max_width)[:2]
    for line in headline_lines:
        _draw_shadowed_text(draw, (margin, y), line, headline_font, (248, 248, 246, 255))
        y += text_size(draw, line, headline_font)[1] + 8
    if slide.subtext:
        y += 12
        for line in wrap_text(draw, slide.subtext, subtext_font, max_width)[:2]:
            _draw_shadowed_text(draw, (margin, y), line, subtext_font, (229, 226, 218, 218), shadow_alpha=118)
            y += text_size(draw, line, subtext_font)[1] + 7
    _draw_handle(draw, handle)


def _draw_shadowed_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font,
    fill: tuple[int, int, int, int],
    shadow_alpha: int = 176,
) -> None:
    x, y = xy
    for dx, dy, alpha in ((0, 4, shadow_alpha), (2, 2, shadow_alpha // 2), (-2, 2, shadow_alpha // 2)):
        draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, alpha))
    draw.text((x, y), text, font=font, fill=fill)


def _draw_handle(draw: ImageDraw.ImageDraw, handle: str) -> None:
    font = load_font(size=24, bold=False, warnings=[])
    handle_w, handle_h = text_size(draw, handle, font)
    draw.text(
        (REEL_SIZE[0] - 78 - handle_w, REEL_SIZE[1] - 90 - handle_h),
        handle,
        font=font,
        fill=(238, 236, 230, 154),
    )


def _cover_title(plan: CarouselPlan) -> str:
    topic = plan.topic.strip().rstrip("?")
    lower = topic.lower()
    if "ocean" in lower and "overnight" in lower:
        return "If The Ocean Moved Overnight"
    if lower.startswith("what if"):
        return topic + "?"
    return plan.title.strip() or topic


def _title_case(value: str) -> str:
    clean = " ".join(value.strip().split())
    if clean.isupper() or clean.islower():
        return clean.title()
    return clean
