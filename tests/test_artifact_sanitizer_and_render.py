from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw, ImageStat

from app.content.schemas import CarouselPlan, CarouselSlide
from app.image.prompt_builder import build_image_prompt
from app.image.quality import score_candidate
from app.image.sanitizer import (
    bottom_artifact_suspicion,
    protect_bottom_band,
    sanitize_post_images,
    sanitizer_visual_damage_risk,
    targeted_sanitizer_area_ratio,
)
from app.render.carousel_renderer import CarouselRenderer
from app.render.reel_exporter import export_reel_package


def make_slide(slide_number: int = 1) -> CarouselSlide:
    return CarouselSlide(
        slide_number=slide_number,
        role="hook" if slide_number == 1 else "CTA",
        tag="SCIENCE",
        headline="OCEANS ROSE OVERNIGHT",
        subtext="The street becomes a shoreline.",
        visual_goal="Show a flooded city street with clean dark lower space.",
        image_prompt="cinematic realistic flooded city street, vertical composition, text-safe negative space, no text",
        text_position="bottom_left",
        composition_hint="leave dark negative space in the lower third for text",
        fact_claim="",
        needs_fact_check=False,
    )


def make_plan() -> CarouselPlan:
    return CarouselPlan(
        topic="Test topic",
        niche="science",
        title="Test topic",
        selected_pattern="POV Survival",
        content_angle="A simple test angle.",
        target_audience="Curious readers",
        tone="cinematic",
        caption=(
            "A sudden flood changes the street in seconds and forces every choice to become practical.\n\n"
            "The test keeps the story grounded in one visible scene instead of adding claims.\n\n"
            "It uses the same image pipeline as the real package so artifacts are handled consistently.\n\n"
            "Would you know where to move first?\n\n"
            "Save this for clean science carousel checks."
        ),
        hashtags=["science"],
        slides=[make_slide(1)],
    )


class ArtifactSanitizerRenderTests(unittest.TestCase):
    def test_prompt_builder_enforces_strict_no_text_rule(self) -> None:
        prompt = build_image_prompt(make_slide(), "science").prompt.lower()
        for phrase in ("no text", "no letters", "no words", "no signs", "no watermark", "no ui", "clean image only"):
            self.assertIn(phrase, prompt)

    def test_synthetic_bottom_gibberish_band_is_sanitized(self) -> None:
        image = Image.new("RGB", (686, 858), (72, 91, 104))
        draw = ImageDraw.Draw(image)
        for index in range(8):
            draw.text((80, 675 + index * 18), "AXT L0REM WTRMRK ###", fill=(238, 238, 230))

        suspicion, _ = bottom_artifact_suspicion(image)
        cleaned = protect_bottom_band(image)
        before = ImageStat.Stat(image.crop((0, 650, 686, 858)).convert("L")).mean[0]
        after = ImageStat.Stat(cleaned.crop((0, 650, 686, 858)).convert("L")).mean[0]

        self.assertGreaterEqual(suspicion, 40.0)
        self.assertLess(after, before)
        self.assertLessEqual(targeted_sanitizer_area_ratio(cleaned), 0.20)
        self.assertEqual(sanitizer_visual_damage_risk(targeted_sanitizer_area_ratio(cleaned)), "medium")

    def test_intentional_rendered_overlay_text_is_not_raw_artifact_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "clean.jpg"
            image = Image.new("RGB", (686, 858), (44, 55, 61))
            draw = ImageDraw.Draw(image)
            draw.rectangle((80, 90, 610, 500), fill=(65, 78, 82))
            image.save(path)

            score = score_candidate(path, make_slide(), "cinematic no text text-safe", "science")

        self.assertFalse(score.high_artifact_risk)
        self.assertLess(score.artifact_risk_score, 70.0)

    def test_renderer_prefers_sanitized_image_when_available(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_dir = root / "raw_images"
            sanitized_dir = root / "sanitized_images"
            final_dir = root / "final_slides"
            raw_dir.mkdir()
            sanitized_dir.mkdir()
            Image.new("RGB", (686, 858), (190, 20, 20)).save(raw_dir / "slide_01.jpg")
            Image.new("RGB", (686, 858), (20, 150, 70)).save(sanitized_dir / "slide_01.jpg")

            CarouselRenderer().render_plan(make_plan(), raw_dir, final_dir, sanitized_dir=sanitized_dir)
            rendered = Image.open(final_dir / "slide_01.jpg").convert("RGB")
            sample = ImageStat.Stat(rendered.crop((400, 250, 650, 500))).mean

        self.assertGreater(sample[1], sample[0])

    def test_reel_cover_is_vertical_full_size(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_dir = root / "raw_images"
            final_dir = root / "final_slides"
            raw_dir.mkdir()
            final_dir.mkdir()
            Image.new("RGB", (686, 858), (40, 70, 95)).save(raw_dir / "slide_01.jpg")

            result = export_reel_package(make_plan(), final_dir=final_dir, raw_dir=raw_dir, output_dir=root, duration_seconds=1)
            with Image.open(result.cover_path) as cover:
                cover_size = cover.size

        self.assertEqual(cover_size, (1080, 1920))

    def test_sanitize_post_images_writes_sanitized_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_dir = root / "raw_images"
            sanitized_dir = root / "sanitized_images"
            raw_dir.mkdir()
            image = Image.new("RGB", (686, 858), (72, 91, 104))
            draw = ImageDraw.Draw(image)
            for index in range(8):
                draw.text((80, 675 + index * 18), "AXT L0REM WTRMRK ###", fill=(238, 238, 230))
            image.save(raw_dir / "slide_01.jpg")

            report = sanitize_post_images(make_plan(), raw_dir=raw_dir, sanitized_dir=sanitized_dir)

        self.assertTrue(report["sanitized_images_used"])
        self.assertIn("slide_01", report["sanitized_slides"])
        self.assertLessEqual(report["sanitizer_area_ratio"], 0.20)
        self.assertIn(report["sanitizer_visual_damage_risk"], {"low", "medium"})
        self.assertEqual(report["sanitizer_mode"], "targeted")
        self.assertFalse(report["sanitizer_heavy_default"])

    def test_large_area_sanitizer_ratio_is_high_damage(self) -> None:
        self.assertEqual(sanitizer_visual_damage_risk(0.26), "high")


if __name__ == "__main__":
    unittest.main()
