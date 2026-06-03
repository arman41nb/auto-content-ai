from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.content.explainer_planner import plan_editorial_explainer_reel
from app.content.explainer_schemas import explainer_plan_to_carousel_plan
from app.quality.editorial_motion_quality import evaluate_editorial_motion, run_editorial_motion_quality
from app.quality.post_quality_gate import run_post_quality_gate
from app.render.editorial_motion import motion_scale_delta
from app.render.editorial_motion_planner import plan_editorial_motion
from app.render.explainer_host_reel_renderer import export_explainer_host_reel


class EditorialMotionTests(unittest.TestCase):
    def test_editorial_motion_planner_exists_and_caps_still_delta(self) -> None:
        plan = plan_editorial_explainer_reel("What is the relationship between oil prices and the dollar?", "economy")
        motion_plan = plan_editorial_motion(plan, _media_plan())

        self.assertEqual(motion_plan["version"], "editorial_motion_v1")
        for scene in motion_plan["scenes"]:
            if scene["source_type"] in {"pexels_photo", "infographic", "ai_fallback"}:
                self.assertLessEqual(motion_scale_delta(scene), 0.035)

    def test_repeated_zoom_pattern_fails_qa(self) -> None:
        motion_plan = _motion_plan_with(
            [
                {"selected_motion_preset": "subtle_push", "scale_start": 1.0, "scale_end": 1.04},
                {"selected_motion_preset": "subtle_push", "scale_start": 1.0, "scale_end": 1.04},
                {"selected_motion_preset": "subtle_push", "scale_start": 1.0, "scale_end": 1.04},
                {"selected_motion_preset": "subtle_pull", "scale_start": 1.04, "scale_end": 1.0},
                {"selected_motion_preset": "subtle_pull", "scale_start": 1.04, "scale_end": 1.0},
            ]
        )

        report = evaluate_editorial_motion(motion_plan)

        self.assertFalse(report["quality_gate_passed"])
        self.assertGreaterEqual(report["repeated_motion_pattern_count"], 1)

    def test_obvious_slideshow_motion_fails_qa(self) -> None:
        motion_plan = _motion_plan_with(
            [
                {"selected_motion_preset": "zoom_in", "scale_start": 1.0, "scale_end": 1.09},
                {"selected_motion_preset": "zoom_out", "scale_start": 1.09, "scale_end": 1.0},
                {"selected_motion_preset": "zoom_in", "scale_start": 1.0, "scale_end": 1.08},
                {"selected_motion_preset": "zoom_out", "scale_start": 1.08, "scale_end": 1.0},
                {"selected_motion_preset": "zoom_in", "scale_start": 1.0, "scale_end": 1.07},
            ]
        )

        report = evaluate_editorial_motion(motion_plan)

        self.assertFalse(report["quality_gate_passed"])
        self.assertEqual(report["slideshow_motion_risk"], "high")
        self.assertGreater(report["obvious_zoom_count"], 1)

    def test_infographic_scene_reveals_elements_not_full_frame_zoom(self) -> None:
        plan = plan_editorial_explainer_reel("What is the relationship between oil prices and the dollar?", "economy")
        motion_plan = plan_editorial_motion(plan, _media_plan())
        infographic_scene = motion_plan["scenes"][2]

        self.assertEqual(infographic_scene["source_type"], "infographic")
        self.assertEqual(infographic_scene["selected_motion_preset"], "infographic_reveal")
        self.assertEqual(motion_scale_delta(infographic_scene), 0.0)

    def test_pexels_video_scene_prefers_real_clip_motion_without_artificial_zoom(self) -> None:
        plan = plan_editorial_explainer_reel("What is the relationship between oil prices and the dollar?", "economy")
        media_plan = _media_plan()
        with tempfile.TemporaryDirectory() as temp:
            clip_path = Path(temp) / "clip.mp4"
            clip_path.write_bytes(b"fake")
            media_plan["scenes"][1]["selected"] = {
                "provider": "pexels",
                "media_type": "stock_video",
                "local_path": "poster.jpg",
                "local_video_path": str(clip_path),
            }

            motion_plan = plan_editorial_motion(plan, media_plan)
            video_scene = motion_plan["scenes"][1]

        self.assertEqual(video_scene["source_type"], "pexels_video")
        self.assertEqual(video_scene["selected_motion_preset"], "static_hold")
        self.assertFalse(video_scene["artificial_motion"])
        self.assertIn("clip motion", video_scene["reason"])

    def test_motion_plan_is_saved_by_explainer_renderer(self) -> None:
        plan = plan_editorial_explainer_reel("What is the relationship between oil prices and the dollar?", "economy")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            final = root / "final_slides"
            final.mkdir()
            for index in range(1, 6):
                Image.new("RGB", (1080, 1920), (40 + index, 60, 80)).save(final / f"slide_{index:02d}.jpg")
            (root / "media_plan.json").write_text(json.dumps(_media_plan()), encoding="utf-8")

            with patch("app.render.explainer_host_reel_renderer.get_ffmpeg_path", return_value=None):
                result = export_explainer_host_reel(plan, final, root)

            self.assertTrue((root / "editorial_motion_plan.json").exists())
            self.assertEqual(result.metadata["editorial_motion_plan_path"], str(root / "editorial_motion_plan.json"))
            self.assertTrue(result.metadata["single_source_of_truth"])

    def test_motion_qa_integrates_with_post_quality_gate(self) -> None:
        explainer_plan = plan_editorial_explainer_reel("What is the relationship between oil prices and the dollar?", "economy")
        carousel_plan = explainer_plan_to_carousel_plan(explainer_plan)
        bad_motion = evaluate_editorial_motion(
            _motion_plan_with(
                [
                    {"selected_motion_preset": "zoom_in", "scale_start": 1.0, "scale_end": 1.09},
                    {"selected_motion_preset": "zoom_in", "scale_start": 1.0, "scale_end": 1.08},
                    {"selected_motion_preset": "zoom_in", "scale_start": 1.0, "scale_end": 1.07},
                    {"selected_motion_preset": "static_hold", "scale_start": 1.0, "scale_end": 1.0},
                    {"selected_motion_preset": "static_hold", "scale_start": 1.0, "scale_end": 1.0},
                ]
            )
        )
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            final = root / "final_slides"
            final.mkdir()
            for index in range(1, 6):
                Image.new("RGB", (1080, 1920), (70, 80 + index, 90)).save(final / f"slide_{index:02d}.jpg")

            report = run_post_quality_gate(
                root,
                carousel_plan,
                {
                    "visual_template": "editorial_explainer_reel",
                    "reel_export": {"requested": False},
                    "editorial_motion_quality": bad_motion,
                },
            )

        self.assertFalse(report.publish_ready)
        self.assertEqual(report.recommended_action, "polish_motion")

    def test_motion_quality_report_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "editorial_motion_plan.json").write_text(json.dumps(_motion_plan_with([{}] * 5)), encoding="utf-8")

            report = run_editorial_motion_quality(root)

            self.assertTrue((root / "editorial_motion_quality_report.json").exists())
            self.assertGreaterEqual(report["editorial_motion_score"], 85)


def _media_plan() -> dict[str, object]:
    scenes = []
    for index in range(1, 6):
        if index in {3, 5}:
            selected = {"provider": "premium_infographic", "media_type": "generated_chart_spec", "title": "summary card"}
        else:
            selected = {"provider": "pexels", "media_type": "stock_photo", "title": "oil tanker wide port vertical"}
        scenes.append({"scene_number": index, "selected": selected, "selected_source_type": selected["provider"]})
    return {"pexels_first_policy_active": True, "scenes": scenes}


def _motion_plan_with(overrides: list[dict[str, object]]) -> dict[str, object]:
    scenes = []
    for index, override in enumerate(overrides, start=1):
        scene = {
            "scene_number": index,
            "source_type": "pexels_photo",
            "selected_motion_preset": "static_hold",
            "scale_start": 1.0,
            "scale_end": 1.0,
            "transition_out": "clean_cut" if index < len(overrides) else "none",
            "reason": "test motion",
            "combined_motion_load_score": 30,
        }
        scene.update(override)
        scenes.append(scene)
    return {
        "version": "editorial_motion_v1",
        "scenes": scenes,
        "transition_plan": [
            {"from_scene": index, "to_scene": index + 1, "transition": "clean_cut", "reason": "test"}
            for index in range(1, len(scenes))
        ],
    }


if __name__ == "__main__":
    unittest.main()
