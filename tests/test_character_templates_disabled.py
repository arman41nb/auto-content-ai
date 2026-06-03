from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from app.main import build_parser, main as app_main
from app.quality.candidate_scorer import score_candidate_folder


class CharacterTemplatesDisabledTests(unittest.TestCase):
    def test_mascot_template_is_rejected_by_cli(self) -> None:
        stream = io.StringIO()
        with redirect_stderr(stream):
            result = app_main(
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
                ]
            )

        self.assertEqual(result, 1)
        self.assertIn("disabled", stream.getvalue().lower())

    def test_hybrid_character_template_is_rejected_by_cli(self) -> None:
        stream = io.StringIO()
        with redirect_stderr(stream):
            result = app_main(
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
                ]
            )

        self.assertEqual(result, 1)
        self.assertIn("disabled", stream.getvalue().lower())

    def test_editorial_and_compatibility_templates_parse(self) -> None:
        parser = build_parser()
        editorial = parser.parse_args(
            [
                "generate",
                "--topic",
                "What is the relationship between oil prices and the dollar?",
                "--niche",
                "economy",
                "--slides",
                "5",
                "--template",
                "editorial_explainer_reel",
            ]
        )
        legacy_alias = parser.parse_args(
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
            ]
        )

        self.assertEqual(editorial.template, "editorial_explainer_reel")
        self.assertEqual(legacy_alias.template, "explainer_host_reel")

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


if __name__ == "__main__":
    unittest.main()
