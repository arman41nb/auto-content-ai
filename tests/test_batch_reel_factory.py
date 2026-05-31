from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.content.reel_schemas import native_reel_plan_for_topic
from app.main import build_parser, diverse_batch_selection
from app.discovery.schemas import TopicCandidate
from app.quality.candidate_scorer import score_candidate_folder


class BatchReelFactoryTests(unittest.TestCase):
    def test_batch_reels_flags_exist(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "batch-reels",
                "--niche",
                "science",
                "--lane",
                "any",
                "--count",
                "3",
                "--sources",
                "static",
                "--template",
                "native_reel_story",
                "--voiceover",
            ]
        )

        self.assertEqual(args.command, "batch-reels")
        self.assertEqual(args.count, 3)
        self.assertTrue(args.voiceover)

    def test_native_reel_plan_factory_uses_topic(self) -> None:
        plan = native_reel_plan_for_topic("What if oxygen disappeared for 5 seconds?", "science")

        self.assertEqual(plan.topic, "What if oxygen disappeared for 5 seconds?")
        self.assertEqual(len(plan.scenes), 5)
        self.assertIn("oxygen", plan.voiceover_script.lower())
        self.assertTrue(all(len(scene.on_screen_text.split()) <= 5 for scene in plan.scenes))

    def test_diversity_avoids_repeated_flood_topics_when_possible(self) -> None:
        candidates = [
            _candidate("What if oceans rose overnight?", ["ocean", "flood"]),
            _candidate("What if every iceberg melted overnight?", ["ocean", "flood"]),
            _candidate("What if oxygen disappeared for 5 seconds?", ["oxygen"]),
        ]

        selected = diverse_batch_selection(candidates, 2)

        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0].topic, "What if oceans rose overnight?")
        self.assertEqual(selected[1].topic, "What if oxygen disappeared for 5 seconds?")

    def test_candidate_score_caps_missing_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "metadata.json").write_text(
                json.dumps(
                    {
                        "topic": "What if oxygen disappeared for 5 seconds?",
                        "topic_discovery_lane": "what_if_disaster",
                        "topic_discovery_score": 90,
                        "voiceover_requested": True,
                        "reel_export": {"created_video": True},
                    }
                ),
                encoding="utf-8",
            )
            (root / "native_reel_quality_report.json").write_text(
                json.dumps(
                    {
                        "publish_ready": True,
                        "native_reel_score": 90,
                        "first_second_hook_score": 92,
                        "scene_variety_score": 88,
                        "voiceover_quality_score": 90,
                        "cover_quality_score": 94,
                        "ai_slideshow_risk_score": 20,
                        "cover_native_1080x1920": True,
                        "reel_native_1080x1920": True,
                    }
                ),
                encoding="utf-8",
            )
            (root / "post_quality_report.json").write_text(
                json.dumps({"publish_ready": True, "score": 92, "voiceover_audio_stream_present": False}),
                encoding="utf-8",
            )

            scored = score_candidate_folder(root, voiceover_requested=True)

        self.assertLessEqual(scored["candidate_score"], 50)
        self.assertIn("voiceover requested", " ".join(scored["warnings"]))


def _candidate(topic: str, keywords: list[str]) -> TopicCandidate:
    return TopicCandidate(
        topic=topic,
        niche="science",
        lane="what_if_disaster",
        angle=topic,
        source="static",
        keywords=keywords,
        score=90,
    )


if __name__ == "__main__":
    unittest.main()
