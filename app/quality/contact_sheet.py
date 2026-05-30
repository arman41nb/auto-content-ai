"""Create visual QA contact sheets for generated packages."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.render.fonts import load_font


def create_qa_contact_sheet(
    final_dir: Path,
    output_path: Path,
    publish_ready: bool | None = None,
    score: int | None = None,
    design_score: int | None = None,
    topic: str = "",
    reel_path: str = "",
    cover_path: str = "",
) -> Path:
    slide_paths = sorted(path for path in final_dir.glob("slide_*.jpg") if path.is_file())
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
        draw.text((slide_x, slide_y + thumb_h + 9), f"slide_{index + 1:02d}", font=label_font, fill=(222, 222, 216))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "JPEG", quality=92, optimize=True)
    return output_path


def _paste_thumb(canvas: Image.Image, path: Path, xy: tuple[int, int], size: tuple[int, int]) -> None:
    image = Image.open(path).convert("RGB")
    image.thumbnail(size, Image.Resampling.LANCZOS)
    frame = Image.new("RGB", size, (8, 8, 8))
    frame.paste(image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2))
    canvas.paste(frame, xy)
