from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from app.main import build_parser
from app.queue.weekly_queue import assign_topics_to_days, discover_weekly_topics, run_weekly_queue


class WeeklyQueueTests(unittest.TestCase):
    def test_weekly_queue_flags_exist(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "weekly-queue",
                "--niche",
                "science",
                "--lane",
                "any",
                "--days",
                "7",
                "--candidates-per-day",
                "3",
                "--sources",
                "static",
                "--handle",
                "@yourpage",
                "--image-variants",
                "3",
                "--rate-limit",
                "25",
                "--llm-provider",
                "auto",
                "--template",
                "native_reel_story",
                "--voiceover",
                "--max-full-generations",
                "21",
            ]
        )

        self.assertEqual(args.command, "weekly-queue")
        self.assertEqual(args.days, 7)
        self.assertEqual(args.candidates_per_day, 3)
        self.assertTrue(args.voiceover)

    def test_dry_run_writes_preview_without_batch_runner(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            queue_dir = Path(temp) / "queue"
            args = argparse.Namespace(
                niche="science",
                lane="any",
                days=2,
                candidates_per_day=2,
                sources="static",
                handle="@yourpage",
                image_variants=3,
                rate_limit=25,
                llm_provider="auto",
                template="native_reel_story",
                voiceover=True,
                tts_provider="none",
                voice="en-US-GuyNeural",
                voice_rate="-5%",
                dry_run=True,
                score_only=False,
                queue_dir=str(queue_dir),
                max_full_generations=None,
            )

            result = run_weekly_queue(args, batch_runner=_unexpected_batch_runner)

            self.assertEqual(result, 0)
            self.assertTrue((queue_dir / "queue_plan_preview.json").exists())
            self.assertTrue((queue_dir / "queue_plan_preview.md").exists())
            self.assertFalse((queue_dir / "day_01").exists())

    def test_static_weekly_topics_are_unique_and_limit_flood_repetition(self) -> None:
        args = argparse.Namespace(niche="science", lane="any", sources="static")

        selected = discover_weekly_topics(args, 21)
        plans = assign_topics_to_days(selected, days=7, candidates_per_day=3)

        self.assertEqual(len(selected), 21)
        self.assertEqual(len(plans), 7)
        self.assertTrue(all(len(day["topics"]) == 3 for day in plans))
        normalized = [" ".join(candidate.topic.lower().split()) for candidate in selected]
        self.assertEqual(len(normalized), len(set(normalized)))
        flood_like = [
            candidate
            for candidate in selected
            if any(term in " ".join([candidate.topic, candidate.angle, " ".join(candidate.keywords)]).lower() for term in ("ocean", "flood", "tsunami", "tide", "water", "iceberg"))
        ]
        self.assertLessEqual(len(flood_like), 2)


def _unexpected_batch_runner(args: argparse.Namespace) -> int:
    raise AssertionError("dry-run must not call batch generation")


if __name__ == "__main__":
    unittest.main()

