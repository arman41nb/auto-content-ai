"""Deterministic safe-zone caption layout for native Reel captions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PIL import ImageDraw

from app.render.fonts import load_font
from app.render.layout import text_size


REEL_SIZE = (1080, 1920)


Box = tuple[int, int, int, int]


@dataclass(frozen=True)
class CaptionSafeZones:
    top: int = 160
    bottom: int = 260
    side: int = 80
    caption_preferred_min_y: int = 1280
    caption_preferred_max_y: int = 1450
    hook_preferred_y: int = 760


@dataclass(frozen=True)
class TextStylePreset:
    name: str
    base_font_size: int
    min_font_size: int
    active_fill: tuple[int, int, int, int]
    inactive_fill: tuple[int, int, int, int]
    future_fill: tuple[int, int, int, int]
    stroke_width: int
    background_fill: tuple[int, int, int, int]
    background_padding_x: int
    background_padding_y: int
    word_gap: int = 18
    line_gap: int = 12


STYLE_PRESETS: dict[str, TextStylePreset] = {
    "pro_yellow_word": TextStylePreset(
        name="pro_yellow_word",
        base_font_size=62,
        min_font_size=46,
        active_fill=(255, 226, 67, 255),
        inactive_fill=(248, 248, 246, 236),
        future_fill=(232, 232, 228, 172),
        stroke_width=5,
        background_fill=(0, 0, 0, 74),
        background_padding_x=24,
        background_padding_y=14,
    ),
    "pro_cyan_phrase": TextStylePreset(
        name="pro_cyan_phrase",
        base_font_size=60,
        min_font_size=44,
        active_fill=(89, 231, 255, 255),
        inactive_fill=(248, 248, 246, 236),
        future_fill=(232, 232, 228, 172),
        stroke_width=5,
        background_fill=(0, 0, 0, 58),
        background_padding_x=22,
        background_padding_y=12,
    ),
    "minimal_documentary": TextStylePreset(
        name="minimal_documentary",
        base_font_size=52,
        min_font_size=40,
        active_fill=(255, 226, 67, 255),
        inactive_fill=(246, 246, 242, 232),
        future_fill=(226, 226, 220, 164),
        stroke_width=4,
        background_fill=(0, 0, 0, 0),
        background_padding_x=18,
        background_padding_y=10,
        word_gap=14,
        line_gap=10,
    ),
}


@dataclass(frozen=True)
class AvoidanceZone:
    name: str
    box: Box
    priority: int = 50


@dataclass(frozen=True)
class CaptionWordBox:
    word: str
    box: Box
    line_index: int
    word_index: int
    active: bool = False
    emphasis: bool = False


@dataclass(frozen=True)
class CaptionLayout:
    text_lines: list[str]
    word_boxes: list[CaptionWordBox]
    full_caption_box: Box
    background_box: Box
    anchor_point: tuple[int, int]
    final_position: tuple[int, int]
    font_size: int
    style_preset: str
    hidden: bool = False
    collision_warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "text_lines": self.text_lines,
            "word_boxes": [
                {
                    "word": item.word,
                    "box": list(item.box),
                    "line_index": item.line_index,
                    "word_index": item.word_index,
                    "active": item.active,
                    "emphasis": item.emphasis,
                }
                for item in self.word_boxes
            ],
            "full_caption_box": list(self.full_caption_box),
            "background_box": list(self.background_box),
            "anchor_point": list(self.anchor_point),
            "final_position": list(self.final_position),
            "font_size": self.font_size,
            "style_preset": self.style_preset,
            "hidden": self.hidden,
            "collision_warnings": self.collision_warnings,
        }


def layout_caption_block(
    draw: ImageDraw.ImageDraw,
    words: list[dict[str, Any]] | list[str],
    active_word_index: int = -1,
    style_preset: str = "pro_yellow_word",
    scene_role: str = "detail",
    frame_size: tuple[int, int] = REEL_SIZE,
    safe_zones: CaptionSafeZones | None = None,
    avoidance_zones: list[AvoidanceZone] | None = None,
    priority: int = 40,
) -> CaptionLayout:
    """Layout a single caption block from final wrapped text geometry."""

    safe = safe_zones or CaptionSafeZones()
    style = STYLE_PRESETS.get(style_preset, STYLE_PRESETS["pro_yellow_word"])
    normalized_words = _normalize_words(words)
    if not normalized_words:
        return _empty_layout(style.name)

    frame_w, frame_h = frame_size
    max_width = frame_w - (safe.side + style.background_padding_x + style.stroke_width) * 2
    selected_font_size = style.base_font_size
    selected_lines: list[list[dict[str, Any]]] = []
    for font_size in range(style.base_font_size, style.min_font_size - 1, -2):
        font = load_font(size=font_size, bold=True, warnings=[])
        lines = _wrap_words(draw, normalized_words, font, max_width, style.word_gap)
        if len(lines) <= 2:
            selected_font_size = font_size
            selected_lines = lines
            break
    if not selected_lines:
        selected_font_size = style.min_font_size
        selected_lines = _wrap_words(
            draw,
            normalized_words,
            load_font(size=selected_font_size, bold=True, warnings=[]),
            max_width,
            style.word_gap,
        )[:2]

    font = load_font(size=selected_font_size, bold=True, warnings=[])
    line_height = text_size(draw, "HIGHLIGHT", font)[1]
    line_widths = [_line_width(draw, line, font, style.word_gap) for line in selected_lines]
    block_width = max(line_widths) if line_widths else 0
    block_height = len(selected_lines) * line_height + max(0, len(selected_lines) - 1) * style.line_gap
    preferred_center = (safe.caption_preferred_min_y + safe.caption_preferred_max_y) // 2
    if scene_role == "hook_title":
        preferred_center = safe.hook_preferred_y

    candidate_tops = _candidate_tops(
        preferred_center=preferred_center,
        block_height=block_height,
        frame_height=frame_h,
        safe=safe,
        scene_role=scene_role,
    )
    warnings: list[str] = []
    avoidance = avoidance_zones or []
    chosen_top = candidate_tops[0]
    hidden = False
    for top in candidate_tops:
        caption_box = _caption_box(frame_w, block_width, block_height, top)
        bg_box = _background_box(caption_box, style, frame_size)
        collisions = [zone for zone in avoidance if boxes_overlap(bg_box, zone.box)]
        if not collisions:
            chosen_top = top
            break
    else:
        collisions = [zone for zone in avoidance if boxes_overlap(_background_box(_caption_box(frame_w, block_width, block_height, chosen_top), style, frame_size), zone.box)]
        if collisions and max(zone.priority for zone in collisions) >= priority:
            hidden = True
            warnings.extend(f"hidden_due_to_{zone.name}" for zone in collisions)
        else:
            warnings.extend(f"collision_with_{zone.name}" for zone in collisions)

    caption_box = _caption_box(frame_w, block_width, block_height, chosen_top)
    background_box = _background_box(caption_box, style, frame_size)
    if not _inside_safe_zone(background_box, frame_size, safe):
        warnings.append("safe_zone_violation")

    word_boxes = _word_boxes(
        draw=draw,
        lines=selected_lines,
        font=font,
        style=style,
        caption_box=caption_box,
        line_widths=line_widths,
        line_height=line_height,
        active_word_index=active_word_index,
    )
    if word_boxes and not all(box_contains(background_box, item.box) for item in word_boxes):
        warnings.append("background_does_not_cover_word_boxes")

    return CaptionLayout(
        text_lines=[" ".join(str(item.get("word", "")).upper() for item in line) for line in selected_lines],
        word_boxes=word_boxes,
        full_caption_box=caption_box,
        background_box=background_box,
        anchor_point=(frame_w // 2, preferred_center),
        final_position=(caption_box[0], caption_box[1]),
        font_size=selected_font_size,
        style_preset=style.name,
        hidden=hidden,
        collision_warnings=warnings,
    )


def hook_title_zone(
    draw: ImageDraw.ImageDraw,
    text: str,
    frame_size: tuple[int, int] = REEL_SIZE,
    safe_zones: CaptionSafeZones | None = None,
) -> AvoidanceZone:
    words = [{"word": word} for word in text.upper().split()[:5]]
    layout = layout_caption_block(
        draw,
        words,
        style_preset="pro_yellow_word",
        scene_role="hook_title",
        frame_size=frame_size,
        safe_zones=safe_zones,
        avoidance_zones=[],
        priority=90,
    )
    return AvoidanceZone("hook_title", layout.background_box, priority=90)


def handle_zone(handle_box: Box | None = None) -> AvoidanceZone:
    return AvoidanceZone("handle", handle_box or (760, 1660, 1010, 1860), priority=80)


def scene_label_zone() -> AvoidanceZone:
    return AvoidanceZone("scene_label", (60, 55, 190, 120), priority=60)


def instagram_bottom_unsafe_zone(frame_size: tuple[int, int] = REEL_SIZE, safe_zones: CaptionSafeZones | None = None) -> AvoidanceZone:
    safe = safe_zones or CaptionSafeZones()
    width, height = frame_size
    return AvoidanceZone("instagram_bottom_unsafe_zone", (0, height - safe.bottom, width, height), priority=100)


def caption_layout_metrics(layouts: list[CaptionLayout]) -> dict[str, Any]:
    visible = [layout for layout in layouts if not layout.hidden]
    warnings = [warning for layout in layouts for warning in layout.collision_warnings]
    collision_count = sum(1 for warning in warnings if warning.startswith("collision_with_"))
    safe_violations = sum(1 for warning in warnings if warning == "safe_zone_violation")
    alignment_failures = sum(1 for warning in warnings if warning == "background_does_not_cover_word_boxes")
    hidden_for_collision = sum(1 for warning in warnings if warning.startswith("hidden_due_to_"))
    background_alignment_score = max(0, 100 - alignment_failures * 30)
    safe_zone_score = max(0, 100 - safe_violations * 25)
    layout_score = max(0, min(100, round(96 - collision_count * 35 - safe_violations * 20 - alignment_failures * 25)))
    return {
        "caption_layout_score": layout_score,
        "caption_collision_count": collision_count,
        "caption_background_alignment_score": background_alignment_score,
        "caption_safe_zone_score": safe_zone_score,
        "active_highlight_layout_stability_score": 100,
        "duplicate_text_layer_detected": False,
        "caption_layout_hidden_collision_count": hidden_for_collision,
        "caption_layout_warning_count": len(warnings),
        "caption_layout_sample_count": len(layouts),
        "caption_visible_sample_count": len(visible),
    }


def boxes_overlap(first: Box, second: Box) -> bool:
    return first[0] < second[2] and first[2] > second[0] and first[1] < second[3] and first[3] > second[1]


def box_contains(outer: Box, inner: Box) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def _normalize_words(words: list[dict[str, Any]] | list[str]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in words:
        if isinstance(item, dict):
            word = str(item.get("word", "")).strip()
            if word:
                normalized.append({**item, "word": word.upper()})
        else:
            word = str(item).strip()
            if word:
                normalized.append({"word": word.upper()})
    return normalized


def _wrap_words(
    draw: ImageDraw.ImageDraw,
    words: list[dict[str, Any]],
    font,
    max_width: int,
    word_gap: int,
) -> list[list[dict[str, Any]]]:
    lines: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_width = 0
    for word in words:
        width = text_size(draw, str(word.get("word", "")), font)[0]
        next_width = width if not current else current_width + word_gap + width
        if current and next_width > max_width:
            lines.append(current)
            current = [word]
            current_width = width
        else:
            current.append(word)
            current_width = next_width
    if current:
        lines.append(current)
    return lines


def _line_width(draw: ImageDraw.ImageDraw, line: list[dict[str, Any]], font, word_gap: int) -> int:
    if not line:
        return 0
    return sum(text_size(draw, str(item.get("word", "")), font)[0] for item in line) + word_gap * (len(line) - 1)


def _candidate_tops(
    preferred_center: int,
    block_height: int,
    frame_height: int,
    safe: CaptionSafeZones,
    scene_role: str,
) -> list[int]:
    centers = [preferred_center]
    if scene_role == "hook_title":
        centers.extend([690, 850, 610])
    else:
        centers.extend([1260, 1430, 1120, 980])
    top_min = safe.top
    top_max = frame_height - safe.bottom - block_height
    tops: list[int] = []
    for center in centers:
        top = max(top_min, min(top_max, int(center - block_height / 2)))
        if top not in tops:
            tops.append(top)
    return tops or [top_min]


def _caption_box(frame_width: int, block_width: int, block_height: int, top: int) -> Box:
    left = int((frame_width - block_width) / 2)
    return (left, top, left + block_width, top + block_height)


def _background_box(caption_box: Box, style: TextStylePreset, frame_size: tuple[int, int]) -> Box:
    width, height = frame_size
    pad_x = style.background_padding_x + style.stroke_width
    pad_y = style.background_padding_y + style.stroke_width
    return (
        max(0, caption_box[0] - pad_x),
        max(0, caption_box[1] - pad_y),
        min(width, caption_box[2] + pad_x),
        min(height, caption_box[3] + pad_y),
    )


def _inside_safe_zone(box: Box, frame_size: tuple[int, int], safe: CaptionSafeZones) -> bool:
    width, height = frame_size
    return box[0] >= safe.side and box[2] <= width - safe.side and box[1] >= safe.top and box[3] <= height - safe.bottom


def _word_boxes(
    draw: ImageDraw.ImageDraw,
    lines: list[list[dict[str, Any]]],
    font,
    style: TextStylePreset,
    caption_box: Box,
    line_widths: list[int],
    line_height: int,
    active_word_index: int,
) -> list[CaptionWordBox]:
    boxes: list[CaptionWordBox] = []
    cursor_index = 0
    y = caption_box[1]
    for line_index, line in enumerate(lines):
        x = int(caption_box[0] + ((caption_box[2] - caption_box[0]) - line_widths[line_index]) / 2)
        for word in line:
            text = str(word.get("word", ""))
            width = text_size(draw, text, font)[0]
            boxes.append(
                CaptionWordBox(
                    word=text,
                    box=(x, y, x + width, y + line_height),
                    line_index=line_index,
                    word_index=cursor_index,
                    active=cursor_index == active_word_index,
                    emphasis=bool(word.get("emphasis", False)),
                )
            )
            x += width + style.word_gap
            cursor_index += 1
        y += line_height + style.line_gap
    return boxes


def _empty_layout(style_preset: str) -> CaptionLayout:
    return CaptionLayout(
        text_lines=[],
        word_boxes=[],
        full_caption_box=(0, 0, 0, 0),
        background_box=(0, 0, 0, 0),
        anchor_point=(0, 0),
        final_position=(0, 0),
        font_size=0,
        style_preset=style_preset,
        hidden=True,
        collision_warnings=["empty_caption"],
    )
