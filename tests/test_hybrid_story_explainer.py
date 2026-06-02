from __future__ import annotations

import io
import json
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from app.content.hybrid_story_planner import plan_hybrid_story_reel
from app.content.hybrid_story_schemas import HybridStoryPlan, hybrid_story_plan_to_carousel_plan
from app.main import build_hybrid_story_scene_image_prompt, build_parser, main as app_main
from app.mascot.mascot_profile import load_mascot_profile
from app.media.hybrid_media_planner import create_hybrid_media_plan
from app.quality.hybrid_story_quality import run_hybrid_story_quality_gate


class HybridStoryExplainerTests(unittest.TestCase):
    def test_hybrid_story_explainer_template_accepted(self) -> None:
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
                "hybrid_story_explainer",
                "--mascot",
                "miko",
                "--media-sources",
                "mixed",
                "--prefer-video-media",
                "--no-human-host",
                "--production-visual-minimums",
                "--allow-questioner",
                "--max-mascot-frame-share",
                "0.35",
                "--require-real-world-context-scenes",
                "3",
                "--caption-style",
                "hybrid_editorial",
            ]
        )

        self.assertEqual(args.template, "hybrid_story_explainer")
        self.assertEqual(args.mascot, "miko")
        self.assertTrue(args.no_human_host)
        self.assertEqual(args.max_mascot_frame_share, 0.35)
        self.assertEqual(args.caption_style, "hybrid_editorial")

    def test_hybrid_story_schema_validates_required_structure(self) -> None:
        plan = _plan()

        self.assertEqual(len(plan.scenes), 8)
        self.assertGreaterEqual(sum(1 for scene in plan.scenes if scene.mascot_presence != "none"), 2)
        self.assertGreaterEqual(sum(1 for scene in plan.scenes if scene.visual_type in {"real_world_broll", "ai_realistic_scene", "hybrid_broll_overlay", "mascot_context_scene"}), 3)
        self.assertTrue(any(scene.questioner_line_optional or scene.proxy_role_optional != "none" for scene in plan.scenes))
        self.assertTrue(any(scene.visual_type == "premium_infographic" for scene in plan.scenes))
        self.assertLessEqual(len(plan.voiceover_script.split()), 80)

    def test_hybrid_story_plan_converts_to_carousel_without_role_labels(self) -> None:
        carousel = hybrid_story_plan_to_carousel_plan(_plan())

        self.assertEqual(carousel.selected_pattern, "hybrid_story_explainer")
        self.assertNotIn("HOOK", {slide.headline.upper() for slide in carousel.slides})
        self.assertEqual(len(carousel.slides), 8)

    def test_hybrid_prompt_keeps_miko_small_and_contextual(self) -> None:
        mascot = load_mascot_profile("miko")
        plan = _plan()
        prompt = build_hybrid_story_scene_image_prompt(
            Namespace(hybrid_story_plan=plan, mascot_profile=mascot),
            plan.scenes[1].ai_scene_prompt,
            2,
        )

        self.assertIn("target frame share 18%", prompt)
        self.assertIn("small contextual guide", prompt)
        self.assertIn("giant centered character", prompt)
        self.assertIn("no text", prompt.lower())

    def test_media_planner_creates_reports_and_truthful_external_flag_without_keys(self) -> None:
        plan = _plan()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.dict("os.environ", {"PEXELS_API_KEY": "", "UNSPLASH_ACCESS_KEY": ""}, clear=False):
                media_plan = create_hybrid_media_plan(
                    plan,
                    root,
                    root / "raw_images",
                    media_sources="mixed",
                    prefer_video_media=True,
                )

            self.assertTrue((root / "media_candidates.json").exists())
            self.assertTrue((root / "media_decision_report.json").exists())
            self.assertTrue((root / "media_selection_report.json").exists())
            self.assertTrue((root / "media_attribution.json").exists())
            self.assertTrue((root / "hybrid_story_quality_report.json").exists() is False)
            self.assertFalse(media_plan["external_media_used"])
            self.assertIn("ai_generated", media_plan["media_sources_used"])
            self.assertIn("premium_infographic", media_plan["media_sources_used"])
            self.assertTrue(any(scene["production_ready"] for scene in media_plan["scenes"]))

    def test_quality_gate_passes_good_hybrid_plan_but_requires_review(self) -> None:
        report = _quality_report_with_frames(_plan())

        self.assertTrue(report["quality_gate_passed"])
        self.assertFalse(report["publish_ready"])
        self.assertTrue(report["review_required"])
        self.assertGreaterEqual(report["real_world_context_scenes"], 3)
        self.assertGreaterEqual(report["mascot_scenes"], 2)
        self.assertLessEqual(report["mascot_dominant_scenes"], 1)

    def test_max_mascot_frame_share_enforced(self) -> None:
        plan = _with_scene_update(_plan(), 2, mascot_frame_share_target=0.5)
        report = _quality_report_with_frames(plan)

        self.assertFalse(report["quality_gate_passed"])
        self.assertEqual(report["mascot_dominance_risk"], "high")
        self.assertTrue(any("max mascot frame share" in issue for issue in report["blocking_issues"]))

    def test_giant_mascot_only_scene_fails_unless_justified(self) -> None:
        plan = _with_scene_update(
            _plan(),
            2,
            mascot_frame_share_target=0.52,
            mascot_presence="side_guide",
            required_context_objects=["Miko"],
        )
        report = _quality_report_with_frames(plan)

        self.assertFalse(report["quality_gate_passed"])
        self.assertTrue(any("mascot" in issue.lower() for issue in report["blocking_issues"]))

    def test_real_world_context_scene_requirement_enforced(self) -> None:
        plan = _plan()
        scenes = [scene.model_copy(update={"visual_type": "mascot_small_overlay", "mascot_presence": "side_guide", "mascot_frame_share_target": 0.18}) for scene in plan.scenes]
        report = _quality_report_with_frames(plan.model_copy(update={"scenes": scenes}))

        self.assertFalse(report["quality_gate_passed"])
        self.assertTrue(any("real-world/realistic context scenes < 3" in issue for issue in report["blocking_issues"]))

    def test_questioner_or_proxy_scene_can_be_planned(self) -> None:
        plan = _plan()

        self.assertTrue(any(scene.proxy_role_optional == "importer" for scene in plan.scenes))
        self.assertTrue(any(scene.questioner_line_optional for scene in plan.scenes))

    def test_generic_title_card_sequence_fails_quality_gate(self) -> None:
        plan = _plan()
        scenes = [
            scene.model_copy(update={"caption_text": "The Link", "required_context_objects": ["idea"]})
            for scene in plan.scenes
        ]
        report = _quality_report_with_frames(plan.model_copy(update={"scenes": scenes}))

        self.assertFalse(report["quality_gate_passed"])
        self.assertLessEqual(report["viral_readiness_score"], 55)
        self.assertTrue(any("title-card" in issue for issue in report["blocking_issues"]))

    def test_caption_dominance_lowers_score_and_can_fail(self) -> None:
        report = _quality_report_with_frames(_plan(), caption_ratio=0.22)

        self.assertFalse(report["quality_gate_passed"])
        self.assertLess(report["caption_dominance_score"], 20)
        self.assertGreaterEqual(report["cheapness_risk_score"], 70)

    def test_external_media_used_requires_actual_external_file(self) -> None:
        report = _quality_report_with_frames(_plan(), external_flag_without_file=True)

        self.assertFalse(report["external_media_used_requires_actual_file"])
        self.assertFalse(report["quality_gate_passed"])

    def test_scene_production_ready_false_fails_output(self) -> None:
        report = _quality_report_with_frames(_plan(), production_ready_scene=4, production_ready=False)

        self.assertFalse(report["quality_gate_passed"])
        self.assertTrue(any("production_ready=false" in issue for issue in report["blocking_issues"]))

    def test_no_secrets_printed_in_media_health(self) -> None:
        with patch.dict("os.environ", {"PEXELS_API_KEY": "secret_pexels_value", "UNSPLASH_ACCESS_KEY": ""}, clear=False):
            stream = io.StringIO()
            with redirect_stdout(stream):
                result = app_main(["media-health"])

        output = stream.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("media_health_passed:", output)
        self.assertIn("secrets_printed: false", output)
        self.assertNotIn("secret_pexels_value", output)


def _plan() -> HybridStoryPlan:
    mascot = load_mascot_profile("miko")
    return plan_hybrid_story_reel("What is the relationship between oil prices and the dollar?", "economy", mascot)


def _with_scene_update(plan: HybridStoryPlan, scene_number: int, **updates) -> HybridStoryPlan:
    scenes = [
        scene.model_copy(update=updates) if scene.scene_number == scene_number else scene
        for scene in plan.scenes
    ]
    return plan.model_copy(update={"scenes": scenes})


def _quality_report_with_frames(
    plan: HybridStoryPlan,
    caption_ratio: float = 0.08,
    external_flag_without_file: bool = False,
    production_ready_scene: int = 0,
    production_ready: bool = True,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        frames = root / "final_reel" / "frames"
        raw = root / "raw_images"
        frames.mkdir(parents=True)
        raw.mkdir()
        for index in range(1, len(plan.scenes) + 1):
            frame = Image.new("RGB", (1080, 1920), (72, 104, 126))
            raw_image = Image.new("RGB", (1080, 1920), (84, 116, 132))
            for image in (frame, raw_image):
                draw = ImageDraw.Draw(image)
                draw.rectangle((130, 310, 940, 760), fill=(34, 48, 54))
                draw.ellipse((160, 860, 520, 1220), fill=(218, 148, 72))
                draw.rectangle((560, 900, 920, 1240), fill=(48, 150, 132))
                draw.line((150, 1440, 930, 1200), fill=(238, 206, 104), width=16)
            frame.save(frames / f"frame_{index:02d}.jpg")
            raw_image.save(raw / f"slide_{index:02d}.jpg")

        scenes = []
        for scene in plan.scenes:
            provider = "premium_infographic" if scene.visual_type == "premium_infographic" else "ai_generated"
            if scene.visual_type in {"real_world_broll", "hybrid_broll_overlay"} and not external_flag_without_file:
                provider = "pexels"
            local_path = raw / f"slide_{scene.scene_number:02d}.jpg"
            if external_flag_without_file and scene.scene_number == 1:
                provider = "pexels"
                local_path = raw / "missing_external.jpg"
            scenes.append(
                {
                    "scene_number": scene.scene_number,
                    "requested_visual_type": scene.visual_type,
                    "visual_type": scene.visual_type,
                    "chosen_source": provider,
                    "quality_score": 90,
                    "scene_relevance_score": 90,
                    "composition_score": 90,
                    "production_ready": production_ready if scene.scene_number == production_ready_scene else True,
                    "external_media_used": provider == "pexels" and local_path.exists(),
                    "ai_generation_required": provider == "ai_generated",
                    "selected": {
                        "provider": provider,
                        "media_type": "stock_photo" if provider == "pexels" else "generated_chart_spec" if provider == "premium_infographic" else "generated_ai_prompt",
                        "local_path": str(local_path),
                        "relevance_score": 90,
                        "visual_clarity_score": 90,
                        "vertical_usability_score": 96,
                        "license_safety_score": 92,
                    },
                }
            )
        (root / "media_plan.json").write_text(
            json.dumps(
                {
                    "template": "hybrid_story_explainer",
                    "external_media_used": external_flag_without_file or any(scene["external_media_used"] for scene in scenes),
                    "media_sources_used": sorted({str(scene["chosen_source"]) for scene in scenes}),
                    "scenes": scenes,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "media_quality_report.json").write_text(
            json.dumps(
                {
                    "not_production_ready_scene_numbers": [production_ready_scene] if production_ready_scene and not production_ready else [],
                    "ai_generation_required_scene_numbers": [
                        scene["scene_number"] for scene in scenes if scene["ai_generation_required"]
                    ],
                    "external_media_used_flag_truthful": not external_flag_without_file,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (root / "media_attribution.json").write_text('{"external_media_used": false, "missing_attribution_count": 0}', encoding="utf-8")

        return run_hybrid_story_quality_gate(
            root,
            plan,
            {
                "voiceover": {"caption_sync_score": 96, "caption_layout_score": 96, "caption_collision_count": 0},
                "hybrid_story_render": {
                    "professional_edit_score": 90,
                    "infographic_quality_score": 91,
                    "prompt_text_visible_count": 0,
                    "caption_box_dominance_ratio": caption_ratio,
                },
            },
            voiceover_requested=True,
        )


if __name__ == "__main__":
    unittest.main()
