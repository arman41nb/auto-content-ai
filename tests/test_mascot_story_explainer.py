from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.content.mascot_story_planner import plan_mascot_story_reel
from app.content.mascot_story_schemas import mascot_story_plan_to_carousel_plan
from app.main import build_mascot_story_scene_image_prompt, build_parser
from app.mascot.mascot_profile import load_mascot_profile
from app.media.media_planner import create_media_plan
from app.media.visual_fallbacks import create_scene_fallback
from app.quality.mascot_story_quality import run_mascot_story_quality_gate


class MascotStoryExplainerTests(unittest.TestCase):
    def test_mascot_profile_loads(self) -> None:
        mascot = load_mascot_profile("miko")

        self.assertEqual(mascot.mascot_id, "miko")
        self.assertIn("fox-like robot", mascot.species_type)
        self.assertIn("human presenter", mascot.negative_prompt)

    def test_mascot_story_explainer_template_accepted(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "generate",
                "--topic",
                "What is the relationship between oil prices and the dollar?",
                "--niche",
                "economy",
                "--slides",
                "8",
                "--template",
                "mascot_story_explainer",
                "--mascot",
                "miko",
                "--media-sources",
                "mixed",
                "--prefer-video-media",
                "--no-human-host",
            ]
        )

        self.assertEqual(args.template, "mascot_story_explainer")
        self.assertEqual(args.mascot, "miko")
        self.assertTrue(args.no_human_host)

    def test_slides_8_produces_7_to_9_scenes(self) -> None:
        mascot = load_mascot_profile("miko")
        plan = plan_mascot_story_reel("What is the relationship between oil prices and the dollar?", "economy", mascot)

        self.assertGreaterEqual(len(plan.scenes), 7)
        self.assertLessEqual(len(plan.scenes), 9)
        self.assertEqual(len(plan.scenes), 8)
        self.assertGreaterEqual(sum(1 for scene in plan.scenes if scene.visual_type in {"mascot_ai", "mixed"}), 2)

    def test_no_human_host_prevents_human_host_scenes(self) -> None:
        mascot = load_mascot_profile("miko")
        plan = plan_mascot_story_reel("What is the relationship between oil prices and the dollar?", "economy", mascot)
        carousel = mascot_story_plan_to_carousel_plan(plan)

        self.assertNotIn("host_ai", {scene.visual_type for scene in plan.scenes})
        self.assertTrue(all("human presenter" not in slide.visual_goal.lower() for slide in carousel.slides))

    def test_blank_visual_fallback_returns_ai_or_chart_fallback(self) -> None:
        mascot = load_mascot_profile("miko")
        plan = plan_mascot_story_reel("What is the relationship between oil prices and the dollar?", "economy", mascot)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            item = create_scene_fallback(plan.scenes[0], root / "slide_01.jpg", mascot)
            chart = create_scene_fallback(plan.scenes[3], root / "slide_04.jpg", mascot)

            self.assertTrue(Path(item.local_path).exists())
            self.assertIn(item.media_type, {"generated_ai_prompt", "generated_chart_spec"})
            self.assertEqual(chart.media_type, "generated_chart_spec")

    def test_prompt_text_and_role_debug_labels_are_not_visible_in_prompt(self) -> None:
        mascot = load_mascot_profile("miko")
        plan = plan_mascot_story_reel("What is the relationship between oil prices and the dollar?", "economy", mascot)
        prompt = build_mascot_story_scene_image_prompt(
            Namespace(mascot_story_plan=plan, mascot_profile=mascot),
            plan.scenes[0].visual_goal,
            1,
        )

        self.assertNotIn("SETUP", prompt)
        self.assertNotIn("MECHANISM", prompt)
        self.assertIn("no text", prompt.lower())

    def test_all_scenes_have_visual_assets_and_external_flag_truthful(self) -> None:
        mascot = load_mascot_profile("miko")
        plan = plan_mascot_story_reel("What is the relationship between oil prices and the dollar?", "economy", mascot)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.dict("os.environ", {"PEXELS_API_KEY": "", "UNSPLASH_ACCESS_KEY": ""}, clear=False):
                media_plan = create_media_plan(
                    plan,
                    root,
                    root / "raw_images",
                    template="mascot_story_explainer",
                    mascot=mascot,
                    media_sources="mixed",
                    prefer_video_media=True,
                )

            for index in range(1, len(plan.scenes) + 1):
                self.assertTrue((root / "raw_images" / f"slide_{index:02d}.jpg").exists())
            self.assertFalse(media_plan["external_media_used"])

    def test_quality_gate_fails_blank_scene_count(self) -> None:
        mascot = load_mascot_profile("miko")
        plan = plan_mascot_story_reel("What is the relationship between oil prices and the dollar?", "economy", mascot)
        report = _quality_report_with_frames(plan, blank=True, prompt_count=0)

        self.assertFalse(report["quality_gate_passed"])
        self.assertGreater(report["blank_scene_count"], 0)

    def test_quality_gate_fails_prompt_text_visible_count(self) -> None:
        mascot = load_mascot_profile("miko")
        plan = plan_mascot_story_reel("What is the relationship between oil prices and the dollar?", "economy", mascot)
        report = _quality_report_with_frames(plan, blank=False, prompt_count=1)

        self.assertFalse(report["quality_gate_passed"])
        self.assertEqual(report["prompt_text_visible_count"], 1)


def _quality_report_with_frames(plan, blank: bool, prompt_count: int) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        frames = root / "final_reel" / "frames"
        raw = root / "raw_images"
        frames.mkdir(parents=True)
        raw.mkdir()
        color = (0, 0, 0) if blank else (80, 120, 140)
        for index in range(1, len(plan.scenes) + 1):
            Image.new("RGB", (1080, 1920), color).save(frames / f"frame_{index:02d}.jpg")
            Image.new("RGB", (1080, 1920), (90, 120, 150)).save(raw / f"slide_{index:02d}.jpg")
        scenes = [
            {
                "scene_number": scene.scene_number,
                "requested_visual_type": scene.visual_type,
                "selected": {
                    "provider": "fallback",
                    "local_path": str(raw / f"slide_{scene.scene_number:02d}.jpg"),
                    "relevance_score": 85,
                    "visual_clarity_score": 85,
                },
            }
            for scene in plan.scenes
        ]
        (root / "media_plan.json").write_text(
            '{"media_sources_used":["fallback"],"external_media_used":false,"scenes":' + str(scenes).replace("'", '"') + "}",
            encoding="utf-8",
        )
        (root / "media_attribution.json").write_text('{"external_media_used":false,"missing_attribution_count":0}', encoding="utf-8")
        (root / "media_fallback_report.json").write_text('{"missing_api_keys":[]}', encoding="utf-8")

        return run_mascot_story_quality_gate(
            root,
            plan,
            {
                "voiceover": {"caption_sync_score": 90, "caption_layout_score": 90, "caption_collision_count": 0},
                "mascot_story_render": {
                    "professional_edit_score": 90,
                    "infographic_quality_score": 91,
                    "prompt_text_visible_count": prompt_count,
                },
                "mascot_consistency": {"mascot_presence_score": 92, "mascot_consistency_score": 88},
            },
            voiceover_requested=True,
        )


if __name__ == "__main__":
    unittest.main()

