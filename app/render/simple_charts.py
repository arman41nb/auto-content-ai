"""Simple vertical chart and diagram backgrounds for explainer scenes."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.content.explainer_schemas import ExplainerScene
from app.render.fonts import load_font
from app.render.layout import text_size, wrap_text


REEL_SIZE = (1080, 1920)


def create_chart_for_scene(scene: ExplainerScene, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lower = f"{scene.visual_goal} {scene.media_query}".lower()
    if "oil" in lower and "import" in lower:
        image = relationship_arrows(
            title="Oil-Dollar Chain",
            nodes=["Oil price UP", "Import bill UP", "Dollar demand UP", "Currency pressure UP"],
        )
    elif "comparison" in lower:
        image = two_column_comparison("Compare", "Before", "After")
    elif "line" in lower:
        image = simple_line_placeholder(scene.on_screen_text)
    else:
        image = relationship_arrows(scene.on_screen_text.title(), ["Cause", "Pressure", "Response", "Caveat"])
    image.save(output_path, "JPEG", quality=95, optimize=True)
    return output_path


def relationship_arrows(title: str, nodes: list[str]) -> Image.Image:
    image = _base()
    draw = ImageDraw.Draw(image, "RGBA")
    title_font = load_font(size=62, bold=True, warnings=[])
    node_font = load_font(size=42, bold=True, warnings=[])
    small_font = load_font(size=28, bold=False, warnings=[])
    margin = 94
    y = 230
    for line in wrap_text(draw, title, title_font, REEL_SIZE[0] - margin * 2)[:2]:
        draw.text((margin, y), line, font=title_font, fill=(248, 248, 242, 255))
        y += text_size(draw, line, title_font)[1] + 8
    draw.text((margin, y + 12), "Simplified mechanism, not financial advice", font=small_font, fill=(220, 226, 214, 185))
    y = 520
    for index, node in enumerate(nodes):
        box = (margin, y, REEL_SIZE[0] - margin, y + 150)
        fill = (34, 48, 57, 238) if index % 2 == 0 else (44, 48, 38, 238)
        draw.rounded_rectangle(box, radius=8, fill=fill, outline=(221, 185, 104, 210), width=3)
        lines = wrap_text(draw, node, node_font, box[2] - box[0] - 56)[:2]
        text_y = y + 45 - (len(lines) - 1) * 20
        for line in lines:
            width, height = text_size(draw, line, node_font)
            draw.text(((REEL_SIZE[0] - width) // 2, text_y), line, font=node_font, fill=(250, 248, 236, 255))
            text_y += height + 6
        if index < len(nodes) - 1:
            arrow_y = y + 174
            draw.line((REEL_SIZE[0] // 2, arrow_y, REEL_SIZE[0] // 2, arrow_y + 80), fill=(221, 185, 104, 230), width=5)
            draw.polygon(
                [
                    (REEL_SIZE[0] // 2 - 20, arrow_y + 76),
                    (REEL_SIZE[0] // 2 + 20, arrow_y + 76),
                    (REEL_SIZE[0] // 2, arrow_y + 112),
                ],
                fill=(221, 185, 104, 230),
            )
        y += 262
    return image


def two_column_comparison(title: str, left: str, right: str) -> Image.Image:
    image = _base()
    draw = ImageDraw.Draw(image, "RGBA")
    title_font = load_font(size=62, bold=True, warnings=[])
    body_font = load_font(size=42, bold=True, warnings=[])
    draw.text((92, 260), title, font=title_font, fill=(248, 248, 242, 255))
    draw.rounded_rectangle((92, 560, 516, 1280), radius=8, fill=(34, 48, 57, 238))
    draw.rounded_rectangle((564, 560, 988, 1280), radius=8, fill=(44, 48, 38, 238))
    draw.text((132, 620), left, font=body_font, fill=(250, 248, 236, 255))
    draw.text((604, 620), right, font=body_font, fill=(250, 248, 236, 255))
    return image


def simple_line_placeholder(title: str) -> Image.Image:
    image = _base()
    draw = ImageDraw.Draw(image, "RGBA")
    title_font = load_font(size=62, bold=True, warnings=[])
    draw.text((92, 260), title, font=title_font, fill=(248, 248, 242, 255))
    points = [(120, 1280), (310, 1180), (500, 1210), (690, 920), (880, 1040), (980, 860)]
    draw.line(points, fill=(221, 185, 104, 255), width=8)
    for point in points:
        draw.ellipse((point[0] - 10, point[1] - 10, point[0] + 10, point[1] + 10), fill=(244, 236, 205, 255))
    return image


def _base() -> Image.Image:
    image = Image.new("RGB", REEL_SIZE, (18, 24, 29))
    draw = ImageDraw.Draw(image, "RGBA")
    for y in range(REEL_SIZE[1]):
        amount = y / REEL_SIZE[1]
        draw.line((0, y, REEL_SIZE[0], y), fill=(18 + int(10 * amount), 24 + int(18 * amount), 29 + int(12 * amount)))
    draw.rectangle((0, 0, REEL_SIZE[0], REEL_SIZE[1]), outline=(221, 185, 104, 90), width=2)
    return image
