from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from app.content.mascot_story_planner import plan_mascot_story_reel
from app.content.mascot_story_schemas import mascot_story_plan_to_carousel_plan
from app.main import build_mascot_story_scene_image_prompt, build_parser, main as app_main
from app.mascot.mascot_profile import load_mascot_profile
from app.media.media_planner import create_media_plan
from app.media.visual_fallbacks import create_scene_fallback
from app.quality.candidate_scorer import score_candidate_folder
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
                "--production-visual-minimums",
            ]
        )

        self.assertEqual(args.template, "mascot_story_explainer")
        self.assertEqual(args.mascot, "miko")
        self.assertTrue(args.no_human_host)
        self.assertTrue(args.production_visual_minimums)

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

    def test_production_fallback_schedules_ai_and_premium_chart(self) -> None:
        mascot = load_mascot_profile("miko")
        plan = plan_mascot_story_reel("What is the relationship between oil prices and the dollar?", "economy", mascot)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            item = create_scene_fallback(plan.scenes[0], root / "slide_01.jpg", mascot)
            chart = create_scene_fallback(plan.scenes[3], root / "slide_04.jpg", mascot)

            self.assertFalse(Path(item.local_path).exists())
            self.assertEqual(item.provider, "ai_generated")
            self.assertEqual(item.media_type, "generated_ai_prompt")
            self.assertEqual(chart.provider, "premium_infographic")
            self.assertEqual(chart.media_type, "generated_chart_spec")
            self.assertTrue(Path(chart.local_path).exists())

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
                scene = plan.scenes[index - 1]
                if scene.visual_type == "chart_motion":
                    self.assertTrue((root / "raw_images" / f"slide_{index:02d}.jpg").exists())
            self.assertFalse(media_plan["external_media_used"])
            self.assertNotIn("fallback", media_plan["media_sources_used"])
            self.assertNotIn("ai_fallback", media_plan["media_sources_used"])
            self.assertTrue(any(scene["ai_generation_required"] for scene in media_plan["scenes"]))

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

    def test_primitive_vector_mascot_cannot_pass_production_quality(self) -> None:
        mascot = load_mascot_profile("miko")
        plan = plan_mascot_story_reel("What is the relationship between oil prices and the dollar?", "economy", mascot)
        report = _quality_report_with_frames(plan, blank=False, prompt_count=0, mascot_provider="primitive_debug")

        self.assertFalse(report["quality_gate_passed"])
        self.assertEqual(report["primitive_mascot_risk"], "high")
        self.assertLessEqual(report["viral_readiness_score"], 40)

    def test_placeholder_scene_fails_quality_gate(self) -> None:
        mascot = load_mascot_profile("miko")
        plan = plan_mascot_story_reel("What is the relationship between oil prices and the dollar?", "economy", mascot)
        report = _quality_report_with_frames(plan, blank=False, prompt_count=0, broll_provider="fallback")

        self.assertFalse(report["quality_gate_passed"])
        self.assertEqual(report["placeholder_visual_risk"], "high")

    def test_powerpoint_like_chart_fails_quality_gate(self) -> None:
        mascot = load_mascot_profile("miko")
        plan = plan_mascot_story_reel("What is the relationship between oil prices and the dollar?", "economy", mascot)
        report = _quality_report_with_frames(plan, blank=False, prompt_count=0, chart_provider="chart")

        self.assertFalse(report["quality_gate_passed"])
        self.assertEqual(report["powerpoint_chart_risk"], "high")

    def test_mark_review_command_creates_human_review_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = app_main(
                [
                    "mark-review",
                    "--output-dir",
                    str(root),
                    "--status",
                    "rejected",
                    "--reason",
                    "visual quality unacceptable",
                ]
            )

            self.assertEqual(result, 0)
            self.assertTrue((root / "human_review.json").exists())
            self.assertIn('"do_not_post": true', (root / "human_review.json").read_text(encoding="utf-8"))

    def test_rejected_package_not_treated_as_best_example(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "metadata.json").write_text('{"topic":"x","reel_export":{"created_video":true}}', encoding="utf-8")
            (root / "native_reel_quality_report.json").write_text(
                '{"publish_ready":true,"native_reel_score":95,"first_second_hook_score":95,"scene_variety_score":95,"cover_quality_score":95,"ai_slideshow_risk_score":0,"cover_native_1080x1920":true,"reel_native_1080x1920":true}',
                encoding="utf-8",
            )
            (root / "post_quality_report.json").write_text(
                '{"publish_ready":true,"score":95,"voiceover_audio_stream_present":true}',
                encoding="utf-8",
            )
            (root / "carousel_plan.json").write_text('{"topic":"x","caption":"this is a long enough caption for scoring"}', encoding="utf-8")
            (root / "human_review.json").write_text('{"status":"rejected","do_not_post":true}', encoding="utf-8")

            scored = score_candidate_folder(root, voiceover_requested=False)

            self.assertFalse(scored["publish_ready"])
            self.assertEqual(scored["candidate_score"], 0)
            self.assertTrue(any("human_review=rejected" in warning for warning in scored["warnings"]))


def _quality_report_with_frames(
    plan,
    blank: bool,
    prompt_count: int,
    mascot_provider: str = "ai_generated",
    broll_provider: str = "ai_generated",
    chart_provider: str = "premium_infographic",
) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        frames = root / "final_reel" / "frames"
        raw = root / "raw_images"
        frames.mkdir(parents=True)
        raw.mkdir()
        color = (0, 0, 0) if blank else (80, 120, 140)
        for index in range(1, len(plan.scenes) + 1):
            frame = Image.new("RGB", (1080, 1920), color)
            raw_image = Image.new("RGB", (1080, 1920), (90, 120, 150))
            if not blank:
                for image in (frame, raw_image):
                    draw = ImageDraw.Draw(image)
                    draw.ellipse((120, 240, 760, 980), fill=(220, 150, 80))
                    draw.rectangle((260, 1040, 940, 1350), fill=(50, 80, 92))
                    draw.line((120, 1500, 960, 1180), fill=(230, 210, 120), width=18)
            frame.save(frames / f"frame_{index:02d}.jpg")
            raw_image.save(raw / f"slide_{index:02d}.jpg")
        scenes = [
            {
                "scene_number": scene.scene_number,
                "requested_visual_type": scene.visual_type,
                "selected": {
                    "provider": _provider_for_scene(scene.visual_type, mascot_provider, broll_provider, chart_provider),
                    "media_type": _media_type_for_scene(scene.visual_type, _provider_for_scene(scene.visual_type, mascot_provider, broll_provider, chart_provider)),
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
                    "caption_box_dominance_ratio": 0.06,
                },
                "mascot_consistency": {"mascot_presence_score": 92, "mascot_consistency_score": 88, "production_asset_ready": True},
            },
            voiceover_requested=True,
        )


def _provider_for_scene(visual_type: str, mascot_provider: str, broll_provider: str, chart_provider: str) -> str:
    if visual_type == "chart_motion":
        return chart_provider
    if visual_type in {"mascot_ai", "mixed"}:
        return mascot_provider
    return broll_provider


def _media_type_for_scene(visual_type: str, provider: str) -> str:
    if provider == "primitive_debug":
        return "debug_primitive_visual"
    if visual_type == "chart_motion":
        return "generated_chart_spec"
    return "generated_ai_prompt"


if __name__ == "__main__":
    unittest.main()
