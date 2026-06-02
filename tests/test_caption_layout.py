from __future__ import annotations

import unittest

from PIL import Image, ImageDraw

from app.render.caption_layout import (
    AvoidanceZone,
    CaptionSafeZones,
    box_contains,
    boxes_overlap,
    caption_layout_metrics,
    hook_title_zone,
    instagram_bottom_unsafe_zone,
    layout_caption_block,
)


class CaptionLayoutEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.image = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def test_one_line_caption_background_aligns_with_text_bbox(self) -> None:
        layout = layout_caption_block(self.draw, ["THE", "MOON", "VANISHES"])

        self.assertFalse(layout.hidden)
        self.assertEqual(len(layout.text_lines), 1)
        self.assertTrue(all(box_contains(layout.background_box, word.box) for word in layout.word_boxes))
        self.assertNotIn("background_does_not_cover_word_boxes", layout.collision_warnings)

    def test_two_line_caption_background_covers_both_lines(self) -> None:
        layout = layout_caption_block(
            self.draw,
            ["WHAT", "HAPPENS", "WHEN", "THE", "MOON", "DISAPPEARS", "FOREVER"],
        )

        self.assertFalse(layout.hidden)
        self.assertEqual(len(layout.text_lines), 2)
        self.assertTrue(all(box_contains(layout.background_box, word.box) for word in layout.word_boxes))

    def test_active_word_highlight_does_not_shift_layout(self) -> None:
        words = ["OCEANS", "LOSE", "THEIR", "RHYTHM"]
        first = layout_caption_block(self.draw, words, active_word_index=0)
        third = layout_caption_block(self.draw, words, active_word_index=2)

        self.assertEqual(first.full_caption_box, third.full_caption_box)
        self.assertEqual(first.background_box, third.background_box)
        self.assertEqual([word.box for word in first.word_boxes], [word.box for word in third.word_boxes])

    def test_background_covers_all_word_boxes(self) -> None:
        layout = layout_caption_block(self.draw, ["TIDES", "SURGE"], active_word_index=1)

        for word in layout.word_boxes:
            self.assertTrue(box_contains(layout.background_box, word.box))

    def test_hook_and_caption_do_not_overlap(self) -> None:
        hook = hook_title_zone(self.draw, "THE MOON VANISHES")
        layout = layout_caption_block(
            self.draw,
            ["WHAT", "IF", "THE", "MOON"],
            avoidance_zones=[hook],
        )

        self.assertTrue(layout.hidden or not boxes_overlap(layout.background_box, hook.box))
        self.assertEqual(caption_layout_metrics([layout])["caption_collision_count"], 0)

    def test_bottom_safe_zone_is_respected(self) -> None:
        layout = layout_caption_block(
            self.draw,
            ["WHERE", "WOULD", "YOU", "LOOK", "FIRST"],
            safe_zones=CaptionSafeZones(caption_preferred_min_y=1700, caption_preferred_max_y=1800),
            avoidance_zones=[instagram_bottom_unsafe_zone()],
        )

        self.assertLessEqual(layout.background_box[3], 1920 - 260)
        self.assertFalse(boxes_overlap(layout.background_box, instagram_bottom_unsafe_zone().box))

    def test_unresolved_collision_is_reported(self) -> None:
        zone = AvoidanceZone("full_frame", (0, 0, 1080, 1920), priority=10)
        layout = layout_caption_block(self.draw, ["CAN", "NOT", "MOVE"], avoidance_zones=[zone], priority=90)

        self.assertIn("collision_with_full_frame", layout.collision_warnings)
        self.assertEqual(caption_layout_metrics([layout])["caption_collision_count"], 1)


if __name__ == "__main__":
    unittest.main()
