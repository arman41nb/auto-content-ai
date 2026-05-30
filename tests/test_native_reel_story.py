from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.content.reel_schemas import deterministic_ocean_reel_plan, reel_plan_to_carousel_plan
from app.main import build_parser
from app.quality.native_reel_quality import run_native_reel_quality_gate
from app.render.native_reel_renderer import export_native_reel_story


class NativeReelStoryTests(unittest.TestCase):
    def test_deterministic_plan_matches_native_reel_rules(self) -> None:
        reel_plan = deterministic_ocean_reel_plan()

        self.assertEqual(len(reel_plan.scenes), 5)
        self.assertGreaterEqual(sum(scene.duration_seconds for scene in reel_plan.scenes), 8)
        self.assertLessEqual(sum(scene.duration_seconds for scene in reel_plan.scenes), 12)
        self.assertIn("What if oceans rose overnight?", reel_plan.voiceover_script)
        self.assertTrue(all(len(scene.on_screen_text.split()) <= 5 for scene in reel_plan.scenes))

    def test_native_reel_flags_exist_on_auto_and_generate(self) -> None:
        parser = build_parser()

        auto_args = parser.parse_args(
            [
                "auto",
                "--niche",
                "science",
                "--count",
                "1",
                "--template",
                "native_reel_story",
                "--make-reel",
                "--voiceover",
                "--tts-provider",
                "none",
            ]
        )
        generate_args = parser.parse_args(
            [
                "generate",
                "--topic",
                "What if oceans rose overnight?",
                "--niche",
                "science",
                "--slides",
                "5",
                "--template",
                "native_reel_story",
                "--voiceover",
            ]
        )

        self.assertEqual(auto_args.template, "native_reel_story")
        self.assertTrue(auto_args.voiceover)
        self.assertEqual(auto_args.tts_provider, "none")
        self.assertTrue(generate_args.voiceover)

    def test_native_renderer_writes_cover_and_scene_frames(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_dir = root / "raw_images"
            raw_dir.mkdir()
            colors = [(55, 82, 100), (78, 94, 106), (38, 39, 42), (20, 34, 45), (72, 76, 78)]
            for index, color in enumerate(colors, start=1):
                Image.new("RGB", (1080, 1920), color).save(raw_dir / f"slide_{index:02d}.jpg")

            with patch("app.render.native_reel_renderer.get_ffmpeg_path", return_value=None):
                result = export_native_reel_story(deterministic_ocean_reel_plan(), raw_dir, root)

            with Image.open(result.cover_path) as cover:
                cover_size = cover.size
            frame_sizes = []
            for frame_path in result.frame_paths:
                with Image.open(frame_path) as frame:
                    frame_sizes.append(frame.size)

        self.assertEqual(cover_size, (1080, 1920))
        self.assertEqual(frame_sizes, [(1080, 1920)] * 5)

    def test_native_quality_blocks_carousel_paste_without_native_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_dir = root / "raw_images"
            reel_dir = root / "final_reel"
            frames_dir = reel_dir / "frames"
            raw_dir.mkdir()
            frames_dir.mkdir(parents=True)
            for index in range(1, 6):
                Image.new("RGB", (1080, 1920), (30 + index * 20, 45, 65)).save(raw_dir / f"slide_{index:02d}.jpg")
                Image.new("RGB", (1080, 1920), (30 + index * 20, 45, 65)).save(frames_dir / f"frame_{index:02d}.jpg")
            Image.new("RGB", (1080, 1920), (30, 45, 65)).save(reel_dir / "cover.jpg")
            (reel_dir / "reel.mp4").write_bytes(b"fake")

            report = run_native_reel_quality_gate(
                output_dir=root,
                reel_plan=deterministic_ocean_reel_plan(),
                metadata={"reel_export": {"reel_dimensions": [1080, 1920]}, "voiceover": {"script_created": True}},
                voiceover_requested=True,
            )

        self.assertFalse(report["publish_ready"])
        self.assertTrue(report["video_is_carousel_pasted_into_9_16"])

    def test_reel_plan_bridges_to_carousel_for_image_pipeline(self) -> None:
        plan = reel_plan_to_carousel_plan(deterministic_ocean_reel_plan())

        self.assertEqual(len(plan.slides), 5)
        self.assertEqual(plan.slides[0].headline, "THE OCEAN MOVES")
        self.assertEqual(plan.selected_pattern, "native_reel_story")


if __name__ == "__main__":
    unittest.main()
