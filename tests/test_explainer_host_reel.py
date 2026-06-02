from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.content.explainer_planner import plan_explainer_host_reel
from app.content.explainer_schemas import explainer_plan_to_carousel_plan, explainer_plan_to_reel_plan
from app.host.host_profile import load_host_profile
from app.main import build_parser
from app.media.media_item import MediaItem
from app.media.media_planner import create_media_plan
from app.quality.explainer_quality import run_explainer_quality_gate
from app.render.explainer_host_reel_renderer import export_explainer_host_reel


class ExplainerHostReelTests(unittest.TestCase):
    def test_explainer_host_reel_template_is_accepted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "generate",
                "--topic",
                "What is the relationship between oil prices and the dollar?",
                "--niche",
                "economy",
                "--slides",
                "5",
                "--template",
                "explainer_host_reel",
                "--voiceover",
            ]
        )

        self.assertEqual(args.template, "explainer_host_reel")
        self.assertTrue(args.voiceover)

    def test_host_profile_loads(self) -> None:
        host = load_host_profile()

        self.assertEqual(host.host_id, "nova")
        self.assertIn("fictional", host.role.lower())
        self.assertIn("celebrity", host.negative_prompt.lower())

    def test_explainer_plan_validates_and_bridges(self) -> None:
        host = load_host_profile()
        plan = plan_explainer_host_reel("What is the relationship between oil prices and the dollar?", "economy", host)
        reel_plan = explainer_plan_to_reel_plan(plan)
        carousel_plan = explainer_plan_to_carousel_plan(plan)

        self.assertEqual(len(plan.scenes), 5)
        self.assertEqual(sum(1 for scene in plan.scenes if scene.visual_type == "host_ai"), 2)
        self.assertEqual(carousel_plan.selected_pattern, "explainer_host_reel")
        self.assertIn("not financial advice", " ".join([plan.caption, *plan.caveats]).lower())
        self.assertIn("indirect", reel_plan.voiceover_script.lower())

    def test_missing_media_api_keys_do_not_crash(self) -> None:
        host = load_host_profile()
        plan = plan_explainer_host_reel("What is the relationship between oil prices and the dollar?", "economy", host)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.dict("os.environ", {"PEXELS_API_KEY": "", "UNSPLASH_ACCESS_KEY": ""}, clear=False):
                media_plan = create_media_plan(plan, root, root / "raw_images")

            self.assertTrue((root / "media_plan.json").exists())
            self.assertTrue((root / "media_selection_report.json").exists())
            self.assertTrue((root / "media_attribution.json").exists())
            self.assertIn("chart", media_plan["media_sources_used"])

    def test_media_attribution_metadata_created_for_external_media(self) -> None:
        host = load_host_profile()
        plan = plan_explainer_host_reel("What is the relationship between oil prices and the dollar?", "economy", host)
        fake_item = MediaItem(
            provider="wikimedia",
            media_type="wikimedia_image",
            title="Oil barrels",
            download_url="",
            width=1600,
            height=2200,
            author="Example Author",
            license="Creative Commons",
            attribution="Oil barrels by Example Author",
            relevance_score=95,
            vertical_usability_score=95,
            license_safety_score=95,
            visual_clarity_score=95,
            source_trust_score=95,
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            Image.new("RGB", (1080, 1920), (40, 50, 60)).save(root / "external.jpg")

            def fake_download(item, output_path):
                Image.open(root / "external.jpg").save(output_path)
                return item.model_copy(update={"local_path": str(output_path)})

            with patch("app.media.pexels_provider.PexelsProvider.search", return_value=[]), patch(
                "app.media.unsplash_provider.UnsplashProvider.search",
                return_value=[],
            ), patch("app.media.wikimedia_provider.WikimediaProvider.search", return_value=[fake_item]), patch(
                "app.media.media_planner.download_media_item",
                side_effect=fake_download,
            ):
                media_plan = create_media_plan(plan, root, root / "raw_images")

            attribution_text = (root / "media_attribution.json").read_text(encoding="utf-8")
            self.assertTrue(media_plan["external_media_used"])
            self.assertIn("Example Author", attribution_text)

    def test_explainer_renderer_disables_old_subtitle_duplication(self) -> None:
        host = load_host_profile()
        plan = plan_explainer_host_reel("What is the relationship between oil prices and the dollar?", "economy", host)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_dir = root / "raw_images"
            raw_dir.mkdir()
            for index in range(1, 6):
                Image.new("RGB", (1080, 1920), (30 + index * 20, 45, 65)).save(raw_dir / f"slide_{index:02d}.jpg")
            with patch("app.render.explainer_host_reel_renderer.get_ffmpeg_path", return_value=None):
                result = export_explainer_host_reel(plan, raw_dir, root)

            self.assertEqual(len(result.frame_paths), 5)
            for frame_path in result.frame_paths:
                with Image.open(frame_path) as frame:
                    self.assertEqual(frame.size, (1080, 1920))

    def test_quality_gate_blocks_caption_collision(self) -> None:
        host = load_host_profile()
        plan = plan_explainer_host_reel("What is the relationship between oil prices and the dollar?", "economy", host)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frames = root / "final_reel" / "frames"
            frames.mkdir(parents=True)
            for index in range(1, 6):
                Image.new("RGB", (1080, 1920), (50, 70, 90)).save(frames / f"frame_{index:02d}.jpg")
            (root / "media_plan.json").write_text('{"scenes":[]}', encoding="utf-8")
            (root / "media_attribution.json").write_text('{"external_media_used":false,"missing_attribution_count":0}', encoding="utf-8")

            report = run_explainer_quality_gate(
                root,
                plan,
                {
                    "voiceover": {"caption_sync_score": 90, "caption_layout_score": 90, "caption_collision_count": 1},
                    "explainer_reel_render": {"professional_edit_score": 88},
                },
                voiceover_requested=True,
            )

        self.assertFalse(report["quality_gate_passed"])
        self.assertIn("caption collision", report["blocking_issues"][0])


if __name__ == "__main__":
    unittest.main()
