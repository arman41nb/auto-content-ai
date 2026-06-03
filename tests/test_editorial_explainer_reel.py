from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image, ImageChops

from app.content.explainer_planner import plan_editorial_explainer_reel
from app.content.explainer_schemas import explainer_plan_to_carousel_plan, explainer_plan_to_reel_plan
from app.main import build_explainer_scene_image_prompt, generate_or_select_images
from app.media.media_item import MediaItem
from app.media.media_planner import create_media_plan
from app.media.media_ranker import rank_media_items
from app.quality.explainer_quality import run_explainer_quality_gate
from app.render.explainer_host_reel_renderer import export_explainer_host_reel, render_explainer_final_slides


class EditorialExplainerReelTests(unittest.TestCase):
    def test_editorial_plan_is_hostless_and_bridges(self) -> None:
        plan = plan_editorial_explainer_reel("What is the relationship between oil prices and the dollar?", "economy")
        reel_plan = explainer_plan_to_reel_plan(plan)
        carousel_plan = explainer_plan_to_carousel_plan(plan)
        text = " ".join(
            [plan.caption, plan.voiceover_script, *[scene.visual_goal for scene in plan.scenes]]
        ).lower()

        self.assertEqual(len(plan.scenes), 5)
        self.assertNotIn("host_ai", {scene.visual_type for scene in plan.scenes})
        self.assertNotIn("mascot", text)
        self.assertNotIn("fictional host", text)
        self.assertEqual(carousel_plan.selected_pattern, "editorial_explainer_reel")
        self.assertIn("indirect", reel_plan.voiceover_script.lower())

    def test_pexels_is_attempted_and_selected_before_fallback(self) -> None:
        plan = plan_editorial_explainer_reel("What is the relationship between oil prices and the dollar?", "economy")
        fake_item = MediaItem(
            provider="pexels",
            media_type="stock_photo",
            title="Oil tanker fuel logistics energy infrastructure vertical export terminal",
            download_url="https://example.com/tanker.jpg",
            width=1600,
            height=2400,
            author="Example Photographer",
            license="Pexels License",
            attribution="Photo by Example Photographer on Pexels",
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.jpg"
            Image.new("RGB", (1080, 1920), (60, 90, 110)).save(source)

            def fake_download(item: MediaItem, output_path: Path) -> MediaItem:
                Image.open(source).save(output_path)
                return item.model_copy(update={"local_path": str(output_path), "width": 1080, "height": 1920})

            with patch("app.media.pexels_provider.PexelsProvider.search", return_value=[fake_item]), patch(
                "app.media.media_planner.download_media_item",
                side_effect=fake_download,
            ):
                media_plan = create_media_plan(plan, root, root / "raw_images", template="editorial_explainer_reel")

        first_scene = media_plan["scenes"][0]
        self.assertTrue(media_plan["pexels_first_policy_active"])
        self.assertTrue(first_scene["pexels_attempted"])
        self.assertEqual(first_scene["selected_source_type"], "pexels")
        self.assertEqual(first_scene["selected_priority"], 1)

    def test_infographic_and_ai_fallbacks_log_pexels_failure(self) -> None:
        plan = plan_editorial_explainer_reel("What is the relationship between oil prices and the dollar?", "economy")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch("app.media.pexels_provider.PexelsProvider.search", return_value=[]):
                media_plan = create_media_plan(plan, root, root / "raw_images", template="editorial_explainer_reel")

            mechanism = media_plan["scenes"][2]
            stock_scene = media_plan["scenes"][0]

            self.assertEqual(mechanism["selected_source_type"], "premium_infographic")
            self.assertTrue(Path(mechanism["selected"]["local_path"]).exists())
            self.assertEqual(stock_scene["selected_source_type"], "ai_generated")
            self.assertIn("Pexels returned no strong", stock_scene["why_ai_fallback_was_needed"])

    def test_final_frames_are_exact_copies_of_final_slides(self) -> None:
        plan = plan_editorial_explainer_reel("What is the relationship between oil prices and the dollar?", "economy")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_dir = root / "raw_images"
            raw_dir.mkdir()
            for index in range(1, 6):
                Image.new("RGB", (1080, 1920), (40 + index * 20, 70, 100)).save(raw_dir / f"slide_{index:02d}.jpg")
            final_paths = render_explainer_final_slides(plan, raw_dir, root)

            with patch("app.render.explainer_host_reel_renderer.get_ffmpeg_path", return_value=None):
                result = export_explainer_host_reel(plan, root / "final_slides", root)

            self.assertEqual(len(final_paths), 5)
            self.assertTrue(result.metadata["final_frames_match_final_slides"])
            for index in range(1, 6):
                final_path = root / "final_slides" / f"slide_{index:02d}.jpg"
                frame_path = root / "final_reel" / "frames" / f"frame_{index:02d}.jpg"
                with Image.open(final_path) as final_image, Image.open(frame_path) as frame_image:
                    self.assertIsNone(ImageChops.difference(final_image, frame_image).getbbox())

    def test_quality_gate_blocks_when_pexels_was_not_attempted(self) -> None:
        plan = plan_editorial_explainer_reel("What is the relationship between oil prices and the dollar?", "economy")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frames = root / "final_reel" / "frames"
            final = root / "final_slides"
            frames.mkdir(parents=True)
            final.mkdir()
            for index in range(1, 6):
                image = Image.new("RGB", (1080, 1920), (50, 70, 90))
                image.save(final / f"slide_{index:02d}.jpg")
                image.save(frames / f"frame_{index:02d}.jpg")
            (root / "media_plan.json").write_text(
                '{"pexels_first_policy_active":false,"scenes":[]}',
                encoding="utf-8",
            )
            (root / "media_attribution.json").write_text(
                '{"external_media_used":false,"missing_attribution_count":0}',
                encoding="utf-8",
            )

            report = run_explainer_quality_gate(root, plan, {"voiceover": {}}, voiceover_requested=False)

        self.assertFalse(report["quality_gate_passed"])
        self.assertTrue(any("Pexels-first" in issue for issue in report["blocking_issues"]))

    def test_retired_character_implementation_files_are_removed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        retired_patterns = [
            "app/mascot/*.py",
            "app/host/*.py",
            "app/content/mascot_story_*.py",
            "app/content/hybrid_story_*.py",
            "app/render/mascot_story_*.py",
            "app/render/hybrid_story_*.py",
            "app/quality/mascot_story_*.py",
            "app/quality/hybrid_story_*.py",
            "app/media/hybrid_media_*.py",
        ]

        remaining = [str(path.relative_to(root)) for pattern in retired_patterns for path in root.glob(pattern)]

        self.assertEqual(remaining, [])

    def test_media_plan_asset_is_not_overwritten_by_ai_selection(self) -> None:
        plan = plan_editorial_explainer_reel("What is the relationship between oil prices and the dollar?", "economy")
        carousel_plan = explainer_plan_to_carousel_plan(plan)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_dir = root / "raw_images"
            raw_dir.mkdir()
            raw_paths = []
            before: dict[Path, bytes] = {}
            for index in range(1, 6):
                raw_path = raw_dir / f"slide_{index:02d}.jpg"
                Image.new("RGB", (1080, 1920), (10 + index, 40, 70)).save(raw_path)
                raw_paths.append(raw_path)
                before[raw_path] = raw_path.read_bytes()
            args = SimpleNamespace(
                template="editorial_explainer_reel",
                resume=False,
                image_variants=2,
                media_plan_info={
                    "scenes": [
                        {
                            "scene_number": index,
                            "selected_source_type": "pexels",
                            "scene_intent": "Oil logistics establishing shot.",
                            "why_selected": "Pexels candidate passed.",
                        }
                        for index in range(1, 6)
                    ]
                },
            )
            image_client = SimpleNamespace(generate_image=lambda *_args, **_kwargs: self.fail("AI generation should not run."))

            report = generate_or_select_images(args, carousel_plan, raw_dir, "economy", image_client, set())
            for raw_path in raw_paths:
                self.assertEqual(raw_path.read_bytes(), before[raw_path])
            self.assertEqual(report["slides"][0]["selected_source_type"], "pexels")
            self.assertEqual(report["slides"][0]["selected_variant"], "slide_01.jpg")

    def test_ai_fallback_generation_uses_logged_strict_prompt(self) -> None:
        args = SimpleNamespace(
            media_plan_info={
                "scenes": [
                    {
                        "scene_number": 1,
                        "ai_generation_required": True,
                        "generated_ai_prompt": "photorealistic or premium editorial infographic style only; avoid readable fake documents",
                    }
                ]
            }
        )

        prompt = build_explainer_scene_image_prompt(args, "generic visual", 1)

        self.assertIn("photorealistic or premium editorial infographic style only", prompt)
        self.assertIn("avoid readable fake documents", prompt)

    def test_quality_gate_rejects_primitive_graphics_and_fake_text_risk(self) -> None:
        plan = plan_editorial_explainer_reel("What is the relationship between oil prices and the dollar?", "economy")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            frames = root / "final_reel" / "frames"
            final = root / "final_slides"
            frames.mkdir(parents=True)
            final.mkdir()
            for index in range(1, 6):
                image = Image.new("RGB", (1080, 1920), (50 + index * 8, 70, 90))
                image.save(final / f"slide_{index:02d}.jpg")
                image.save(frames / f"frame_{index:02d}.jpg")
            scenes = [
                {
                    "scene_number": index,
                    "pexels_attempted": True,
                    "selected": {
                        "provider": "pexels",
                        "media_type": "stock_photo",
                        "relevance_score": 86,
                    },
                }
                for index in range(1, 6)
            ]
            scenes[0]["selected"] = {"provider": "primitive_debug", "media_type": "debug_primitive_visual", "relevance_score": 30}
            scenes[1]["generated_ai_prompt"] = "real invoice document with readable fake text"
            scenes[2]["caption_safe_zone_compatible"] = False
            (root / "media_plan.json").write_text(
                json.dumps({"pexels_first_policy_active": True, "scenes": scenes}),
                encoding="utf-8",
            )
            (root / "media_attribution.json").write_text(
                '{"external_media_used":false,"missing_attribution_count":0}',
                encoding="utf-8",
            )

            report = run_explainer_quality_gate(root, plan, {"voiceover": {}}, voiceover_requested=False)

        self.assertIn(1, report["primitive_scene_numbers"])
        self.assertIn(2, report["fake_text_risk_scene_numbers"])
        self.assertIn(3, report["caption_safe_zone_failure_numbers"])
        self.assertFalse(report["quality_gate_passed"])

    def test_media_ranker_rewards_real_world_relevance_and_vertical_crop(self) -> None:
        relevant = MediaItem(provider="pexels", media_type="stock_photo", title="oil tanker refinery fuel logistics vertical", width=1400, height=2400)
        generic = MediaItem(provider="pexels", media_type="stock_photo", title="empty office chair", width=2400, height=1000)

        ranked = rank_media_items([generic, relevant], "oil tanker fuel logistics")

        self.assertEqual(ranked[0].title, relevant.title)
        self.assertGreaterEqual(ranked[0].vertical_usability_score, 90)


if __name__ == "__main__":
    unittest.main()
