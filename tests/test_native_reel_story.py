from __future__ import annotations

import tempfile
import unittest
import shutil
import subprocess
import argparse
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from app.content.reel_schemas import deterministic_ocean_reel_plan, reel_plan_to_carousel_plan
from app.main import build_parser, build_voiceover_script, generate, write_voiceover_assets
from app.quality.native_reel_quality import run_native_reel_quality_gate
from app.quality.post_quality_gate import run_post_quality_gate
from app.render.media_utils import audio_duration_seconds, video_duration_seconds
from app.render.native_reel_renderer import NativeReelRenderResult, _scene_durations_for_voiceover, export_native_reel_story


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

    def test_voiceover_duration_controls_scene_timing(self) -> None:
        reel_plan = deterministic_ocean_reel_plan()
        durations = _scene_durations_for_voiceover(reel_plan, 19.752)

        self.assertEqual(len(durations), 5)
        self.assertGreaterEqual(sum(durations), 20.252)
        self.assertTrue(all(duration >= 1.4 for duration in durations))
        self.assertGreater(durations[-1], reel_plan.scenes[-1].duration_seconds)

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

    def test_voiceover_script_generation_returns_short_cinematic_script(self) -> None:
        plan = reel_plan_to_carousel_plan(deterministic_ocean_reel_plan())
        script = build_voiceover_script(plan)
        word_count = len(script.split())

        self.assertGreaterEqual(word_count, 25)
        self.assertLessEqual(word_count, 45)
        self.assertIn("What if oceans rose overnight?", script)
        self.assertNotIn("#", script)
        self.assertNotIn("follow for more", script.lower())

    def test_post_quality_gate_blocks_requested_voiceover_without_audio(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = reel_plan_to_carousel_plan(deterministic_ocean_reel_plan())
            _write_final_slides(root)
            voiceover_dir = root / "voiceover"
            voiceover_dir.mkdir()
            script_path = voiceover_dir / "voiceover_script.txt"
            script_path.write_text(deterministic_ocean_reel_plan().voiceover_script + "\n", encoding="utf-8")

            report = run_post_quality_gate(
                root,
                plan,
                {
                    "voiceover_requested": True,
                    "voiceover": {"script_created": True, "script_path": str(script_path)},
                },
            )

        self.assertFalse(report.publish_ready)
        self.assertFalse(report.details["voiceover_ready"])
        self.assertIn("Voiceover was requested but voiceover audio is missing.", report.blocking_issues)

    def test_post_quality_gate_passes_when_requested_voiceover_has_audio_stream(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan = reel_plan_to_carousel_plan(deterministic_ocean_reel_plan())
            _write_final_slides(root)
            voiceover_dir = root / "voiceover"
            reel_dir = root / "final_reel"
            voiceover_dir.mkdir()
            reel_dir.mkdir()
            script_path = voiceover_dir / "voiceover_script.txt"
            script_path.write_text(deterministic_ocean_reel_plan().voiceover_script + "\n", encoding="utf-8")
            audio_path = voiceover_dir / "voiceover.mp3"
            voiced_path = reel_dir / "reel_with_voice.mp4"
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:duration=4",
                    "-c:a",
                    "libmp3lame",
                    str(audio_path),
                ],
                capture_output=True,
                check=True,
            )
            subprocess.run(
                [
                    ffmpeg,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=blue:s=1080x1920:d=4:r=24",
                    "-i",
                    str(audio_path),
                    "-shortest",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    str(voiced_path),
                ],
                capture_output=True,
                check=True,
            )
            (voiceover_dir / "subtitles.srt").write_text("1\n00:00:00,000 --> 00:00:04,000\nTest\n", encoding="utf-8")
            (voiceover_dir / "subtitles.ass").write_text("[Script Info]\n", encoding="utf-8")
            shutil.copyfile(voiced_path, reel_dir / "reel_with_voice_subtitled.mp4")

            report = run_post_quality_gate(
                root,
                plan,
                {
                    "voiceover_requested": True,
                    "voiceover": {
                        "script_created": True,
                        "script_path": str(script_path),
                        "tts_created": True,
                        "tts_path": str(audio_path),
                        "reel_with_voice_path": str(voiced_path),
                        "reel_with_voice_subtitled_path": str(reel_dir / "reel_with_voice_subtitled.mp4"),
                    },
                },
            )

        self.assertTrue(report.publish_ready)
        self.assertTrue(report.details["voiceover_ready"])
        self.assertTrue(report.details["voiceover_audio_stream_present"])
        self.assertGreater(report.details["voiceover_duration_seconds"], 0)
        self.assertTrue(report.details["subtitles_burned_in"])

    def test_voiceover_longer_than_video_fails_native_quality_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_dir = root / "raw_images"
            reel_dir = root / "final_reel"
            frames_dir = reel_dir / "frames"
            raw_dir.mkdir()
            frames_dir.mkdir(parents=True)
            for index in range(1, 6):
                Image.new("RGB", (1080, 1920), (40 + index * 20, 70, 100)).save(raw_dir / f"slide_{index:02d}.jpg")
                Image.new("RGB", (1080, 1920), (40 + index * 20, 70, 100)).save(frames_dir / f"frame_{index:02d}.jpg")
            Image.new("RGB", (1080, 1920), (40, 70, 100)).save(reel_dir / "cover.jpg")
            (reel_dir / "reel.mp4").write_bytes(b"fake")

            report = run_native_reel_quality_gate(
                output_dir=root,
                reel_plan=deterministic_ocean_reel_plan(),
                metadata={
                    "reel_export": {"reel_dimensions": [1080, 1920]},
                    "native_reel_render": {
                        "source": "native_fullscreen_scene_images",
                        "motion": "slow zoom and pan",
                        "scene_count": 5,
                        "scene_durations": [2, 2, 2, 2, 2],
                        "duration_sync_ok": False,
                        "voiceover_duration_seconds": 19.0,
                        "final_video_duration_seconds": 10.0,
                    },
                    "voiceover": {
                        "script_created": True,
                        "tts_created": True,
                        "duration_sync_ok": False,
                        "voiceover_duration_seconds": 19.0,
                        "final_video_duration_seconds": 10.0,
                        "subtitles_created": True,
                        "subtitles_burned_in": True,
                    },
                },
                voiceover_requested=True,
            )

        self.assertFalse(report["publish_ready"])
        self.assertFalse(report["duration_sync_ok"])
        self.assertIn("Voiceover is longer than the final video.", report["blocking_issues"])

    def test_write_voiceover_assets_creates_subtitled_mux_from_existing_audio(self) -> None:
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            self.skipTest("ffmpeg is not available")

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            voiceover_dir = root / "voiceover"
            reel_dir = root / "final_reel"
            voiceover_dir.mkdir()
            reel_dir.mkdir()
            audio_path = voiceover_dir / "voiceover.mp3"
            reel_path = reel_dir / "reel.mp4"
            subtitled_silent = reel_dir / "reel_subtitled_silent.mp4"
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-c:a", "libmp3lame", str(audio_path)],
                capture_output=True,
                check=True,
            )
            for path in (reel_path, subtitled_silent):
                subprocess.run(
                    [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=4.6:r=30", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)],
                    capture_output=True,
                    check=True,
                )

            scene_timings = [
                {"scene_number": index, "start_seconds": (index - 1) * 0.9, "end_seconds": index * 0.9}
                for index in range(1, 6)
            ]
            info = write_voiceover_assets(
                reel_plan_to_carousel_plan(deterministic_ocean_reel_plan()),
                root,
                reel_path,
                argparse.Namespace(tts_provider="none", voice="en-US-GuyNeural", voice_rate="-5%"),
                deterministic_ocean_reel_plan(),
                {
                    "scene_timings": scene_timings,
                    "subtitled_silent_path": str(subtitled_silent),
                    "final_video_duration_seconds": 4.6,
                    "duration_sync_ok": True,
                },
            )
            mux_duration = video_duration_seconds(Path(str(info["reel_with_voice_path"])))
            voice_duration = audio_duration_seconds(audio_path)
            reel_with_voice_exists = Path(str(info["reel_with_voice_path"])).exists()
            subtitled_exists = Path(str(info["reel_with_voice_subtitled_path"])).exists()
            srt_exists = Path(str(info["subtitles_srt_path"])).exists()
            ass_exists = Path(str(info["subtitles_ass_path"])).exists()

        self.assertTrue(reel_with_voice_exists)
        self.assertTrue(subtitled_exists)
        self.assertTrue(srt_exists)
        self.assertTrue(ass_exists)
        self.assertGreaterEqual(mux_duration, voice_duration)
        self.assertTrue(info["duration_sync_ok"])

    def test_render_only_does_not_call_llm_or_pollinations(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            raw_dir = root / "raw_images"
            raw_dir.mkdir()
            reel_plan = deterministic_ocean_reel_plan()
            plan = reel_plan_to_carousel_plan(reel_plan)
            (root / "carousel_plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
            (root / "reel_plan.json").write_text(reel_plan.model_dump_json(indent=2), encoding="utf-8")
            for index in range(1, 6):
                Image.new("RGB", (1080, 1920), (40 + index * 20, 70, 100)).save(raw_dir / f"slide_{index:02d}.jpg")

            def fake_export(*args, **kwargs):
                reel_dir = root / "final_reel"
                frames_dir = reel_dir / "frames"
                frames_dir.mkdir(parents=True, exist_ok=True)
                cover_path = reel_dir / "cover.jpg"
                reel_path = reel_dir / "reel.mp4"
                frame_paths = []
                for index in range(1, 6):
                    path = frames_dir / f"frame_{index:02d}.jpg"
                    Image.new("RGB", (1080, 1920), (40 + index * 20, 70, 100)).save(path)
                    frame_paths.append(path)
                Image.new("RGB", (1080, 1920), (40, 70, 100)).save(cover_path)
                reel_path.write_bytes(b"fake")
                return NativeReelRenderResult(
                    reel_dir,
                    reel_path,
                    cover_path,
                    frame_paths,
                    True,
                    [],
                    {
                        "renderer": "native_reel_story",
                        "source": "native_fullscreen_scene_images",
                        "motion": "slow zoom and pan",
                        "scene_count": 5,
                        "scene_durations": [2, 2, 2, 2, 2],
                    },
                )

            parser = build_parser()
            args = parser.parse_args(
                [
                    "generate",
                    "--output-dir",
                    str(root),
                    "--render-only",
                    "--make-reel",
                    "--template",
                    "native_reel_story",
                    "--tts-provider",
                    "none",
                ]
            )

            with patch("app.main.PollinationsClient", side_effect=AssertionError("Pollinations called")), patch(
                "app.main.build_llm_providers", side_effect=AssertionError("LLM called")
            ), patch("app.main.export_native_reel_story", side_effect=fake_export):
                result = generate(args)

        self.assertEqual(result, 0)


def _write_final_slides(root: Path) -> None:
    final_dir = root / "final_slides"
    final_dir.mkdir()
    colors = [(210, 80, 70), (65, 150, 210), (235, 205, 80), (85, 190, 135), (180, 90, 190)]
    for index, color in enumerate(colors, start=1):
        Image.new("RGB", (1080, 1350), color).save(final_dir / f"slide_{index:02d}.jpg")


if __name__ == "__main__":
    unittest.main()
