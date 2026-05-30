"""Render finished Instagram carousel slides with Pillow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.content.schemas import CarouselPlan, CarouselSlide
from app.image.sanitizer import preferred_image_path
from app.render.fonts import load_font, load_font_set
from app.render.layout import multiline_height, text_size, wrap_text


CANVAS_SIZE = (1080, 1350)
MARGIN_X = 76
MARGIN_Y = 74
WHITE = (248, 248, 246, 255)
MUTED = (226, 224, 218, 226)
SOFT = (226, 222, 214, 178)
ACCENT = (216, 174, 102, 230)
BADGE_FILL = (18, 17, 15, 120)
BADGE_OUTLINE = (255, 255, 255, 50)
EDITORIAL_TEMPLATE = "cinematic_reel_editorial"


@dataclass(frozen=True)
class RenderTemplate:
    name: str
    headline_max_size: int
    headline_min_size: int
    subtext_size: int
    max_width: int
    max_height: int
    panel_alpha: int
    panel_padding_x: int
    panel_padding_y: int
    line_spacing: int
    gap: int
    align: str


TEMPLATES = {
    "cinematic_cover": RenderTemplate(
        name="cinematic_cover",
        headline_max_size=88,
        headline_min_size=52,
        subtext_size=38,
        max_width=790,
        max_height=520,
        panel_alpha=52,
        panel_padding_x=34,
        panel_padding_y=28,
        line_spacing=12,
        gap=24,
        align="left",
    ),
    "cinematic_body": RenderTemplate(
        name="cinematic_body",
        headline_max_size=68,
        headline_min_size=42,
        subtext_size=34,
        max_width=720,
        max_height=420,
        panel_alpha=62,
        panel_padding_x=30,
        panel_padding_y=24,
        line_spacing=10,
        gap=20,
        align="left",
    ),
    "cinematic_cta": RenderTemplate(
        name="cinematic_cta",
        headline_max_size=82,
        headline_min_size=48,
        subtext_size=40,
        max_width=760,
        max_height=500,
        panel_alpha=56,
        panel_padding_x=34,
        panel_padding_y=28,
        line_spacing=11,
        gap=24,
        align="center",
    ),
    "editorial_cover": RenderTemplate(
        name="cinematic_reel_editorial_cover",
        headline_max_size=78,
        headline_min_size=42,
        subtext_size=30,
        max_width=830,
        max_height=250,
        panel_alpha=0,
        panel_padding_x=0,
        panel_padding_y=0,
        line_spacing=8,
        gap=18,
        align="left",
    ),
    "editorial_body": RenderTemplate(
        name="cinematic_reel_editorial_body",
        headline_max_size=64,
        headline_min_size=36,
        subtext_size=28,
        max_width=760,
        max_height=220,
        panel_alpha=0,
        panel_padding_x=0,
        panel_padding_y=0,
        line_spacing=7,
        gap=14,
        align="left",
    ),
    "editorial_cta": RenderTemplate(
        name="cinematic_reel_editorial_cta",
        headline_max_size=70,
        headline_min_size=38,
        subtext_size=30,
        max_width=800,
        max_height=230,
        panel_alpha=0,
        panel_padding_x=0,
        panel_padding_y=0,
        line_spacing=8,
        gap=16,
        align="left",
    ),
}


class CarouselRenderer:
    def __init__(self, handle: str = "@yourpage", template_name: str = EDITORIAL_TEMPLATE) -> None:
        self.handle = handle
        self.template_name = template_name.strip() or EDITORIAL_TEMPLATE
        self.fonts = load_font_set()
        self.warnings = list(self.fonts.warnings)
        self.template_used_per_slide: dict[str, str] = {}

    def render_plan(
        self,
        plan: CarouselPlan,
        raw_dir: Path,
        final_dir: Path,
        sanitized_dir: Path | None = None,
    ) -> dict[str, str]:
        final_dir.mkdir(parents=True, exist_ok=True)
        total = len(plan.slides)
        for slide in plan.slides:
            raw_path = raw_dir / f"slide_{slide.slide_number:02d}.jpg"
            if sanitized_dir is not None:
                raw_path = preferred_image_path(raw_path, sanitized_dir)
            output_path = final_dir / f"slide_{slide.slide_number:02d}.jpg"
            self.render_slide(slide, raw_path, output_path, total)
        return self.template_used_per_slide

    def render_slide(self, slide: CarouselSlide, raw_path: Path, output_path: Path, total: int) -> None:
        image = Image.open(raw_path).convert("RGB")
        canvas = self._cover_crop(image).convert("RGBA")
        template = self._template_for_slide(slide, total)
        self.template_used_per_slide[f"slide_{slide.slide_number:02d}"] = template.name

        if self._uses_editorial_template():
            canvas = self._render_editorial_slide(canvas, slide, template, total)
        else:
            canvas = self._render_legacy_slide(canvas, slide, template, total)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        canvas.convert("RGB").save(output_path, "JPEG", quality=94, optimize=True)

    def _render_legacy_slide(
        self,
        canvas: Image.Image,
        slide: CarouselSlide,
        template: RenderTemplate,
        total: int,
    ) -> Image.Image:
        canvas = self._apply_gradient_overlay(canvas, slide.text_position, template)
        canvas = canvas.filter(ImageFilter.UnsharpMask(radius=1.0, percent=115, threshold=3))
        draw = ImageDraw.Draw(canvas, "RGBA")
        self._draw_badge(draw, slide.tag, template)
        self._draw_slide_number(draw, slide.slide_number, total)
        self._draw_handle(draw)
        self._draw_text_block(draw, slide, template)
        return canvas

    def _render_editorial_slide(
        self,
        canvas: Image.Image,
        slide: CarouselSlide,
        template: RenderTemplate,
        total: int,
    ) -> Image.Image:
        canvas = self._apply_editorial_gradient(canvas, slide, template)
        canvas = canvas.filter(ImageFilter.UnsharpMask(radius=0.8, percent=108, threshold=4))
        draw = ImageDraw.Draw(canvas, "RGBA")
        self._draw_editorial_label(draw, slide, template)
        self._draw_editorial_meta(draw, slide.slide_number, total)
        self._draw_editorial_text(draw, slide, template)
        return canvas

    def _uses_editorial_template(self) -> bool:
        return self.template_name == EDITORIAL_TEMPLATE

    def _cover_crop(self, image: Image.Image) -> Image.Image:
        target_w, target_h = CANVAS_SIZE
        scale = max(target_w / image.width, target_h / image.height)
        resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
        left = max(0, (resized.width - target_w) // 2)
        top = max(0, (resized.height - target_h) // 2)
        return resized.crop((left, top, left + target_w, top + target_h))

    def _apply_editorial_gradient(
        self,
        image: Image.Image,
        slide: CarouselSlide,
        template: RenderTemplate,
    ) -> Image.Image:
        width, height = image.size
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if slide.text_position == "top_left":
            start, end, max_alpha = 0.0, 0.48, 118
            for y in range(height):
                progress = 1 - min(1, max(0, (y - height * start) / (height * end)))
                alpha = int(max_alpha * progress)
                draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))
        else:
            start = 0.48 if template.name.endswith("cover") else 0.55
            max_alpha = 148 if template.name.endswith("cover") else 124
            for y in range(height):
                progress = min(1, max(0, (y - height * start) / (height * (1 - start))))
                alpha = int(max_alpha * progress)
                draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

        side = Image.new("RGBA", image.size, (0, 0, 0, 0))
        side_draw = ImageDraw.Draw(side)
        for x in range(width):
            alpha = int(46 * max(0, 1 - x / (width * 0.44)))
            side_draw.line([(x, 0), (x, height)], fill=(0, 0, 0, alpha))

        vignette = Image.new("RGBA", image.size, (0, 0, 0, 22))
        vignette_draw = ImageDraw.Draw(vignette)
        vignette_draw.rectangle((0, 0, width, height), outline=(0, 0, 0, 42), width=26)
        return Image.alpha_composite(Image.alpha_composite(Image.alpha_composite(image, overlay), side), vignette)

    def _draw_editorial_label(
        self,
        draw: ImageDraw.ImageDraw,
        slide: CarouselSlide,
        template: RenderTemplate,
    ) -> None:
        label = (slide.tag or "FIELD NOTE").upper()
        if template.name.endswith("cover"):
            label = f"{label} / WHAT IF"
        font = load_font(size=22, bold=True, warnings=self.warnings)
        x, y = MARGIN_X, MARGIN_Y
        padding_x, padding_y = 12, 7
        bbox = draw.textbbox((x, y), label, font=font)
        rect = (bbox[0] - padding_x, bbox[1] - padding_y, bbox[2] + padding_x, bbox[3] + padding_y)
        draw.rounded_rectangle(rect, radius=5, fill=(12, 13, 13, 76), outline=(255, 255, 255, 38), width=1)
        draw.text((x, y), label, font=font, fill=(245, 242, 232, 228))
        draw.line((x, rect[3] + 18, x + 64, rect[3] + 18), fill=ACCENT, width=3)

    def _draw_editorial_meta(self, draw: ImageDraw.ImageDraw, current: int, total: int) -> None:
        count_font = load_font(size=22, bold=False, warnings=self.warnings)
        label = f"{current}/{total}"
        count_w, count_h = text_size(draw, label, count_font)
        draw.text(
            (CANVAS_SIZE[0] - MARGIN_X - count_w, MARGIN_Y + 2),
            label,
            font=count_font,
            fill=(235, 232, 224, 172),
        )
        handle_font = load_font(size=22, bold=False, warnings=self.warnings)
        handle_w, handle_h = text_size(draw, self.handle, handle_font)
        draw.text(
            (MARGIN_X, CANVAS_SIZE[1] - MARGIN_Y - handle_h),
            self.handle,
            font=handle_font,
            fill=(238, 236, 230, 158),
        )

    def _draw_editorial_text(
        self,
        draw: ImageDraw.ImageDraw,
        slide: CarouselSlide,
        template: RenderTemplate,
    ) -> None:
        max_width = min(template.max_width, CANVAS_SIZE[0] - (MARGIN_X * 2))
        headline_font, headline_lines = self._fit_headline(
            draw,
            _title_case_for_display(slide.headline),
            max_width,
            template.max_height,
            template,
            max_lines=2,
        )
        subtext_font = load_font(size=template.subtext_size, bold=False, warnings=self.warnings)
        subtext_lines = wrap_text(draw, slide.subtext, subtext_font, max_width) if slide.subtext else []
        subtext_lines = subtext_lines[:2]

        headline_height = multiline_height(draw, headline_lines, headline_font, template.line_spacing)
        subtext_height = multiline_height(draw, subtext_lines, subtext_font, 8)
        gap = template.gap if subtext_lines else 0
        block_height = headline_height + gap + subtext_height
        block_width = max(
            [text_size(draw, line or " ", headline_font)[0] for line in headline_lines]
            + [text_size(draw, line or " ", subtext_font)[0] for line in subtext_lines]
            + [max_width // 2]
        )
        x, y = self._editorial_text_origin(slide, block_width, block_height, template)
        draw.line((x, y - 22, x + 86, y - 22), fill=(216, 174, 102, 208), width=3)

        current_y = y
        for line in headline_lines:
            self._draw_shadowed_text(draw, (x, current_y), line, headline_font, WHITE)
            current_y += text_size(draw, line or " ", headline_font)[1] + template.line_spacing
        current_y += max(0, gap - template.line_spacing)
        for line in subtext_lines:
            self._draw_shadowed_text(draw, (x, current_y), line, subtext_font, MUTED, shadow_alpha=136)
            current_y += text_size(draw, line or " ", subtext_font)[1] + 8

    def _editorial_text_origin(
        self,
        slide: CarouselSlide,
        block_width: int,
        block_height: int,
        template: RenderTemplate,
    ) -> tuple[int, int]:
        if slide.text_position == "top_left":
            return MARGIN_X, 246
        if slide.text_position == "center":
            return MARGIN_X, max(440, (CANVAS_SIZE[1] - block_height) // 2 + 130)
        if template.name.endswith("cta"):
            return MARGIN_X, CANVAS_SIZE[1] - MARGIN_Y - 250 - block_height
        if template.name.endswith("cover"):
            return MARGIN_X, CANVAS_SIZE[1] - MARGIN_Y - 250 - block_height
        return MARGIN_X, CANVAS_SIZE[1] - MARGIN_Y - 190 - block_height

    def _draw_shadowed_text(
        self,
        draw: ImageDraw.ImageDraw,
        xy: tuple[int, int],
        text: str,
        font: ImageFont.ImageFont,
        fill: tuple[int, int, int, int],
        shadow_alpha: int = 182,
    ) -> None:
        x, y = xy
        for dx, dy, alpha in ((0, 3, shadow_alpha), (2, 2, shadow_alpha // 2), (-2, 2, shadow_alpha // 2)):
            draw.text((x + dx, y + dy), text, font=font, fill=(0, 0, 0, alpha))
        draw.text((x, y), text, font=font, fill=fill)

    def _apply_gradient_overlay(self, image: Image.Image, position: str, template: RenderTemplate) -> Image.Image:
        width, height = image.size
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        for y in range(height):
            if template.name == "cinematic_cover":
                alpha = int(max(18, 205 * ((y - height * 0.18) / (height * 0.82))))
            elif template.name == "cinematic_cta":
                distance = abs(y - height / 2) / (height / 2)
                alpha = int(max(26, 184 * (1 - distance)))
            elif position == "top_left":
                alpha = int(max(8, 185 * (1 - y / (height * 0.68))))
            elif position == "center":
                distance = abs(y - height / 2) / (height / 2)
                alpha = int(max(28, 152 * (1 - distance)))
            else:
                alpha = int(max(12, 218 * ((y - height * 0.26) / (height * 0.74))))
            if y > height * 0.70:
                lower_progress = (y - height * 0.70) / (height * 0.30)
                alpha = max(alpha, int(62 + 162 * lower_progress))
            alpha = max(0, min(224, alpha))
            draw.line([(0, y), (width, y)], fill=(0, 0, 0, alpha))

        vignette = Image.new("RGBA", image.size, (0, 0, 0, 48))
        vignette_draw = ImageDraw.Draw(vignette)
        vignette_draw.rectangle((0, 0, width, height), outline=(0, 0, 0, 78), width=34)
        return Image.alpha_composite(Image.alpha_composite(image, overlay), vignette)

    def _draw_badge(self, draw: ImageDraw.ImageDraw, tag: str, template: RenderTemplate) -> None:
        x, y = MARGIN_X, MARGIN_Y
        if template.name == "cinematic_cover":
            label = f"{tag} / FIELD NOTE"
        elif template.name == "cinematic_cta":
            label = tag
        else:
            label = tag

        padding_x, padding_y = 16, 9
        bbox = draw.textbbox((x, y), label, font=self.fonts.badge)
        rect = (
            bbox[0] - padding_x,
            bbox[1] - padding_y,
            bbox[2] + padding_x,
            bbox[3] + padding_y,
        )
        draw.rounded_rectangle(rect, radius=6, fill=BADGE_FILL, outline=BADGE_OUTLINE, width=1)
        draw.text((x, y), label, font=self.fonts.badge, fill=(242, 239, 231, 226))
        draw.line((x, rect[3] + 18, x + 76, rect[3] + 18), fill=ACCENT, width=3)

    def _draw_slide_number(self, draw: ImageDraw.ImageDraw, current: int, total: int) -> None:
        label = f"{current:02d}/{total:02d}"
        width, _ = text_size(draw, label, self.fonts.meta)
        draw.text((CANVAS_SIZE[0] - MARGIN_X - width, MARGIN_Y + 4), label, font=self.fonts.meta, fill=MUTED)

    def _draw_handle(self, draw: ImageDraw.ImageDraw) -> None:
        width, height = text_size(draw, self.handle, self.fonts.meta)
        draw.text(
            (CANVAS_SIZE[0] - MARGIN_X - width, CANVAS_SIZE[1] - MARGIN_Y - height),
            self.handle,
            font=self.fonts.meta,
            fill=(235, 235, 232, 165),
        )

    def _draw_text_block(self, draw: ImageDraw.ImageDraw, slide: CarouselSlide, template: RenderTemplate) -> None:
        max_width = min(template.max_width, CANVAS_SIZE[0] - (MARGIN_X * 2))
        headline_font, headline_lines = self._fit_headline(
            draw,
            slide.headline,
            max_width,
            template.max_height,
            template,
        )
        subtext_font = load_font(size=template.subtext_size, bold=False, warnings=self.warnings)
        subtext_lines = wrap_text(draw, slide.subtext, subtext_font, max_width) if slide.subtext else []

        content_width = max(
            [text_size(draw, line or " ", headline_font)[0] for line in headline_lines]
            + [text_size(draw, line or " ", subtext_font)[0] for line in subtext_lines]
            + [max_width // 2]
        )
        min_width = 560 if template.name != "cinematic_body" else 460
        block_width = min(max_width, max(min_width, content_width))

        headline_height = multiline_height(draw, headline_lines, headline_font, template.line_spacing)
        subtext_height = multiline_height(draw, subtext_lines, subtext_font, 10)
        gap = template.gap if subtext_lines else 0
        block_height = headline_height + gap + subtext_height

        x, y = self._text_origin(slide.text_position, block_height, block_width, template)
        self._draw_soft_panel(draw, x, y, block_width, block_height, template)
        current_y = y
        for line in headline_lines:
            line_x = self._line_x(draw, line, headline_font, x, block_width, template)
            draw.text((line_x, current_y), line, font=headline_font, fill=WHITE)
            current_y += text_size(draw, line or " ", headline_font)[1] + template.line_spacing
        current_y += max(0, gap - template.line_spacing)
        for line in subtext_lines:
            line_x = self._line_x(draw, line, subtext_font, x, block_width, template)
            draw.text((line_x, current_y), line, font=subtext_font, fill=MUTED)
            current_y += text_size(draw, line or " ", subtext_font)[1] + 10

    def _fit_headline(
        self,
        draw: ImageDraw.ImageDraw,
        headline: str,
        max_width: int,
        max_height: int,
        template: RenderTemplate,
        max_lines: int = 5,
    ) -> tuple[ImageFont.ImageFont, list[str]]:
        warnings: list[str] = []
        for size in range(template.headline_max_size, template.headline_min_size - 1, -4):
            font = load_font(size=size, bold=True, warnings=warnings)
            lines = wrap_text(draw, headline, font, max_width)
            if (
                multiline_height(draw, lines, font, template.line_spacing) <= max_height
                and len(lines) <= max_lines
            ):
                self.warnings.extend(warnings)
                return font, lines
        font = load_font(size=template.headline_min_size, bold=True, warnings=warnings)
        self.warnings.extend(warnings)
        return font, wrap_text(draw, headline, font, max_width)[:max_lines]

    def _text_origin(
        self,
        position: str,
        block_height: int,
        block_width: int,
        template: RenderTemplate,
    ) -> tuple[int, int]:
        if template.name == "cinematic_cover":
            return MARGIN_X, max(690, CANVAS_SIZE[1] - 305 - block_height)
        if template.name == "cinematic_cta":
            x = (CANVAS_SIZE[0] - block_width) // 2
            return x, max(520, (CANVAS_SIZE[1] - block_height) // 2 + 130)
        if position == "top_left":
            return MARGIN_X, 228
        if position == "center":
            return MARGIN_X, max(312, (CANVAS_SIZE[1] - block_height) // 2 + 80)
        return MARGIN_X, max(760, CANVAS_SIZE[1] - MARGIN_Y - 158 - block_height)

    def _draw_soft_panel(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        width: int,
        height: int,
        template: RenderTemplate,
    ) -> None:
        pad_x = template.panel_padding_x
        pad_y = template.panel_padding_y
        rect = (x - pad_x, y - pad_y, x + width + pad_x, y + height + pad_y)
        draw.rounded_rectangle(rect, radius=8, fill=(12, 11, 9, template.panel_alpha), outline=(255, 255, 255, 16), width=1)
        if template.name == "cinematic_cover":
            draw.line((rect[0], rect[1], rect[0], rect[3]), fill=ACCENT, width=5)
        elif template.name == "cinematic_cta":
            draw.line((rect[0] + 36, rect[1] + 20, rect[2] - 36, rect[1] + 20), fill=(255, 255, 255, 34), width=1)
            draw.line((rect[0] + 36, rect[3] - 20, rect[2] - 36, rect[3] - 20), fill=(255, 255, 255, 34), width=1)

    def _line_x(
        self,
        draw: ImageDraw.ImageDraw,
        line: str,
        font: ImageFont.ImageFont,
        x: int,
        max_width: int,
        template: RenderTemplate,
    ) -> int:
        if template.align != "center":
            return x
        width, _ = text_size(draw, line, font)
        return x + max(0, (max_width - width) // 2)

    def _template_for_slide(self, slide: CarouselSlide, total: int) -> RenderTemplate:
        if self._uses_editorial_template():
            if slide.slide_number == 1 or slide.role == "hook":
                return TEMPLATES["editorial_cover"]
            if slide.slide_number == total or slide.role in {"CTA", "final"}:
                return TEMPLATES["editorial_cta"]
            return TEMPLATES["editorial_body"]
        if slide.slide_number == 1 or slide.role == "hook":
            return TEMPLATES["cinematic_cover"]
        if slide.slide_number == total or slide.role in {"CTA", "final"}:
            return TEMPLATES["cinematic_cta"]
        return TEMPLATES["cinematic_body"]


def _title_case_for_display(value: str) -> str:
    if value.isupper() and len(value.split()) > 1:
        return value.title()
    return value
