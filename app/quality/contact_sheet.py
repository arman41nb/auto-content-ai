"""Create visual QA contact sheets for generated packages."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.render.fonts import load_font


def create_qa_contact_sheet(
    final_dir: Path,
    output_path: Path,
    publish_ready: bool | None = None,
    score: int | None = None,
    design_score: int | None = None,
    native_reel_score: int | None = None,
    ai_slideshow_risk_score: int | None = None,
    topic: str = "",
    reel_path: str = "",
    cover_path: str = "",
) -> Path:
    native_frames_dir = final_dir.parent / "final_reel" / "frames"
    native_frame_paths = sorted(path for path in native_frames_dir.glob("frame_*.jpg") if path.is_file())
    slide_paths = native_frame_paths or sorted(path for path in final_dir.glob("slide_*.jpg") if path.is_file())
    if not slide_paths:
        return output_path

    cover = Path(cover_path) if cover_path else final_dir.parent / "final_reel" / "cover.jpg"
    thumb_w, thumb_h = 216, 270
    cover_w, cover_h = 216, 384
    gap = 18
    header_h = 132
    sheet_w = (3 * thumb_w) + cover_w + (5 * gap)
    slide_rows = min(2, (min(5, len(slide_paths)) + 2) // 3)
    slide_area_h = slide_rows * (thumb_h + 44) - 44
    sheet_h = header_h + max(cover_h, slide_area_h) + 58
    canvas = Image.new("RGB", (sheet_w, sheet_h), (18, 18, 18))
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(size=24, bold=True, warnings=[])
    label_font = load_font(size=17, bold=False, warnings=[])
    meta_font = load_font(size=15, bold=False, warnings=[])

    status = []
    if publish_ready is not None:
        status.append(f"publish_ready={str(publish_ready).lower()}")
    if score is not None:
        status.append(f"technical={score}")
    if design_score is not None:
        status.append(f"design={design_score}")
    if native_reel_score is not None:
        status.append(f"native_reel={native_reel_score}")
    if ai_slideshow_risk_score is not None:
        status.append(f"slideshow_risk={ai_slideshow_risk_score}")
    draw.text((gap, 20), "QA Contact Sheet", font=title_font, fill=(242, 242, 238))
    draw.text((gap, 55), "  ".join(status), font=label_font, fill=(222, 222, 216))
    if topic:
        draw.text((gap, 82), f"topic: {topic}", font=meta_font, fill=(196, 196, 190))
    if reel_path:
        draw.text((gap, 106), f"reel: {reel_path}", font=meta_font, fill=(176, 176, 170))

    x = gap
    y = header_h
    if cover.exists():
        _paste_thumb(canvas, cover, (x, y), (cover_w, cover_h))
        draw.rectangle((x, y, x + cover_w, y + cover_h), outline=(88, 88, 84), width=1)
        draw.text((x, y + cover_h + 10), "cover", font=label_font, fill=(222, 222, 216))
    else:
        draw.rectangle((x, y, x + cover_w, y + cover_h), outline=(88, 88, 84), width=1)
        draw.text((x + 34, y + cover_h // 2), "cover missing", font=label_font, fill=(222, 160, 150))

    for index, path in enumerate(slide_paths[:5]):
        col = index % 3
        row = index // 3
        slide_x = x + cover_w + gap + col * (thumb_w + gap)
        slide_y = y + row * (thumb_h + 44)
        _paste_thumb(canvas, path, (slide_x, slide_y), (thumb_w, thumb_h))
        draw.rectangle((slide_x, slide_y, slide_x + thumb_w, slide_y + thumb_h), outline=(70, 70, 70), width=1)
        label = f"frame_{index + 1:02d}" if native_frame_paths else f"slide_{index + 1:02d}"
        draw.text((slide_x, slide_y + thumb_h + 9), label, font=label_font, fill=(222, 222, 216))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "JPEG", quality=92, optimize=True)
    return output_path


def create_batch_contact_sheet(candidates: list[dict[str, object]], output_path: Path) -> Path:
    if not candidates:
        return output_path

    thumb_size = (180, 320)
    card_w = 340
    card_h = 470
    gap = 22
    header_h = 82
    cols = min(3, max(1, len(candidates)))
    rows = (len(candidates) + cols - 1) // cols
    sheet_w = gap + cols * card_w + (cols - 1) * gap + gap
    sheet_h = header_h + rows * card_h + (rows - 1) * gap + gap
    canvas = Image.new("RGB", (sheet_w, sheet_h), (18, 18, 18))
    draw = ImageDraw.Draw(canvas)
    title_font = load_font(size=28, bold=True, warnings=[])
    label_font = load_font(size=18, bold=True, warnings=[])
    meta_font = load_font(size=15, bold=False, warnings=[])

    draw.text((gap, 22), "Batch Reel Candidates", font=title_font, fill=(244, 244, 240))
    for index, candidate in enumerate(candidates):
        col = index % cols
        row = index // cols
        x = gap + col * (card_w + gap)
        y = header_h + row * (card_h + gap)
        draw.rectangle((x, y, x + card_w, y + card_h), fill=(29, 29, 28), outline=(72, 72, 68), width=1)

        cover_path = Path(str(candidate.get("cover_path", "")))
        cover_x = x + (card_w - thumb_size[0]) // 2
        if cover_path.exists():
            _paste_thumb(canvas, cover_path, (cover_x, y + 18), thumb_size)
        else:
            draw.rectangle((cover_x, y + 18, cover_x + thumb_size[0], y + 18 + thumb_size[1]), outline=(100, 80, 78), width=1)
            draw.text((cover_x + 28, y + 162), "cover missing", font=meta_font, fill=(222, 160, 150))

        score = candidate.get("candidate_score", 0)
        publish_ready = str(candidate.get("publish_ready", False)).lower()
        audio = "voiceover ok" if candidate.get("audio_stream_present", False) else "voiceover check"
        draw.text((x + 16, y + 354), f"#{index + 1} score={score}", font=label_font, fill=(242, 242, 238))
        draw.text((x + 16, y + 382), f"publish_ready={publish_ready}", font=meta_font, fill=(212, 212, 206))
        draw.text((x + 16, y + 405), audio, font=meta_font, fill=(212, 212, 206))
        _draw_wrapped(draw, str(candidate.get("topic", "")), (x + 16, y + 430), card_w - 32, meta_font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "JPEG", quality=92, optimize=True)
    return output_path


def _paste_thumb(canvas: Image.Image, path: Path, xy: tuple[int, int], size: tuple[int, int]) -> None:
    image = Image.open(path).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    frame = Image.new("RGB", size, (8, 8, 8))
    frame.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    canvas.paste(frame, xy)


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    max_width: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
) -> None:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        proposed = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), proposed, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = proposed
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    x, y = xy
    for line in lines[:2]:
        draw.text((x, y), line, font=font, fill=(196, 196, 190))
        y += 20
