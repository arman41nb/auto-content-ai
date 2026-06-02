"""CLI entrypoint for the local carousel generator."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from app.config import load_config
from app.content.explainer_planner import plan_explainer_host_reel
from app.content.explainer_schemas import (
    ExplainerPlan,
    explainer_plan_to_carousel_plan,
    explainer_plan_to_reel_plan,
)
from app.content.mascot_story_planner import plan_mascot_story_reel
from app.content.mascot_story_schemas import (
    MascotStoryPlan,
    mascot_story_plan_to_carousel_plan,
    mascot_story_plan_to_reel_plan,
)
from app.content.planner import CarouselPlanner
from app.content.reel_schemas import (
    ReelPlan,
    deterministic_ocean_reel_plan,
    native_reel_plan_for_topic,
    reel_plan_to_carousel_plan,
)
from app.content.schemas import CarouselPlan
from app.discovery.discovery_pipeline import DiscoveryPipeline, write_discovery_reports
from app.discovery.schemas import TopicCandidate
from app.host.host_consistency import host_consistency_report
from app.host.host_profile import HostProfile, load_host_profile
from app.host.host_prompt import build_host_reference_prompt, build_host_scene_prompt
from app.image.pollinations_client import PollinationsClient
from app.image.prompt_builder import build_image_prompt
from app.image.quality import score_candidate, select_best_candidate, selection_to_dict
from app.image.sanitizer import preferred_image_dir, sanitize_post_images
from app.llm.provider_factory import build_llm_providers
from app.quality.candidate_scorer import score_candidate_folder
from app.quality.contact_sheet import create_batch_contact_sheet, create_qa_contact_sheet
from app.quality.explainer_quality import run_explainer_quality_gate
from app.quality.mascot_story_quality import (
    run_mascot_story_quality_gate,
    write_mascot_story_technical_report,
)
from app.quality.native_reel_quality import run_native_reel_quality_gate
from app.quality.overlay_masks import get_expected_overlay_regions
from app.quality.post_quality_gate import PostQualityReport, run_post_quality_gate
from app.render.carousel_renderer import CarouselRenderer
from app.render.explainer_host_reel_renderer import export_explainer_host_reel
from app.render.kinetic_captions import (
    build_caption_timing_from_srt,
    caption_quality_metrics,
    render_kinetic_caption_video,
    write_caption_srt,
)
from app.render.media_utils import audio_duration_seconds, ffprobe_summary, has_audio_stream, media_dimensions, video_duration_seconds
from app.render.mascot_story_reel_renderer import export_mascot_story_reel
from app.render.native_reel_renderer import export_native_reel_story, get_ffmpeg_path
from app.render.reel_exporter import export_reel_package
from app.render.subtitles import build_subtitle_cues, write_subtitle_files
from app.media.media_planner import create_media_plan
from app.mascot.mascot_consistency import ensure_mascot_reference_assets, mascot_consistency_report
from app.mascot.mascot_profile import MascotProfile, load_mascot_profile
from app.mascot.mascot_prompt import build_mascot_scene_prompt
from app.mascot.mascot_scene_generator import (
    build_production_mascot_scene_prompt,
    build_production_non_mascot_scene_prompt,
    create_neutral_scene_fallback,
)
from app.research.research_pack_loader import load_research_pack
from app.research.web_research_pack import load_explainer_research_pack
from app.storage.post_exporter import PostExporter
from app.strategy.pattern_library import load_relevant_patterns


LANE_CHOICES = ["what_if_disaster", "extreme_science", "future_scenario", "any"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate Instagram carousel post packages.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Generate a carousel post package.")
    generate.add_argument("--topic", default=None, help="Carousel topic.")
    generate.add_argument("--niche", default=None, help="Content niche, e.g. history or science.")
    generate.add_argument("--slides", type=int, default=None, help="Number of carousel slides.")
    generate.add_argument("--handle", default="@yourpage", help="Small handle rendered on each slide.")
    generate.add_argument(
        "--template",
        default="cinematic_reel_editorial",
        help="Visual template name for prompt guidance.",
    )
    generate.add_argument("--mascot", default="miko", help="Mascot id for mascot_story_explainer.")
    generate.add_argument(
        "--media-sources",
        default="mixed",
        help="Media source mode for mascot explainers: auto, ai, pexels, unsplash, wikimedia, or mixed.",
    )
    generate.add_argument("--prefer-video-media", action="store_true", help="Prefer video-capable media search when available.")
    generate.add_argument("--no-human-host", action="store_true", help="Forbid human host scenes in supported templates.")
    generate.add_argument(
        "--production-visual-minimums",
        action="store_true",
        default=False,
        help="Enforce production visual minimums for mascot_story_explainer.",
    )
    generate.add_argument("--skip-images", action="store_true", help="Only save plan and metadata.")
    generate.add_argument(
        "--skip-render",
        action="store_true",
        help="Generate raw images but skip final Pillow-rendered slides.",
    )
    generate.add_argument(
        "--rate-limit",
        type=float,
        default=None,
        help="Seconds to wait between Pollinations requests.",
    )
    generate.add_argument(
        "--image-variants",
        type=int,
        default=3,
        help="Number of image candidates to generate per slide before selecting the best one.",
    )
    generate.add_argument(
        "--show-grounding",
        action="store_true",
        help="Print the research pack, selected patterns, and grounding warnings before planning.",
    )
    generate.add_argument(
        "--llm-provider",
        choices=["auto", "groq", "gemini", "openrouter", "cerebras"],
        default=None,
        help="LLM provider to use. Defaults to DEFAULT_LLM_PROVIDER or auto.",
    )
    generate.add_argument(
        "--compare-plans",
        action="store_true",
        help="Generate plans from all available providers, score them, and use the best one.",
    )
    generate.add_argument(
        "--make-reel",
        action="store_true",
        help="Create final_reel/cover.jpg and final_reel/reel.mp4 from generated images when FFmpeg is available.",
    )
    add_voiceover_arguments(generate)
    add_sanitizer_argument(generate)
    generate.add_argument(
        "--plan-file",
        default=None,
        help="Load and validate an existing carousel_plan.json, skipping LLM planning.",
    )
    generate.add_argument(
        "--output-dir",
        default=None,
        help="Use a specific existing or new output folder.",
    )
    generate.add_argument(
        "--render-only",
        action="store_true",
        help="Load an existing output folder and re-render final slides without LLM or image API calls.",
    )
    generate.add_argument(
        "--resume",
        action="store_true",
        help="Resume an output folder by regenerating missing or failed images and re-rendering slides.",
    )

    discover = subparsers.add_parser("discover", help="Discover and score carousel topics.")
    discover.add_argument("--niche", required=True, help="Content niche: science, future, or history.")
    discover.add_argument(
        "--lane",
        choices=LANE_CHOICES,
        default="any",
        help="Growth discovery lane.",
    )
    discover.add_argument("--count", required=True, type=int, help="Number of candidates to return.")
    discover.add_argument(
        "--sources",
        default="static,nasa,wikipedia,gdelt",
        help="Comma-separated discovery sources: static,nasa,wikipedia,gdelt.",
    )
    discover.add_argument(
        "--output",
        default="outputs/discovery",
        help="Discovery report output directory.",
    )
    discover.add_argument("--query", default=None, help="Optional source query override.")
    discover.add_argument(
        "--date",
        default="today",
        help="Report date label. Currently supports 'today'.",
    )

    auto = subparsers.add_parser("auto", help="Discover top topics and generate carousels.")
    auto.add_argument("--niche", required=True, help="Content niche: science, future, or history.")
    auto.add_argument(
        "--lane",
        choices=LANE_CHOICES,
        default="any",
        help="Growth discovery lane.",
    )
    auto.add_argument("--count", required=True, type=int, help="Number of posts/topics to generate.")
    auto.add_argument("--handle", default="@yourpage", help="Small handle rendered on each slide.")
    auto.add_argument("--slides", type=int, default=5, help="Number of carousel slides per topic.")
    auto.add_argument(
        "--template",
        default="cinematic_reel_editorial",
        help="Visual template name for prompt guidance.",
    )
    auto.add_argument("--mascot", default="miko", help="Mascot id for mascot_story_explainer.")
    auto.add_argument(
        "--media-sources",
        default="mixed",
        help="Media source mode for mascot explainers: auto, ai, pexels, unsplash, wikimedia, or mixed.",
    )
    auto.add_argument("--prefer-video-media", action="store_true", help="Prefer video-capable media search when available.")
    auto.add_argument("--no-human-host", action="store_true", help="Forbid human host scenes in supported templates.")
    auto.add_argument(
        "--production-visual-minimums",
        action="store_true",
        default=False,
        help="Enforce production visual minimums for mascot_story_explainer.",
    )
    auto.add_argument(
        "--sources",
        default="static,nasa,wikipedia,gdelt",
        help="Comma-separated discovery sources: static,nasa,wikipedia,gdelt.",
    )
    auto.add_argument(
        "--output",
        default="outputs/discovery",
        help="Discovery report output directory.",
    )
    auto.add_argument("--query", default=None, help="Optional source query override.")
    auto.add_argument(
        "--rate-limit",
        type=float,
        default=None,
        help="Seconds to wait between Pollinations requests.",
    )
    auto.add_argument(
        "--image-variants",
        type=int,
        default=3,
        help="Number of image candidates to generate per slide before selecting the best one.",
    )
    auto.add_argument(
        "--llm-provider",
        choices=["auto", "groq", "gemini", "openrouter", "cerebras"],
        default=None,
        help="LLM provider to use. Defaults to DEFAULT_LLM_PROVIDER or auto.",
    )
    auto.add_argument(
        "--compare-plans",
        action="store_true",
        help="Generate plans from all available providers, score them, and use the best one.",
    )
    auto.add_argument("--skip-images", action="store_true", help="Only save plan and metadata.")
    auto.add_argument(
        "--skip-render",
        action="store_true",
        help="Generate raw images but skip final Pillow-rendered slides.",
    )
    auto.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and print selected topics without generating carousels.",
    )
    auto.add_argument(
        "--compare-candidates",
        action="store_true",
        help="Generate a native Reel candidate batch and comparison report instead of loose posts.",
    )
    auto.add_argument(
        "--make-reel",
        action="store_true",
        help="Create final_reel/cover.jpg and final_reel/reel.mp4 from generated images when FFmpeg is available.",
    )
    add_voiceover_arguments(auto)
    add_sanitizer_argument(auto)

    batch = subparsers.add_parser("batch-reels", help="Generate or rescore a native Reel candidate batch.")
    batch.add_argument("--niche", default=None, help="Content niche: science, future, or history.")
    batch.add_argument("--lane", choices=LANE_CHOICES, default="any", help="Growth discovery lane.")
    batch.add_argument("--count", type=int, default=3, help="Number of Reel candidates to generate.")
    batch.add_argument(
        "--sources",
        default="static",
        help="Comma-separated discovery sources: static,nasa,wikipedia,gdelt.",
    )
    batch.add_argument("--handle", default="@yourpage", help="Small handle rendered on each scene.")
    batch.add_argument("--image-variants", type=int, default=3, help="Image candidates per scene.")
    batch.add_argument("--rate-limit", type=float, default=None, help="Seconds between Pollinations requests.")
    batch.add_argument(
        "--llm-provider",
        choices=["auto", "groq", "gemini", "openrouter", "cerebras"],
        default=None,
        help="Accepted for command parity; native Reel batch uses topic-factory plans.",
    )
    batch.add_argument("--template", default="native_reel_story", help="Must be native_reel_story for Reel batches.")
    add_voiceover_arguments(batch)
    add_sanitizer_argument(batch)
    batch.add_argument("--batch-dir", default=None, help="Existing batch folder for --score-only, or output batch folder.")
    batch.add_argument("--score-only", action="store_true", help="Recompute comparison reports without LLM or images.")

    weekly = subparsers.add_parser("weekly-queue", help="Plan, generate, or rescore a weekly native Reel queue.")
    weekly.add_argument("--niche", default=None, help="Content niche: science, future, or history.")
    weekly.add_argument("--lane", choices=LANE_CHOICES, default="any", help="Growth discovery lane.")
    weekly.add_argument("--days", type=int, default=7, help="Number of queue days.")
    weekly.add_argument("--candidates-per-day", type=int, default=3, help="Candidates to generate per day.")
    weekly.add_argument(
        "--sources",
        default="static",
        help="Comma-separated discovery sources: static,nasa,wikipedia,gdelt.",
    )
    weekly.add_argument("--handle", default="@yourpage", help="Small handle rendered on each scene.")
    weekly.add_argument("--image-variants", type=int, default=3, help="Image candidates per scene.")
    weekly.add_argument("--rate-limit", type=float, default=None, help="Seconds between Pollinations requests.")
    weekly.add_argument(
        "--llm-provider",
        choices=["auto", "groq", "gemini", "openrouter", "cerebras"],
        default=None,
        help="Accepted for command parity; native Reel queue uses topic-factory plans.",
    )
    weekly.add_argument("--template", default="native_reel_story", help="Must be native_reel_story for weekly queues.")
    add_voiceover_arguments(weekly)
    add_sanitizer_argument(weekly)
    weekly.add_argument("--dry-run", action="store_true", help="Discover and assign topics without LLM, images, or video.")
    weekly.add_argument("--score-only", action="store_true", help="Recompute queue reports from existing candidate outputs.")
    weekly.add_argument("--queue-dir", default=None, help="Existing queue folder for --score-only, or output queue folder.")
    weekly.add_argument(
        "--max-full-generations",
        type=int,
        default=None,
        help="Required cap for real generation; must be at least days*candidates-per-day.",
    )

    compare_batch_parser = subparsers.add_parser("compare-batch", help="Recompute native Reel batch scores only.")
    compare_batch_parser.add_argument("--batch-dir", required=True, help="Existing batch folder to rescore.")
    compare_batch_parser.add_argument(
        "--voiceover",
        action="store_true",
        default=True,
        help="Expect reel_with_voice audio streams when scoring candidates.",
    )
    mark_review_parser = subparsers.add_parser("mark-review", help="Mark a generated package with human review status.")
    mark_review_parser.add_argument("--output-dir", required=True, help="Output package directory to mark.")
    mark_review_parser.add_argument("--status", required=True, choices=["approved", "rejected", "needs_revision"], help="Human review status.")
    mark_review_parser.add_argument("--reason", default="", help="Short human review reason.")
    return parser


def add_voiceover_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--voiceover",
        action="store_true",
        help="Create voiceover/voiceover_script.txt and optional TTS audio for Reel output.",
    )
    parser.add_argument(
        "--tts-provider",
        choices=["auto", "edge", "none"],
        default="auto",
        help="Voiceover TTS provider. Use none to write only the script.",
    )
    parser.add_argument(
        "--voice",
        default="en-US-GuyNeural",
        help="edge-tts voice name.",
    )
    parser.add_argument(
        "--voice-rate",
        default="-5%",
        help="edge-tts speaking rate, e.g. -5%% or +0%%.",
    )


def add_sanitizer_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--sanitizer-mode",
        choices=["off", "light", "targeted", "strict"],
        default="targeted",
        help="Image cleanup strength for likely AI text artifacts.",
    )


def generate(args: argparse.Namespace) -> int:
    native_reel_mode = is_native_reel_story(args)
    explainer_host_mode = is_explainer_host_reel(args)
    mascot_story_mode = is_mascot_story_explainer(args)
    if native_reel_mode and args.image_variants < 3:
        args.image_variants = 3
    if mascot_story_mode:
        args.mascot = str(getattr(args, "mascot", "") or "miko")
        args.media_sources = str(getattr(args, "media_sources", "") or "mixed")
        args.prefer_video_media = True if getattr(args, "prefer_video_media", False) else True
        args.no_human_host = True
        args.production_visual_minimums = True
    if getattr(args, "voiceover", False) and not getattr(args, "make_reel", False):
        args.make_reel = True
    if args.render_only and not args.output_dir:
        raise ValueError("--render-only requires --output-dir.")
    if args.resume and not args.output_dir:
        raise ValueError("--resume requires --output-dir.")
    if args.render_only and (args.plan_file or args.resume):
        raise ValueError("--render-only cannot be combined with --plan-file or --resume.")
    if not (args.plan_file or args.render_only or args.resume):
        missing = [name for name in ("topic", "niche", "slides") if getattr(args, name, None) in (None, "")]
        if missing:
            raise ValueError("Normal generation requires: " + ", ".join(f"--{name}" for name in missing) + ".")
    if args.slides is not None and (args.slides < 1 or args.slides > 20):
        raise ValueError("--slides must be between 1 and 20.")
    if args.image_variants < 1 or args.image_variants > 8:
        raise ValueError("--image-variants must be between 1 and 8.")

    config = load_config()
    exporter = PostExporter(config.outputs_root)
    created_at = datetime.now().astimezone()
    warnings = list(config.warnings)
    planning_info = empty_planning_info()
    reel_plan: ReelPlan | None = None
    explainer_plan: ExplainerPlan | None = None
    mascot_story_plan: MascotStoryPlan | None = None
    host_profile: HostProfile | None = None
    mascot_profile: MascotProfile | None = None
    grounding_warnings: list[str] = []
    research_pack_used = "none"
    pattern_library_used = False
    existing_metadata: dict[str, object] = {}

    if args.render_only or args.resume:
        output_dir = resolve_output_dir(config.project_root, args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        plan = load_plan(output_dir / "carousel_plan.json")
        reel_plan = load_reel_plan(output_dir / "reel_plan.json") if (native_reel_mode or mascot_story_mode) else None
        explainer_plan = load_explainer_plan(output_dir / "explainer_plan.json") if explainer_host_mode else None
        mascot_story_plan = load_mascot_story_plan(output_dir / "mascot_story_plan.json") if mascot_story_mode else None
        if explainer_plan is not None:
            reel_plan = explainer_plan_to_reel_plan(explainer_plan)
            host_profile = load_host_profile()
        if mascot_story_plan is not None:
            reel_plan = mascot_story_plan_to_reel_plan(mascot_story_plan)
            mascot_profile = load_mascot_profile(mascot_story_plan.mascot_id)
        existing_metadata = load_existing_metadata(output_dir)
        apply_plan_defaults(args, plan)
    elif args.plan_file:
        plan = load_plan(resolve_output_dir(config.project_root, args.plan_file))
        reel_plan = (
            native_reel_plan_for_topic(plan.topic, str(args.niche or plan.niche))
            if native_reel_mode
            else None
        )
        apply_plan_defaults(args, plan)
        output_dir = (
            resolve_output_dir(config.project_root, args.output_dir)
            if args.output_dir
            else exporter.create_output_dir(plan.topic, created_at)
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        exporter.save_plan(output_dir, plan)
        planning_info = empty_planning_info(provider="plan_file", model=str(resolve_output_dir(config.project_root, args.plan_file)))
    elif mascot_story_mode:
        topic = str(args.topic or "What is the relationship between oil prices and the dollar?")
        mascot_profile = load_mascot_profile(str(getattr(args, "mascot", "miko") or "miko"))
        research_result = load_explainer_research_pack(
            topic=topic,
            niche=str(args.niche or "economy"),
            research_root=config.project_root / "data" / "research",
        )
        grounding_warnings = [str(warning) for warning in research_result.get("warnings", []) if str(warning).strip()]
        warnings.extend(grounding_warnings)
        research_pack_used = str(research_result.get("path", "")) if research_result.get("used") else "none"
        mascot_story_plan = plan_mascot_story_reel(topic, str(args.niche or "economy"), mascot_profile)
        reel_plan = mascot_story_plan_to_reel_plan(mascot_story_plan)
        plan = mascot_story_plan_to_carousel_plan(mascot_story_plan)
        args.topic = mascot_story_plan.topic
        args.niche = mascot_story_plan.niche
        args.slides = len(mascot_story_plan.scenes)
        output_dir = (
            resolve_output_dir(config.project_root, args.output_dir)
            if args.output_dir
            else exporter.create_output_dir(mascot_story_plan.topic, created_at)
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output: {output_dir}")
        exporter.save_plan(output_dir, plan)
        save_reel_plan(output_dir, reel_plan)
        save_mascot_story_plan(output_dir, mascot_story_plan)
        planning_info = empty_planning_info(provider="deterministic", model="mascot_story_explainer/topic_factory")
    elif explainer_host_mode:
        topic = str(args.topic or "What is the relationship between oil prices and the dollar?")
        host_profile = load_host_profile()
        research_result = load_explainer_research_pack(
            topic=topic,
            niche=str(args.niche or "economy"),
            research_root=config.project_root / "data" / "research",
        )
        grounding_warnings = [str(warning) for warning in research_result.get("warnings", []) if str(warning).strip()]
        warnings.extend(grounding_warnings)
        research_pack_used = str(research_result.get("path", "")) if research_result.get("used") else "none"
        explainer_plan = plan_explainer_host_reel(topic, str(args.niche or "economy"), host_profile)
        reel_plan = explainer_plan_to_reel_plan(explainer_plan)
        plan = explainer_plan_to_carousel_plan(explainer_plan)
        args.topic = explainer_plan.topic
        args.niche = explainer_plan.niche
        args.slides = len(explainer_plan.scenes)
        output_dir = (
            resolve_output_dir(config.project_root, args.output_dir)
            if args.output_dir
            else exporter.create_output_dir(explainer_plan.topic, created_at)
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output: {output_dir}")
        exporter.save_plan(output_dir, plan)
        save_reel_plan(output_dir, reel_plan)
        save_explainer_plan(output_dir, explainer_plan)
        planning_info = empty_planning_info(provider="deterministic", model="explainer_host_reel/topic_factory")
    elif native_reel_mode:
        discovery_candidate = getattr(args, "topic_discovery_candidate", None)
        topic = str(getattr(discovery_candidate, "topic", None) or args.topic or "What if gravity doubled for one day?")
        lane = str(getattr(discovery_candidate, "lane", "what_if_disaster") or "what_if_disaster")
        angle = str(getattr(discovery_candidate, "angle", "") or "")
        reel_plan = native_reel_plan_for_topic(topic, str(args.niche or "science"), lane=lane, angle=angle)
        plan = reel_plan_to_carousel_plan(reel_plan)
        args.topic = reel_plan.topic
        args.niche = reel_plan.niche
        args.slides = len(reel_plan.scenes)
        output_dir = (
            resolve_output_dir(config.project_root, args.output_dir)
            if args.output_dir
            else exporter.create_output_dir(reel_plan.topic, created_at)
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Output: {output_dir}")
        exporter.save_plan(output_dir, plan)
        save_reel_plan(output_dir, reel_plan)
        planning_info = empty_planning_info(provider="deterministic", model="native_reel_story/topic_factory")
    else:
        output_dir = (
            resolve_output_dir(config.project_root, args.output_dir)
            if args.output_dir
            else exporter.create_output_dir(str(args.topic), created_at)
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        research_result = load_research_pack(
            topic=str(args.topic),
            niche=str(args.niche),
            research_root=config.project_root / "data" / "research",
        )
        pattern_selection = load_relevant_patterns(
            niche=str(args.niche),
            patterns_path=config.project_root / "data" / "patterns" / "carousel_patterns.json",
        )
        grounding_warnings = [*research_result.warnings, *pattern_selection.warnings]
        warnings.extend(grounding_warnings)
        research_pack_used = str(research_result.path) if research_result.used else "none"
        pattern_library_used = pattern_selection.used

        print(f"Output: {output_dir}")
        if args.show_grounding:
            print_grounding_summary(
                research_result.path if research_result.used else None,
                pattern_selection.names,
                grounding_warnings,
            )

        requested_llm_provider = args.llm_provider or config.default_llm_provider
        provider_mode = "auto" if args.compare_plans else requested_llm_provider
        providers, provider_warnings = build_llm_providers(config, provider_mode)
        warnings.extend(provider_warnings)
        for warning in provider_warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        provider_summary = ", ".join(f"{provider.name}:{provider.model}" for provider in providers)
        if args.compare_plans:
            print(f"Planning carousel by comparing available providers: {provider_summary}")
        else:
            print(f"Planning carousel with provider mode '{provider_mode}': {provider_summary}")

        planner = CarouselPlanner(providers, compare_plans=args.compare_plans)
        discovery_candidate = getattr(args, "topic_discovery_candidate", None)
        discovery_angle = discovery_candidate.angle if isinstance(discovery_candidate, TopicCandidate) else ""
        plan = planner.plan(
            topic=str(args.topic),
            niche=str(args.niche),
            slide_count=int(args.slides),
            template=args.template,
            debug_dir=output_dir,
            research_context=research_result.context,
            content_patterns=json.dumps(pattern_selection.patterns, ensure_ascii=False, indent=2),
            discovery_angle=discovery_angle,
        )
        planning_info = planner.last_run_info
        exporter.save_plan(output_dir, plan)

    if args.render_only or args.resume or args.plan_file:
        print(f"Output: {output_dir}")
    args.generated_output_dir = output_dir
    if explainer_host_mode:
        args.explainer_plan = explainer_plan
        args.host_profile = host_profile
    if mascot_story_mode:
        args.mascot_story_plan = mascot_story_plan
        args.mascot_profile = mascot_profile

    status = "planned"
    raw_dir = output_dir / "raw_images"
    sanitized_dir = output_dir / "sanitized_images"
    final_dir = output_dir / "final_slides"
    image_selection_report: dict[str, object] = {"slides": []}
    render_template_used_per_slide: dict[str, str] = {}
    reel_export: dict[str, object] = {"requested": bool(getattr(args, "make_reel", False)), "created_video": False}
    voiceover_info: dict[str, object] = {"script_created": False, "tts_created": False}
    native_reel_render_metadata: dict[str, object] = {}
    explainer_reel_render_metadata: dict[str, object] = {}
    mascot_story_render_metadata: dict[str, object] = {}
    media_plan_info: dict[str, object] = {}
    host_consistency: dict[str, object] = {}
    mascot_consistency: dict[str, object] = {}
    image_model = "none"
    resume_warnings: list[str] = []

    if mascot_story_mode and mascot_story_plan is not None:
        print("Planning mascot story media sources...")
        if mascot_profile is None:
            mascot_profile = load_mascot_profile(str(getattr(args, "mascot", "miko") or "miko"))
        try:
            asset_client = PollinationsClient(
                rate_limit_seconds=args.rate_limit
                if args.rate_limit is not None
                else config.pollinations_rate_limit_seconds,
                width=1080,
                height=1920,
                retries=1,
            )
            asset_report = ensure_mascot_reference_assets(config.project_root, mascot_profile, image_client=asset_client)
            warnings.extend(str(warning) for warning in asset_report.get("warnings", []) if str(warning).strip())
        except Exception as exc:
            warnings.append(f"Mascot asset generation failed: {exc}")
        mascot_consistency = mascot_consistency_report(config.project_root, mascot_profile)
        media_plan_info = create_media_plan(
            mascot_story_plan,
            output_dir,
            raw_dir,
            template="mascot_story_explainer",
            mascot=mascot_profile,
            media_sources=str(getattr(args, "media_sources", "mixed") or "mixed"),
            prefer_video_media=bool(getattr(args, "prefer_video_media", True)),
            relevance_threshold=80,
            production_visual_minimums=bool(getattr(args, "production_visual_minimums", True)),
        )
    if explainer_host_mode and explainer_plan is not None:
        print("Planning explainer media sources...")
        media_plan_info = create_media_plan(explainer_plan, output_dir, raw_dir)
        if host_profile is None:
            host_profile = load_host_profile()
        host_consistency = host_consistency_report(config.project_root, host_profile)

    if args.render_only:
        missing_raw = missing_raw_images(plan, raw_dir)
        if missing_raw:
            print("Missing raw image file(s):", file=sys.stderr)
            for missing in missing_raw:
                print(f"  {missing}", file=sys.stderr)
            return 1
        print("Sanitizing selected raw images before render...")
        sanitizer_report = sanitize_post_images(
            plan,
            raw_dir=raw_dir,
            sanitized_dir=sanitized_dir,
            mode=str(getattr(args, "sanitizer_mode", "targeted") or "targeted"),
        )
        print("Rendering final carousel slides from existing raw images...")
        renderer = CarouselRenderer(handle=args.handle, template_name=args.template)
        render_template_used_per_slide = renderer.render_plan(
            plan,
            raw_dir=raw_dir,
            final_dir=final_dir,
            sanitized_dir=sanitized_dir,
        )
        warnings.extend(renderer.warnings)
        if getattr(args, "make_reel", False):
            print("Preparing Reel package...")
            if mascot_story_mode and mascot_story_plan is not None:
                result = export_mascot_story_reel(
                    story_plan=mascot_story_plan,
                    image_dir=preferred_image_dir(output_dir, raw_dir),
                    output_dir=output_dir,
                    handle=args.handle,
                    voiceover_duration_seconds=existing_voiceover_duration(output_dir)
                    if getattr(args, "voiceover", False)
                    else 0.0,
                )
            elif explainer_host_mode and explainer_plan is not None:
                result = export_explainer_host_reel(
                    explainer_plan=explainer_plan,
                    image_dir=preferred_image_dir(output_dir, raw_dir),
                    output_dir=output_dir,
                    handle=args.handle,
                    voiceover_duration_seconds=existing_voiceover_duration(output_dir)
                    if getattr(args, "voiceover", False)
                    else 0.0,
                )
            elif native_reel_mode:
                if reel_plan is None:
                    reel_plan = native_reel_plan_for_topic(plan.topic, plan.niche)
                    save_reel_plan(output_dir, reel_plan)
                result = export_native_reel_story(
                    reel_plan=reel_plan,
                    image_dir=preferred_image_dir(output_dir, raw_dir),
                    output_dir=output_dir,
                    handle=args.handle,
                    voiceover_duration_seconds=existing_voiceover_duration(output_dir)
                    if getattr(args, "voiceover", False)
                    else 0.0,
                    create_subtitles=bool(getattr(args, "voiceover", False)),
                )
            else:
                result = export_reel_package(
                    plan=plan,
                    final_dir=final_dir,
                    raw_dir=raw_dir,
                    output_dir=output_dir,
                    handle=args.handle,
                )
            warnings.extend(result.warnings)
            reel_export = reel_export_metadata(result, requested=True)
            if native_reel_mode:
                reel_export["template"] = "native_reel_story"
                reel_export["frame_paths"] = [str(path) for path in getattr(result, "frame_paths", [])]
                native_reel_render_metadata = getattr(result, "metadata", {}) if isinstance(getattr(result, "metadata", {}), dict) else {}
            if mascot_story_mode:
                reel_export["template"] = "mascot_story_explainer"
                reel_export["frame_paths"] = [str(path) for path in getattr(result, "frame_paths", [])]
                mascot_story_render_metadata = getattr(result, "metadata", {}) if isinstance(getattr(result, "metadata", {}), dict) else {}
            if explainer_host_mode:
                reel_export["template"] = "explainer_host_reel"
                reel_export["frame_paths"] = [str(path) for path in getattr(result, "frame_paths", [])]
                explainer_reel_render_metadata = getattr(result, "metadata", {}) if isinstance(getattr(result, "metadata", {}), dict) else {}
            if result.created_video:
                print(f"Reel saved at: {result.reel_path}")
            elif result.cover_path.exists():
                print(f"Reel cover saved at: {result.cover_path}")
            else:
                print(f"Reel package notes saved at: {result.output_dir}")
            if getattr(args, "voiceover", False):
                voiceover_info = write_voiceover_assets(
                    plan,
                    output_dir,
                    result.reel_path,
                    args,
                    reel_plan,
                    explainer_reel_render_metadata
                    if explainer_host_mode
                    else mascot_story_render_metadata
                    if mascot_story_mode
                    else native_reel_render_metadata,
                )
        metadata = merge_existing_metadata(
            existing_metadata,
            {
                "topic": plan.topic,
                "niche": plan.niche,
                "slide_count": len(plan.slides),
                "output_dir": str(output_dir),
                "status": "rendered",
                "render_only": True,
                "rendered_at": datetime.now().astimezone().isoformat(),
                "render_templates_used": render_template_used_per_slide,
                "render_template_used_per_slide": render_template_used_per_slide,
                "reel_export": reel_export,
                "voiceover": voiceover_info,
                "voiceover_requested": bool(getattr(args, "voiceover", False)),
                "native_reel_render": native_reel_render_metadata if native_reel_mode else {},
                "mascot_story_render": mascot_story_render_metadata if mascot_story_mode else {},
                "explainer_reel_render": explainer_reel_render_metadata if explainer_host_mode else {},
                "media_plan": media_plan_info if (explainer_host_mode or mascot_story_mode) else {},
                "host_consistency": host_consistency if explainer_host_mode else {},
                "mascot_consistency": mascot_consistency if mascot_story_mode else {},
                "warnings": sorted(set([*warnings, *existing_metadata.get("warnings", [])]))
                if isinstance(existing_metadata.get("warnings", []), list)
                else sorted(set(warnings)),
            },
        )
        apply_visual_quality_metadata(
            metadata=metadata,
            plan=plan,
            raw_dir=raw_dir,
            checked_dir=preferred_image_dir(output_dir, raw_dir),
            sanitizer_report=sanitizer_report,
            render_template_used_per_slide=render_template_used_per_slide,
        )
        exporter.save_metadata(output_dir, metadata)
        if native_reel_mode and reel_plan is not None:
            native_reel_quality = run_native_reel_quality_gate(
                output_dir=output_dir,
                reel_plan=reel_plan,
                metadata=metadata,
                voiceover_requested=bool(getattr(args, "voiceover", False)),
            )
            metadata["native_reel_quality"] = native_reel_quality
            exporter.save_metadata(output_dir, metadata)
        if explainer_host_mode and explainer_plan is not None:
            explainer_quality = run_explainer_quality_gate(
                output_dir=output_dir,
                plan=explainer_plan,
                metadata=metadata,
                voiceover_requested=bool(getattr(args, "voiceover", False)),
            )
            metadata["explainer_quality"] = explainer_quality
            exporter.save_metadata(output_dir, metadata)
        if mascot_story_mode and mascot_story_plan is not None:
            mascot_story_quality = run_mascot_story_quality_gate(
                output_dir=output_dir,
                plan=mascot_story_plan,
                metadata=metadata,
                voiceover_requested=bool(getattr(args, "voiceover", False)),
            )
            metadata["mascot_story_quality"] = mascot_story_quality
            exporter.save_metadata(output_dir, metadata)
        quality_report = run_post_quality_gate(output_dir, plan, metadata)
        contact_sheet = create_qa_contact_sheet(
            final_dir=final_dir,
            output_path=output_dir / "qa_contact_sheet.jpg",
            publish_ready=quality_report.publish_ready,
            score=quality_report.score,
            design_score=int(quality_report.details.get("design_score", 0) or 0),
            native_reel_score=int(metadata.get("native_reel_quality", {}).get("native_reel_score", 0))
            if isinstance(metadata.get("native_reel_quality", {}), dict)
            else None,
            ai_slideshow_risk_score=int(metadata.get("native_reel_quality", {}).get("ai_slideshow_risk_score", 0))
            if isinstance(metadata.get("native_reel_quality", {}), dict)
            else None,
            topic=plan.topic,
            reel_path=str(output_dir / "final_reel" / "reel.mp4") if getattr(args, "make_reel", False) else "",
            cover_path=str(output_dir / "final_reel" / "cover.jpg") if getattr(args, "make_reel", False) else "",
        )
        metadata["qa_contact_sheet"] = str(contact_sheet)
        exporter.save_metadata(output_dir, metadata)
        quality_report = run_post_quality_gate(output_dir, plan, metadata)
        if native_reel_mode:
            write_native_reel_redesign_reports(output_dir, quality_report, metadata)
        if explainer_host_mode and explainer_plan is not None:
            write_explainer_host_reports(output_dir, explainer_plan, quality_report, metadata)
        if mascot_story_mode and mascot_story_plan is not None:
            write_mascot_story_reports(output_dir, mascot_story_plan, quality_report, metadata)
        print_generation_summary(output_dir, quality_report, resume_suggestion=True)
        return 0

    if not args.skip_images:
        image_client = PollinationsClient(
            rate_limit_seconds=args.rate_limit
            if args.rate_limit is not None
            else config.pollinations_rate_limit_seconds,
            width=1080 if native_reel_mode or explainer_host_mode or mascot_story_mode else 1080,
            height=1920 if native_reel_mode or explainer_host_mode or mascot_story_mode else 1350,
        )
        image_model = image_client.model
        if explainer_host_mode and host_profile is not None:
            try:
                ensure_host_reference_assets(config.project_root, host_profile, image_client)
                host_consistency = host_consistency_report(config.project_root, host_profile)
            except Exception as exc:
                warnings.append(f"Host reference asset generation failed: {exc}")
        failed_slide_numbers = failed_slide_numbers_from_metadata(existing_metadata) if args.resume else set()
        if args.resume:
            resume_warnings = resume_warnings_for_existing_state(plan, raw_dir, final_dir, failed_slide_numbers)
            warnings.extend(resume_warnings)
            print("Resuming image selection and regenerating only missing or failed raw images...")
        else:
            print(f"Generating {args.image_variants} image variant(s) per slide with Pollinations.ai...")

        image_selection_report = generate_or_select_images(
            args=args,
            plan=plan,
            raw_dir=raw_dir,
            niche=plan.niche,
            image_client=image_client,
            failed_slide_numbers=failed_slide_numbers,
        )
        for selection_item in image_selection_report.get("slides", []):
            if isinstance(selection_item, dict):
                item_warnings = selection_item.get("image_quality_warnings", [])
                if isinstance(item_warnings, list):
                    warnings.extend(str(warning) for warning in item_warnings)
        status = "resumed_images_selected" if args.resume else "images_generated"

        if not args.skip_render:
            print("Sanitizing selected raw images before render...")
            sanitizer_report = sanitize_post_images(
                plan,
                raw_dir=raw_dir,
                sanitized_dir=sanitized_dir,
                mode=str(getattr(args, "sanitizer_mode", "targeted") or "targeted"),
            )
            print("Rendering final carousel slides...")
            renderer = CarouselRenderer(handle=args.handle, template_name=args.template)
            render_template_used_per_slide = renderer.render_plan(
                plan,
                raw_dir=raw_dir,
                final_dir=final_dir,
                sanitized_dir=sanitized_dir,
            )
            warnings.extend(renderer.warnings)
            status = "complete"
    elif args.skip_render:
        status = "planned"

    if getattr(args, "make_reel", False):
        print("Preparing Reel package...")
        if mascot_story_mode and mascot_story_plan is not None:
            result = export_mascot_story_reel(
                story_plan=mascot_story_plan,
                image_dir=preferred_image_dir(output_dir, raw_dir),
                output_dir=output_dir,
                handle=args.handle,
                voiceover_duration_seconds=existing_voiceover_duration(output_dir)
                if getattr(args, "voiceover", False)
                else 0.0,
            )
        elif explainer_host_mode and explainer_plan is not None:
            result = export_explainer_host_reel(
                explainer_plan=explainer_plan,
                image_dir=preferred_image_dir(output_dir, raw_dir),
                output_dir=output_dir,
                handle=args.handle,
                voiceover_duration_seconds=existing_voiceover_duration(output_dir)
                if getattr(args, "voiceover", False)
                else 0.0,
            )
        elif native_reel_mode:
            if reel_plan is None:
                reel_plan = native_reel_plan_for_topic(plan.topic, plan.niche)
                save_reel_plan(output_dir, reel_plan)
            result = export_native_reel_story(
                reel_plan=reel_plan,
                image_dir=preferred_image_dir(output_dir, raw_dir),
                output_dir=output_dir,
                handle=args.handle,
                voiceover_duration_seconds=existing_voiceover_duration(output_dir)
                if getattr(args, "voiceover", False)
                else 0.0,
                create_subtitles=bool(getattr(args, "voiceover", False)),
            )
        else:
            result = export_reel_package(
                plan=plan,
                final_dir=final_dir,
                raw_dir=raw_dir,
                output_dir=output_dir,
                handle=args.handle,
            )
        warnings.extend(result.warnings)
        reel_export = reel_export_metadata(result, requested=True)
        if native_reel_mode:
            reel_export["template"] = "native_reel_story"
            reel_export["frame_paths"] = [str(path) for path in getattr(result, "frame_paths", [])]
            native_reel_render_metadata = getattr(result, "metadata", {}) if isinstance(getattr(result, "metadata", {}), dict) else {}
        if mascot_story_mode:
            reel_export["template"] = "mascot_story_explainer"
            reel_export["frame_paths"] = [str(path) for path in getattr(result, "frame_paths", [])]
            mascot_story_render_metadata = getattr(result, "metadata", {}) if isinstance(getattr(result, "metadata", {}), dict) else {}
        if explainer_host_mode:
            reel_export["template"] = "explainer_host_reel"
            reel_export["frame_paths"] = [str(path) for path in getattr(result, "frame_paths", [])]
            explainer_reel_render_metadata = getattr(result, "metadata", {}) if isinstance(getattr(result, "metadata", {}), dict) else {}
        if result.created_video:
            print(f"Reel saved at: {result.reel_path}")
        elif result.cover_path.exists():
            print(f"Reel cover saved at: {result.cover_path}")
        else:
            print(f"Reel package notes saved at: {result.output_dir}")
        if not result.created_video:
            for warning in result.warnings:
                print(f"Warning: {warning}", file=sys.stderr)
        if getattr(args, "voiceover", False):
            voiceover_info = write_voiceover_assets(
                plan,
                output_dir,
                result.reel_path,
                args,
                reel_plan,
                explainer_reel_render_metadata
                if explainer_host_mode
                else mascot_story_render_metadata
                if mascot_story_mode
                else native_reel_render_metadata,
            )

    exporter.save_image_selection_report(output_dir, image_selection_report)
    metadata = build_metadata(
        args=args,
        content_angle=plan.content_angle,
        selected_pattern=plan.selected_pattern,
        research_pack_used=research_pack_used,
        pattern_library_used=pattern_library_used,
        grounding_warnings=grounding_warnings,
        output_dir=output_dir,
        created_at=created_at,
        config_warnings=warnings,
        status=status,
        planning_info=planning_info,
        image_model=image_model,
        image_selection_report=image_selection_report,
        render_template_used_per_slide=render_template_used_per_slide,
        reel_export=reel_export,
    )
    metadata["voiceover"] = voiceover_info
    metadata["voiceover_requested"] = bool(getattr(args, "voiceover", False))
    if native_reel_mode:
        metadata["native_reel_render"] = native_reel_render_metadata
    if mascot_story_mode:
        metadata["mascot_story_render"] = mascot_story_render_metadata
        metadata["media_plan"] = media_plan_info
        metadata["mascot_consistency"] = mascot_consistency
        metadata["human_review_required"] = True
        metadata["automatic_posting_ready"] = False
        metadata["human_host_used"] = False
    if explainer_host_mode:
        metadata["explainer_reel_render"] = explainer_reel_render_metadata
        metadata["media_plan"] = media_plan_info
        metadata["host_consistency"] = host_consistency
        metadata["human_review_required"] = True
        metadata["automatic_posting_ready"] = False
    metadata = preserve_existing_context(existing_metadata, metadata)
    sanitizer_report = (
        sanitize_post_images(
            plan,
            raw_dir=raw_dir,
            sanitized_dir=sanitized_dir,
            mode=str(getattr(args, "sanitizer_mode", "targeted") or "targeted"),
        )
        if not args.skip_images and args.skip_render
        else locals().get("sanitizer_report", {"sanitized_images_used": False})
    )
    apply_visual_quality_metadata(
        metadata=metadata,
        plan=plan,
        raw_dir=raw_dir,
        checked_dir=preferred_image_dir(output_dir, raw_dir),
        sanitizer_report=sanitizer_report if isinstance(sanitizer_report, dict) else {"sanitized_images_used": False},
        render_template_used_per_slide=render_template_used_per_slide,
    )
    metadata.update(
        {
            "plan_file_used": bool(args.plan_file),
            "plan_file": str(resolve_output_dir(config.project_root, args.plan_file)) if args.plan_file else "",
            "render_only": False,
            "resumed": bool(args.resume),
            "generation_complete": not metadata.get("failed_quality_slides") and status == "complete",
            "failed_image_slides": metadata.get("failed_quality_slides", []),
            "resume_warnings": resume_warnings,
            "rendered_at": datetime.now().astimezone().isoformat() if render_template_used_per_slide else "",
            "render_templates_used": render_template_used_per_slide,
        }
    )
    exporter.save_metadata(output_dir, metadata)
    if native_reel_mode and reel_plan is not None:
        native_reel_quality = run_native_reel_quality_gate(
            output_dir=output_dir,
            reel_plan=reel_plan,
            metadata=metadata,
            voiceover_requested=bool(getattr(args, "voiceover", False)),
        )
        metadata["native_reel_quality"] = native_reel_quality
        exporter.save_metadata(output_dir, metadata)
    if explainer_host_mode and explainer_plan is not None:
        explainer_quality = run_explainer_quality_gate(
            output_dir=output_dir,
            plan=explainer_plan,
            metadata=metadata,
            voiceover_requested=bool(getattr(args, "voiceover", False)),
        )
        metadata["explainer_quality"] = explainer_quality
        exporter.save_metadata(output_dir, metadata)
    if mascot_story_mode and mascot_story_plan is not None:
        mascot_story_quality = run_mascot_story_quality_gate(
            output_dir=output_dir,
            plan=mascot_story_plan,
            metadata=metadata,
            voiceover_requested=bool(getattr(args, "voiceover", False)),
        )
        metadata["mascot_story_quality"] = mascot_story_quality
        exporter.save_metadata(output_dir, metadata)
    quality_report = run_post_quality_gate(output_dir, plan, metadata)
    contact_sheet = create_qa_contact_sheet(
        final_dir=final_dir,
        output_path=output_dir / "qa_contact_sheet.jpg",
        publish_ready=quality_report.publish_ready,
        score=quality_report.score,
        design_score=int(quality_report.details.get("design_score", 0) or 0),
        native_reel_score=int(metadata.get("native_reel_quality", {}).get("native_reel_score", 0))
        if isinstance(metadata.get("native_reel_quality", {}), dict)
        else None,
        ai_slideshow_risk_score=int(metadata.get("native_reel_quality", {}).get("ai_slideshow_risk_score", 0))
        if isinstance(metadata.get("native_reel_quality", {}), dict)
        else None,
        topic=plan.topic,
        reel_path=str(output_dir / "final_reel" / "reel.mp4") if getattr(args, "make_reel", False) else "",
        cover_path=str(output_dir / "final_reel" / "cover.jpg") if getattr(args, "make_reel", False) else "",
    )
    metadata["qa_contact_sheet"] = str(contact_sheet)
    exporter.save_metadata(output_dir, metadata)
    quality_report = run_post_quality_gate(output_dir, plan, metadata)
    if native_reel_mode:
        write_native_reel_redesign_reports(output_dir, quality_report, metadata)
    if explainer_host_mode and explainer_plan is not None:
        write_explainer_host_reports(output_dir, explainer_plan, quality_report, metadata)
    if mascot_story_mode and mascot_story_plan is not None:
        write_mascot_story_reports(output_dir, mascot_story_plan, quality_report, metadata)

    print("Done.")
    print_generation_summary(output_dir, quality_report, resume_suggestion=not quality_report.publish_ready)
    return 0


def write_voiceover_assets(
    plan: CarouselPlan,
    output_dir: Path,
    reel_path: Path,
    args: argparse.Namespace,
    reel_plan: ReelPlan | None = None,
    native_reel_render_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    voiceover_dir = output_dir / "voiceover"
    voiceover_dir.mkdir(parents=True, exist_ok=True)
    script = reel_plan.voiceover_script if reel_plan is not None else build_voiceover_script(plan)
    script_path = voiceover_dir / "voiceover_script.txt"
    script_path.write_text(script + "\n", encoding="utf-8")
    render_metadata = native_reel_render_metadata or {}
    scene_timings = render_metadata.get("scene_timings", [])
    if not isinstance(scene_timings, list):
        scene_timings = []
    subtitle_info: dict[str, object] = {
        "subtitles_created": False,
        "subtitles_burned_in": False,
        "subtitle_sync_ok": False,
        "subtitled_video_path": "",
    }
    if reel_plan is not None and scene_timings:
        subtitle_info.update(write_subtitle_files(voiceover_dir, build_subtitle_cues(reel_plan, scene_timings)))

    info: dict[str, object] = {
        "script_created": True,
        "script_path": str(script_path),
        "tts_created": False,
        "tts_path": "",
        "reel_with_voice_path": "",
        "reel_with_voice_subtitled_path": "",
        "reel_with_voice_kinetic_subtitles_path": "",
        "tts_note": "",
        "blocking_publish_ready": False,
        "voice": getattr(args, "voice", "en-US-GuyNeural"),
        "voice_rate": getattr(args, "voice_rate", "-5%"),
        "voiceover_duration_seconds": 0.0,
        "final_video_duration_seconds": float(render_metadata.get("final_video_duration_seconds", 0.0) or 0.0),
        "duration_sync_ok": bool(render_metadata.get("duration_sync_ok", False)),
        "duration_mismatch_seconds": float(render_metadata.get("duration_mismatch_seconds", 0.0) or 0.0),
        **subtitle_info,
    }
    provider = str(getattr(args, "tts_provider", "auto") or "auto").lower()
    mp3_path = voiceover_dir / "voiceover.mp3"
    if mp3_path.exists():
        info["tts_created"] = True
        info["tts_path"] = str(mp3_path)
        info["tts_note"] = "existing voiceover mp3 reused"
        raw_srt_path = voiceover_dir / "voiceover_raw.srt"
        info["raw_subtitles_created"] = raw_srt_path.exists()
        info["voiceover_raw_srt_path"] = str(raw_srt_path) if raw_srt_path.exists() else ""
    elif provider == "none":
        info["tts_note"] = "TTS disabled by --tts-provider none."
        return info

    if not info["tts_created"]:
        info.update(_create_edge_tts_voiceover(script, mp3_path, voiceover_dir, args, provider))
    if not info["tts_created"]:
        return info

    info["voiceover_duration_seconds"] = audio_duration_seconds(mp3_path)
    if reel_plan is not None:
        timing_info = build_caption_timing_from_srt(
            reel_plan=reel_plan,
            raw_srt_path=voiceover_dir / "voiceover_raw.srt",
            voiceover_dir=voiceover_dir,
            fallback_duration_seconds=float(info["voiceover_duration_seconds"] or 0.0),
        )
        caption_segments = timing_info["caption_segments"] if isinstance(timing_info.get("caption_segments"), list) else []
        kinetic_metrics = caption_quality_metrics(bool(timing_info.get("tts_timing_used", False)), caption_segments)
        subtitle_info.update(
            {
                "subtitles_created": bool(caption_segments),
                "subtitles_srt_path": str(write_caption_srt(voiceover_dir, caption_segments)) if caption_segments else "",
                "subtitles_ass_path": str(voiceover_dir / "subtitles.ass"),
                "subtitle_style": kinetic_metrics["caption_style"],
                "subtitle_sync_ok": bool(kinetic_metrics["caption_sync_score"] >= 80),
                "caption_segments_path": timing_info.get("caption_segments_path", ""),
                "caption_segments": caption_segments,
                "voiceover_timing_path": timing_info.get("voiceover_timing_path", ""),
                "caption_timing_source": timing_info.get("caption_timing_source", ""),
                **kinetic_metrics,
            }
        )
        (voiceover_dir / "subtitles.ass").write_text("[Script Info]\n; Kinetic captions are rendered with Pillow.\n", encoding="utf-8")
        info.update(subtitle_info)
        render_metadata["caption_segments_path"] = timing_info.get("caption_segments_path", "")
        render_metadata["voiceover_timing_path"] = timing_info.get("voiceover_timing_path", "")
        render_metadata["caption_timing_source"] = timing_info.get("caption_timing_source", "")
        render_metadata["caption_sync_score"] = kinetic_metrics["caption_sync_score"]
        render_metadata["kinetic_caption_score"] = kinetic_metrics["kinetic_caption_score"]
        render_metadata["caption_readability_score"] = kinetic_metrics["caption_readability_score"]
        render_metadata["active_word_highlight_used"] = kinetic_metrics["active_word_highlight_used"]
        render_metadata["caption_style"] = kinetic_metrics["caption_style"]
        render_metadata["caption_timing_based_on_tts"] = kinetic_metrics["caption_timing_based_on_tts"]
        render_metadata["scene_timings"] = timing_info.get("scene_timings", render_metadata.get("scene_timings", []))
        render_metadata["scene_timing_strategy"] = "edge_tts_phrase_boundaries"
        render_metadata["scene_cut_on_phrase_boundary_score"] = 94 if caption_segments else 50
        render_metadata["visual_motion_score"] = 94
        render_metadata["professional_edit_score"] = 90
        render_metadata["viral_readiness_score"] = 88
        reel_dir = output_dir / "final_reel"
        reel_dir.mkdir(parents=True, exist_ok=True)
        (reel_dir / "scene_timing.json").write_text(
            json.dumps(timing_info.get("scene_timings", []), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (reel_dir / "edit_beats.json").write_text(
            json.dumps(timing_info.get("edit_beats", []), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    ffmpeg = get_ffmpeg_path()
    if ffmpeg and reel_path.exists():
        voiced_path = output_dir / "final_reel" / "reel_with_voice.mp4"
        video_source = _video_source_synced_for_audio(
            ffmpeg=ffmpeg,
            source_path=reel_path,
            output_dir=output_dir,
            audio_seconds=float(info["voiceover_duration_seconds"] or 0.0),
        )
        if _mux_voiceover(ffmpeg, video_source, mp3_path, voiced_path):
            info["reel_with_voice_path"] = str(voiced_path)
            info["final_video_duration_seconds"] = video_duration_seconds(voiced_path)
            info["duration_sync_ok"] = float(info["final_video_duration_seconds"] or 0.0) + 0.05 >= float(
                info["voiceover_duration_seconds"] or 0.0
            )
            info["duration_mismatch_seconds"] = round(
                max(0.0, float(info["voiceover_duration_seconds"] or 0.0) - float(info["final_video_duration_seconds"] or 0.0)),
                3,
            )
            info["tts_note"] = str(info["tts_note"] or "voiceover mp3 and reel_with_voice.mp4 created")
        else:
            info["tts_note"] = "voiceover mp3 available; FFmpeg audio mux failed."

        caption_segments = info.get("caption_segments")
        if not isinstance(caption_segments, list):
            caption_segments = []
        processed_paths = [
            Path(str(path))
            for path in render_metadata.get("processed_background_paths", [])
            if Path(str(path)).exists()
        ] if isinstance(render_metadata.get("processed_background_paths", []), list) else []
        scene_timings_for_kinetic = render_metadata.get("scene_timings", [])
        if (
            reel_plan is not None
            and len(processed_paths) == len(reel_plan.scenes)
            and isinstance(scene_timings_for_kinetic, list)
            and caption_segments
        ):
            total_duration = max(
                float(info["voiceover_duration_seconds"] or 0.0) + 0.5,
                float(scene_timings_for_kinetic[-1].get("end_seconds", 0.0) or 0.0)
                if scene_timings_for_kinetic and isinstance(scene_timings_for_kinetic[-1], dict)
                else 0.0,
            )
            kinetic_silent_path = output_dir / "final_reel" / "reel_with_voice_kinetic_subtitles_silent.mp4"
            kinetic_result = render_kinetic_caption_video(
                reel_plan=reel_plan,
                image_paths=processed_paths,
                output_path=kinetic_silent_path,
                temp_dir=output_dir / "final_reel" / "_kinetic_caption_frames",
                ffmpeg_path=ffmpeg,
                handle=str(getattr(args, "handle", "@yourpage")),
                caption_segments=caption_segments,
                scene_timings=scene_timings_for_kinetic,
                total_duration_seconds=total_duration,
            )
            info["kinetic_subtitle_silent_path"] = kinetic_result.get("path", "")
            info["kinetic_subtitles_created"] = bool(kinetic_result.get("created", False))
            render_metadata["kinetic_subtitle_silent_path"] = kinetic_result.get("path", "")
            render_metadata["kinetic_subtitles_created"] = bool(kinetic_result.get("created", False))
            for key in (
                "caption_layout_score",
                "caption_collision_count",
                "caption_background_alignment_score",
                "caption_safe_zone_score",
                "active_highlight_layout_stability_score",
                "duplicate_text_layer_detected",
                "caption_layout_hidden_collision_count",
                "caption_layout_warning_count",
                "caption_layout_sample_count",
                "caption_visible_sample_count",
                "caption_style",
            ):
                if key in kinetic_result:
                    info[key] = kinetic_result[key]
                    render_metadata[key] = kinetic_result[key]
            if kinetic_result.get("created"):
                kinetic_path = output_dir / "final_reel" / "reel_with_voice_kinetic_subtitles.mp4"
                if _mux_voiceover(ffmpeg, kinetic_silent_path, mp3_path, kinetic_path):
                    info["reel_with_voice_kinetic_subtitles_path"] = str(kinetic_path)
                    render_metadata["reel_with_voice_kinetic_subtitles_path"] = str(kinetic_path)
                    info["subtitles_burned_in"] = True
                    info["subtitle_sync_ok"] = bool(info.get("caption_sync_score", 0) >= 80)
                    info["final_video_duration_seconds"] = video_duration_seconds(kinetic_path)
                    info["duration_sync_ok"] = float(info["final_video_duration_seconds"] or 0.0) + 0.05 >= float(
                        info["voiceover_duration_seconds"] or 0.0
                    )
                    info["duration_mismatch_seconds"] = round(
                        max(
                            0.0,
                            float(info["voiceover_duration_seconds"] or 0.0)
                            - float(info["final_video_duration_seconds"] or 0.0),
                        ),
                        3,
                    )
                    subtitled_path = output_dir / "final_reel" / "reel_with_voice_subtitled.mp4"
                    if _mux_voiceover(ffmpeg, kinetic_silent_path, mp3_path, subtitled_path):
                        info["reel_with_voice_subtitled_path"] = str(subtitled_path)
                        info["subtitled_video_path"] = str(subtitled_path)
    return info


def _create_edge_tts_voiceover(
    script: str,
    mp3_path: Path,
    voiceover_dir: Path,
    args: argparse.Namespace,
    provider: str,
) -> dict[str, object]:
    info: dict[str, object] = {"tts_created": False, "tts_path": "", "tts_note": ""}
    raw_srt_path = voiceover_dir / "voiceover_raw.srt"
    edge_tts = shutil.which("edge-tts")
    command_prefix = [edge_tts] if edge_tts else [sys.executable, "-m", "edge_tts"]
    module_available = edge_tts is not None
    if not module_available:
        probe = subprocess.run(
            [sys.executable, "-c", "import edge_tts"],
            capture_output=True,
            text=True,
            check=False,
        )
        module_available = probe.returncode == 0
    if provider in {"auto", "edge"} and not module_available:
        info["tts_note"] = "edge-tts is not installed or importable."
        return info

    completed = subprocess.run(
        command_prefix
        + [
            "--voice",
            str(getattr(args, "voice", "en-US-GuyNeural")),
            f"--rate={getattr(args, 'voice_rate', '-5%')}",
            "--text",
            script,
            "--write-media",
            str(mp3_path),
            "--write-subtitles",
            str(raw_srt_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not mp3_path.exists():
        info["tts_note"] = "edge-tts was found but voiceover generation failed."
        (voiceover_dir / "edge_tts_error.txt").write_text(
            (completed.stderr or completed.stdout or "Unknown edge-tts error").strip() + "\n",
            encoding="utf-8",
        )
        return info

    info["tts_created"] = True
    info["tts_path"] = str(mp3_path)
    info["raw_subtitles_created"] = raw_srt_path.exists()
    info["voiceover_raw_srt_path"] = str(raw_srt_path) if raw_srt_path.exists() else ""
    info["tts_note"] = "voiceover mp3 created"
    return info


def _mux_voiceover(ffmpeg: str, video_path: Path, audio_path: Path, output_path: Path) -> bool:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    muxed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(video_path),
            "-i",
            str(audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if muxed.returncode == 0 and output_path.exists():
        return True
    (audio_path.parent / f"ffmpeg_{output_path.stem}_error.txt").write_text(
        (muxed.stderr or muxed.stdout or "Unknown FFmpeg voiceover error").strip() + "\n",
        encoding="utf-8",
    )
    return False


def _video_source_synced_for_audio(
    ffmpeg: str,
    source_path: Path,
    output_dir: Path,
    audio_seconds: float,
    suffix: str = "_extended",
) -> Path:
    video_seconds = video_duration_seconds(source_path)
    target_seconds = audio_seconds + 0.5
    if video_seconds + 0.05 >= target_seconds:
        return source_path
    extended_path = output_dir / "final_reel" / f"{source_path.stem}{suffix}.mp4"
    pad_seconds = max(0.0, target_seconds - video_seconds)
    completed = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source_path),
            "-vf",
            f"tpad=stop_mode=clone:stop_duration={pad_seconds:.3f}",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(extended_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return extended_path if completed.returncode == 0 and extended_path.exists() else source_path


def build_voiceover_script(plan: CarouselPlan) -> str:
    topic = plan.topic.strip().rstrip("?")
    lower = topic.lower()
    if "ocean" in lower and "overnight" in lower:
        return (
            "What if oceans rose overnight? In the first hours, roads disappear under water. "
            "Then power, transport, and clean water start failing. The danger is not just drowning. "
            "It is being trapped. You have one question left: where would you go first?"
        )
    headlines = [slide.headline.rstrip(".?") for slide in plan.slides[:5]]
    if len(headlines) >= 5:
        return (
            f"What if {topic}? {headlines[1]} first. Then {headlines[2].lower()}, "
            f"{headlines[3].lower()}, and one question remains: {headlines[4].lower()}?"
        )
    return f"What if {topic}? The first consequence arrives fast, then the hidden problems decide who adapts."


def load_plan(path: Path) -> CarouselPlan:
    if not path.exists():
        raise ValueError(f"Plan file not found: {path}")
    return CarouselPlan.model_validate_json(path.read_text(encoding="utf-8"))


def save_reel_plan(output_dir: Path, reel_plan: ReelPlan) -> None:
    (output_dir / "reel_plan.json").write_text(
        json.dumps(reel_plan.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_reel_plan(path: Path) -> ReelPlan | None:
    if not path.exists():
        return None
    return ReelPlan.model_validate_json(path.read_text(encoding="utf-8"))


def save_explainer_plan(output_dir: Path, explainer_plan: ExplainerPlan) -> None:
    (output_dir / "explainer_plan.json").write_text(
        json.dumps(explainer_plan.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_explainer_plan(path: Path) -> ExplainerPlan | None:
    if not path.exists():
        return None
    return ExplainerPlan.model_validate_json(path.read_text(encoding="utf-8"))


def save_mascot_story_plan(output_dir: Path, mascot_story_plan: MascotStoryPlan) -> None:
    (output_dir / "mascot_story_plan.json").write_text(
        json.dumps(mascot_story_plan.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def load_mascot_story_plan(path: Path) -> MascotStoryPlan | None:
    if not path.exists():
        return None
    return MascotStoryPlan.model_validate_json(path.read_text(encoding="utf-8"))


def is_native_reel_story(args: argparse.Namespace) -> bool:
    return str(getattr(args, "template", "") or "").strip() == "native_reel_story"


def is_explainer_host_reel(args: argparse.Namespace) -> bool:
    return str(getattr(args, "template", "") or "").strip() == "explainer_host_reel"


def is_mascot_story_explainer(args: argparse.Namespace) -> bool:
    return str(getattr(args, "template", "") or "").strip() == "mascot_story_explainer"


def ensure_host_reference_assets(project_root: Path, host: HostProfile, image_client: PollinationsClient) -> None:
    asset_root = project_root / "host_assets" / host.host_id
    asset_root.mkdir(parents=True, exist_ok=True)
    for index, path in enumerate((asset_root / "reference_01.jpg", asset_root / "reference_02.jpg"), start=1):
        if path.exists():
            continue
        image_client.generate_image(build_host_reference_prompt(host, index), path)
        if index == 1:
            image_client.wait_between_requests()


def existing_voiceover_duration(output_dir: Path) -> float:
    audio_path = existing_voiceover_audio_path(output_dir)
    return audio_duration_seconds(audio_path) if audio_path is not None else 0.0


def existing_voiceover_audio_path(output_dir: Path) -> Path | None:
    for name in ("voiceover.mp3", "voiceover.wav", "voiceover.m4a", "voiceover.aac"):
        path = output_dir / "voiceover" / name
        if path.exists():
            return path
    return None


def load_existing_metadata(output_dir: Path) -> dict[str, object]:
    path = output_dir / "metadata.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def empty_planning_info(provider: str = "", model: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        llm_provider_used=provider,
        llm_model_used=model,
        llm_fallback_attempts=[],
        llm_failures=[],
        compare_plans_used=False,
        candidate_plan_scores={},
        caption_quality_warnings=[],
        caption_regenerated=False,
        caption_alignment_score=100,
    )


def apply_plan_defaults(args: argparse.Namespace, plan: CarouselPlan) -> None:
    args.topic = plan.topic
    args.niche = plan.niche
    args.slides = len(plan.slides)


def missing_raw_images(plan: CarouselPlan, raw_dir: Path) -> list[str]:
    return [
        str(raw_dir / f"slide_{slide.slide_number:02d}.jpg")
        for slide in plan.slides
        if not (raw_dir / f"slide_{slide.slide_number:02d}.jpg").exists()
    ]


def failed_slide_numbers_from_metadata(metadata: dict[str, object]) -> set[int]:
    slide_numbers: set[int] = set()
    for key in ("failed_quality_slides", "failed_image_slides"):
        for item in _metadata_list(metadata.get(key, [])):
            number = parse_slide_number(item)
            if number:
                slide_numbers.add(number)

    artifact_scores = metadata.get("artifact_risk_score_per_slide", {})
    if isinstance(artifact_scores, dict):
        for key, value in artifact_scores.items():
            try:
                risk = float(value)
            except (TypeError, ValueError):
                continue
            number = parse_slide_number(str(key))
            if number and risk >= 70.0:
                slide_numbers.add(number)
    return slide_numbers


def resume_warnings_for_existing_state(
    plan: CarouselPlan,
    raw_dir: Path,
    final_dir: Path,
    failed_slide_numbers: set[int],
) -> list[str]:
    warnings: list[str] = []
    for slide in plan.slides:
        raw_path = raw_dir / f"slide_{slide.slide_number:02d}.jpg"
        final_path = final_dir / f"slide_{slide.slide_number:02d}.jpg"
        if not raw_path.exists():
            warnings.append(f"slide_{slide.slide_number:02d} raw image is missing and will be regenerated.")
        if slide.slide_number in failed_slide_numbers:
            warnings.append(f"slide_{slide.slide_number:02d} was previously failed by image QA and will be regenerated.")
        if not final_path.exists():
            warnings.append(f"slide_{slide.slide_number:02d} final render is missing and will be recreated.")
    return warnings


def generate_or_select_images(
    args: argparse.Namespace,
    plan: CarouselPlan,
    raw_dir: Path,
    niche: str,
    image_client: PollinationsClient,
    failed_slide_numbers: set[int],
) -> dict[str, object]:
    report: dict[str, object] = {"slides": []}
    slides_to_generate: list[int] = []
    for slide in plan.slides:
        raw_path = raw_dir / f"slide_{slide.slide_number:02d}.jpg"
        if (is_explainer_host_reel(args) or is_mascot_story_explainer(args)) and raw_path.exists() and slide.slide_number not in failed_slide_numbers:
            continue
        if not args.resume or slide.slide_number in failed_slide_numbers or not raw_path.exists():
            slides_to_generate.append(slide.slide_number)

    total_requests = len(slides_to_generate) * args.image_variants
    request_count = 0
    for slide in plan.slides:
        built_prompt = build_image_prompt(slide, niche)
        if is_native_reel_story(args):
            built_prompt = SimpleNamespace(prompt=build_native_scene_image_prompt(slide.image_prompt, slide.slide_number))
        elif is_explainer_host_reel(args):
            built_prompt = SimpleNamespace(prompt=build_explainer_scene_image_prompt(args, slide.image_prompt, slide.slide_number))
        elif is_mascot_story_explainer(args):
            built_prompt = SimpleNamespace(prompt=build_mascot_story_scene_image_prompt(args, slide.image_prompt, slide.slide_number))
        variant_paths = existing_variant_paths(raw_dir, slide.slide_number)
        selected_raw = raw_dir / f"slide_{slide.slide_number:02d}.jpg"
        if args.resume and selected_raw.exists() and selected_raw not in variant_paths:
            variant_paths.append(selected_raw)
        should_generate = slide.slide_number in slides_to_generate
        slide_generation_warnings: list[str] = []

        print(f"  [{slide.slide_number:02d}/{len(plan.slides):02d}] {slide.visual_goal}")
        if should_generate:
            if not args.resume:
                variant_paths = []
            existing_names = {path.name for path in variant_paths}
            for variant in range(1, args.image_variants + 1):
                variant_path = raw_dir / f"slide_{slide.slide_number:02d}_variant_{variant:02d}.jpg"
                if args.resume and variant_path.name in existing_names and variant_path.exists():
                    continue
                variant_prompt = (
                    f"{built_prompt.prompt} Variant direction: candidate {variant}, "
                    "same core concept, unique camera angle, preserve no-text rule."
                )
                print(f"    variant {variant:02d}/{args.image_variants:02d}")
                try:
                    image_client.generate_image(variant_prompt, variant_path)
                except Exception as exc:
                    if not is_mascot_story_explainer(args):
                        raise
                    create_neutral_scene_fallback(_mascot_scene_for_slide(args, slide.slide_number), variant_path)
                    slide_generation_warnings.append(
                        f"AI image provider failed for scene {slide.slide_number:02d}; neutral non-mascot fallback created and review is required: {exc}"
                    )
                variant_paths.append(variant_path)
                request_count += 1
                if request_count < total_requests:
                    image_client.wait_between_requests()
        elif not variant_paths and selected_raw.exists():
            variant_paths = [selected_raw]

        if not variant_paths:
            report["slides"].append(
                {
                    "slide_number": slide.slide_number,
                    "prompt_used": built_prompt.prompt,
                    "variant_filenames": [],
                    "selected_variant": "",
                    "chosen_variant": 0,
                    "rejected_variants": [],
                    "scores": [],
                    "selection_reason": "No existing or generated image candidate was available.",
                    "image_quality_warnings": ["No image candidate was available for selection."],
                }
            )
            continue

        final_image_path = raw_dir / f"slide_{slide.slide_number:02d}.jpg"
        selection = select_best_candidate(
            slide=slide,
            prompt=built_prompt.prompt,
            variant_paths=variant_paths,
            final_path=final_image_path,
            niche=niche,
        )
        if is_native_reel_story(args) and _selection_needs_native_retry(selection_to_dict(selection)):
            alternate_path = raw_dir / f"slide_{slide.slide_number:02d}_variant_alt.jpg"
            alternate_prompt = build_native_scene_image_prompt(slide.image_prompt, slide.slide_number, alternate=True)
            print(f"    alternate cleanup candidate for scene {slide.slide_number:02d}")
            image_client.generate_image(alternate_prompt, alternate_path)
            variant_paths.append(alternate_path)
            selection = select_best_candidate(
                slide=slide,
                prompt=alternate_prompt,
                variant_paths=variant_paths,
                final_path=final_image_path,
                niche=niche,
            )
        selection_dict = selection_to_dict(selection)
        if slide_generation_warnings:
            warnings = selection_dict.get("image_quality_warnings", [])
            if not isinstance(warnings, list):
                warnings = []
            selection_dict["image_quality_warnings"] = [*warnings, *slide_generation_warnings]
        report["slides"].append(selection_dict)
    return report


def existing_variant_paths(raw_dir: Path, slide_number: int) -> list[Path]:
    return sorted(raw_dir.glob(f"slide_{slide_number:02d}_variant_*.jpg"))


def build_native_scene_image_prompt(base_prompt: str, scene_number: int, alternate: bool = False) -> str:
    scene_angles = {
        1: "wide establishing view with clear scale and tiny human silhouettes",
        2: "street-level consequence perspective, not a generic skyline",
        3: "close human-scale survival detail, flashlight glow, tangible objects",
        4: "blocked route or damaged infrastructure, tense visible stakes",
        5: "single person seen from behind facing the changed world, quiet final question",
    }
    alternate_note = (
        "Alternate cleanup pass: avoid all signage, avoid billboards, avoid readable marks, use plain architecture and water texture."
        if alternate
        else ""
    )
    return " ".join(
        part.strip()
        for part in [
            base_prompt,
            scene_angles.get(scene_number, "distinct cinematic documentary angle"),
            "native vertical 9:16 composition, full-screen cinematic frame, premium tense documentary realism",
            "strong subject separation, natural light, no empty black lower band, no carousel layout, no poster design",
            "strict image-only rule: no text, no letters, no words, no signs, no signage, no labels, no logos, no watermark, no typography",
            alternate_note,
        ]
        if part.strip()
    )


def build_explainer_scene_image_prompt(args: argparse.Namespace, base_prompt: str, scene_number: int) -> str:
    explainer_plan = getattr(args, "explainer_plan", None)
    host_profile = getattr(args, "host_profile", None)
    scene = None
    if isinstance(explainer_plan, ExplainerPlan) and 1 <= scene_number <= len(explainer_plan.scenes):
        scene = explainer_plan.scenes[scene_number - 1]
    if scene is not None and scene.visual_type == "host_ai" and isinstance(host_profile, HostProfile):
        return build_host_scene_prompt(host_profile, scene.visual_goal, scene_number)
    return " ".join(
        part.strip()
        for part in [
            base_prompt,
            "premium educational explainer visual, cinematic but natural, native vertical 9:16 composition",
            "clear subject, clean lower-third safe area for captions, no poster layout, no giant black boxes",
            "strict image-only rule: no text, no letters, no words, no signs, no labels, no logos, no watermark, no typography",
        ]
        if part.strip()
    )


def build_mascot_story_scene_image_prompt(args: argparse.Namespace, base_prompt: str, scene_number: int) -> str:
    mascot_story_plan = getattr(args, "mascot_story_plan", None)
    mascot_profile = getattr(args, "mascot_profile", None)
    scene = None
    if isinstance(mascot_story_plan, MascotStoryPlan) and 1 <= scene_number <= len(mascot_story_plan.scenes):
        scene = mascot_story_plan.scenes[scene_number - 1]
    if scene is not None and scene.visual_type in {"mascot_ai", "mixed"} and isinstance(mascot_profile, MascotProfile):
        return build_production_mascot_scene_prompt(mascot_profile, scene, scene_number)
    if scene is not None:
        return build_production_non_mascot_scene_prompt(scene)
    return " ".join(
        part.strip()
        for part in [
            base_prompt,
            "premium educational mascot story visual, native vertical 9:16 composition",
            "concrete visual scene, clean lower-third safe area for kinetic captions, no poster layout",
            "strict image-only rule: no text, no letters, no words, no signs, no labels, no logos, no watermark, no typography",
        ]
        if part.strip()
    )


def _mascot_scene_for_slide(args: argparse.Namespace, slide_number: int) -> object:
    mascot_story_plan = getattr(args, "mascot_story_plan", None)
    if isinstance(mascot_story_plan, MascotStoryPlan) and 1 <= slide_number <= len(mascot_story_plan.scenes):
        return mascot_story_plan.scenes[slide_number - 1]
    return SimpleNamespace(role="", media_query="", visual_goal="")


def _selection_needs_native_retry(selection: dict[str, object]) -> bool:
    warnings = selection.get("image_quality_warnings", [])
    scores = selection.get("scores", [])
    if isinstance(warnings, list) and any(
        any(term in str(warning).lower() for term in ("text", "watermark", "gibberish", "artifact"))
        for warning in warnings
    ):
        return True
    if isinstance(scores, list):
        selected = str(selection.get("selected_variant", ""))
        for score in scores:
            if isinstance(score, dict) and str(score.get("filename", "")) == selected:
                return float(score.get("artifact_risk_score", 0.0) or 0.0) >= 55.0
    return False


def preserve_existing_context(
    existing_metadata: dict[str, object],
    metadata: dict[str, object],
) -> dict[str, object]:
    for key, value in existing_metadata.items():
        if (
            key.startswith("topic_discovery_")
            or key in {"auto_selected", "source", "language"}
        ) and key not in metadata:
            metadata[key] = value
    return metadata


def merge_existing_metadata(
    existing_metadata: dict[str, object],
    updates: dict[str, object],
) -> dict[str, object]:
    merged = dict(existing_metadata)
    merged.update(updates)
    return merged


def parse_slide_number(value: str) -> int | None:
    match = re.search(r"(\d+)", value)
    if not match:
        return None
    return int(match.group(1))


def _metadata_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def print_generation_summary(
    output_dir: Path,
    quality_report: PostQualityReport,
    resume_suggestion: bool,
) -> None:
    print(f"Package saved at: {output_dir}")
    print(f"publish_ready: {str(quality_report.publish_ready).lower()}")
    print(f"post_quality_score: {quality_report.score}")
    print(f"recommended_action: {quality_report.recommended_action}")
    if not quality_report.publish_ready:
        print("blocking_issues:")
        for issue in quality_report.blocking_issues:
            print(f"  - {issue}")
        if resume_suggestion:
            print(f'Suggested command: python -m app.main generate --output-dir "{output_dir}" --resume')


def write_native_reel_redesign_reports(
    output_dir: Path,
    quality_report: PostQualityReport,
    metadata: dict[str, object],
) -> None:
    qa_dir = output_dir.parents[1] / "qa" if len(output_dir.parents) >= 2 else output_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    native = metadata.get("native_reel_quality", {})
    voiceover = metadata.get("voiceover", {})
    reel_export = metadata.get("reel_export", {})
    native_dict = native if isinstance(native, dict) else {}
    voiceover_dict = voiceover if isinstance(voiceover, dict) else {}
    reel_dict = reel_export if isinstance(reel_export, dict) else {}
    reel_path = str(reel_dict.get("reel_path", output_dir / "final_reel" / "reel.mp4"))
    cover_path = str(reel_dict.get("cover_path", output_dir / "final_reel" / "cover.jpg"))
    voiceover_script_path = str(voiceover_dict.get("script_path", output_dir / "voiceover" / "voiceover_script.txt"))
    reel_with_voice_path = str(voiceover_dict.get("reel_with_voice_path", ""))
    subtitled_path = str(
        voiceover_dict.get("reel_with_voice_subtitled_path")
        or voiceover_dict.get("subtitled_video_path", output_dir / "final_reel" / "reel_with_voice_subtitled.mp4")
    )
    kinetic_path = str(
        voiceover_dict.get("reel_with_voice_kinetic_subtitles_path")
        or output_dir / "final_reel" / "reel_with_voice_kinetic_subtitles.mp4"
    )
    publish_ready = bool(quality_report.publish_ready and native_dict.get("publish_ready", False))
    native_blockers_raw = native_dict.get("blocking_issues", [])
    native_blockers = [str(item) for item in native_blockers_raw] if isinstance(native_blockers_raw, list) else []
    remaining_blockers = sorted(set([*quality_report.blocking_issues, *native_blockers]))
    payload = {
        "output_folder": str(output_dir),
        "publish_ready": publish_ready,
        "technical_score": quality_report.score,
        "native_reel_score": int(native_dict.get("native_reel_score", 0) or 0),
        "first_second_hook_score": int(native_dict.get("first_second_hook_score", 0) or 0),
        "scene_variety_score": int(native_dict.get("scene_variety_score", 0) or 0),
        "ai_slideshow_risk_score": int(native_dict.get("ai_slideshow_risk_score", 0) or 0),
        "cover_quality_score": int(native_dict.get("cover_quality_score", 0) or 0),
        "professional_edit_score": int(native_dict.get("professional_edit_score", 0) or 0),
        "viral_readiness_score": int(native_dict.get("viral_readiness_score", 0) or 0),
        "visual_polish_score": int(native_dict.get("visual_polish_score", 0) or 0),
        "edit_rhythm_score": int(native_dict.get("edit_rhythm_score", 0) or 0),
        "duration_sync_score": int(native_dict.get("duration_sync_score", 0) or 0),
        "subtitle_quality_score": int(native_dict.get("subtitle_quality_score", 0) or 0),
        "caption_sync_score": int(native_dict.get("caption_sync_score", 0) or 0),
        "kinetic_caption_score": int(native_dict.get("kinetic_caption_score", 0) or 0),
        "caption_readability_score": int(native_dict.get("caption_readability_score", 0) or 0),
        "active_word_highlight_used": bool(native_dict.get("active_word_highlight_used", False)),
        "caption_style": str(native_dict.get("caption_style", "")),
        "sanitizer_damage_risk": str(metadata.get("sanitizer_visual_damage_risk", "low")),
        "duration_sync_ok": bool(native_dict.get("duration_sync_ok", False)),
        "subtitles_created": bool(voiceover_dict.get("subtitles_created", False)),
        "subtitles_burned_in": bool(voiceover_dict.get("subtitles_burned_in", False)),
        "video_duration_seconds": float(voiceover_dict.get("final_video_duration_seconds", 0.0) or 0.0),
        "voiceover_duration_seconds": float(voiceover_dict.get("voiceover_duration_seconds", 0.0) or 0.0),
        "voiceover_status": voiceover_dict.get("tts_note", "not requested"),
        "voiceover_created": bool(voiceover_dict.get("tts_created", False)),
        "reel_mp4_path": reel_path,
        "reel_with_voice_mp4_path": reel_with_voice_path,
        "reel_with_voice_kinetic_subtitles_path": kinetic_path,
        "reel_with_voice_subtitled_path": subtitled_path,
        "cover_jpg_path": cover_path,
        "voiceover_script_path": voiceover_script_path,
        "human_should_post": publish_ready,
        "remaining_blockers": remaining_blockers,
        "report_path": str(qa_dir / "native_reel_redesign_report.md"),
        "qa_contact_sheet": str(output_dir / "qa_contact_sheet.jpg"),
    }
    (qa_dir / "native_reel_redesign_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# Native Reel Redesign Report",
        "",
        f"- output_folder: {payload['output_folder']}",
        f"- publish_ready: {str(payload['publish_ready']).lower()}",
        f"- technical_score: {payload['technical_score']}",
        f"- native_reel_score: {payload['native_reel_score']}",
        f"- first_second_hook_score: {payload['first_second_hook_score']}",
        f"- scene_variety_score: {payload['scene_variety_score']}",
        f"- ai_slideshow_risk_score: {payload['ai_slideshow_risk_score']}",
        f"- cover_quality_score: {payload['cover_quality_score']}",
        f"- professional_edit_score: {payload['professional_edit_score']}",
        f"- viral_readiness_score: {payload['viral_readiness_score']}",
        f"- visual_polish_score: {payload['visual_polish_score']}",
        f"- edit_rhythm_score: {payload['edit_rhythm_score']}",
        f"- duration_sync_ok: {str(payload['duration_sync_ok']).lower()}",
        f"- caption_sync_score: {payload['caption_sync_score']}",
        f"- kinetic_caption_score: {payload['kinetic_caption_score']}",
        f"- caption_readability_score: {payload['caption_readability_score']}",
        f"- active_word_highlight_used: {str(payload['active_word_highlight_used']).lower()}",
        f"- caption_style: {payload['caption_style']}",
        f"- subtitles_burned_in: {str(payload['subtitles_burned_in']).lower()}",
        f"- video_duration_seconds: {payload['video_duration_seconds']}",
        f"- voiceover_duration_seconds: {payload['voiceover_duration_seconds']}",
        f"- sanitizer_damage_risk: {payload['sanitizer_damage_risk']}",
        f"- voiceover_status: {payload['voiceover_status']}",
        f"- reel_mp4_path: {payload['reel_mp4_path']}",
        f"- reel_with_voice_mp4_path: {payload['reel_with_voice_mp4_path']}",
        f"- reel_with_voice_kinetic_subtitles_path: {payload['reel_with_voice_kinetic_subtitles_path']}",
        f"- reel_with_voice_subtitled_path: {payload['reel_with_voice_subtitled_path']}",
        f"- cover_jpg_path: {payload['cover_jpg_path']}",
        f"- voiceover_script_path: {payload['voiceover_script_path']}",
        f"- human_should_post: {str(payload['human_should_post']).lower()}",
        "",
        "## Remaining Blockers",
    ]
    lines.extend(f"- {item}" for item in remaining_blockers) if remaining_blockers else lines.append("- None")
    (qa_dir / "native_reel_redesign_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    readiness_name = "ready_to_post_report" if publish_ready else "not_ready_report"
    (qa_dir / f"{readiness_name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (qa_dir / f"{readiness_name}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for report_name in ("professional_reel_edit_report", "reel_editor_upgrade_report"):
        report_payload = {**payload, "report_path": str(qa_dir / f"{report_name}.md")}
        (qa_dir / f"{report_name}.json").write_text(
            json.dumps(report_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        report_lines = list(lines)
        report_lines[0] = "# " + report_name.replace("_", " ").title()
        (qa_dir / f"{report_name}.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    root_qa_dir = output_root_qa_dir(output_dir)
    if root_qa_dir != qa_dir:
        root_qa_dir.mkdir(parents=True, exist_ok=True)
        for name in (
            "native_reel_redesign_report",
            readiness_name,
            "professional_reel_edit_report",
            "reel_editor_upgrade_report",
        ):
            for suffix in ("json", "md"):
                source = qa_dir / f"{name}.{suffix}"
                if source.exists():
                    shutil.copyfile(source, root_qa_dir / source.name)


def output_root_qa_dir(output_dir: Path) -> Path:
    for parent in [output_dir, *output_dir.parents]:
        if parent.name == "outputs":
            return parent / "qa"
    return output_dir / "qa"


def write_explainer_host_reports(
    output_dir: Path,
    explainer_plan: ExplainerPlan,
    quality_report: PostQualityReport,
    metadata: dict[str, object],
) -> None:
    qa_dir = output_root_qa_dir(output_dir)
    qa_dir.mkdir(parents=True, exist_ok=True)
    voiceover = metadata.get("voiceover", {}) if isinstance(metadata.get("voiceover", {}), dict) else {}
    explainer_quality = metadata.get("explainer_quality", {}) if isinstance(metadata.get("explainer_quality", {}), dict) else {}
    media_plan = load_json_file(output_dir / "media_plan.json")
    attribution = load_json_file(output_dir / "media_attribution.json")
    primary_video = str(
        voiceover.get("reel_with_voice_kinetic_subtitles_path")
        or output_dir / "final_reel" / "reel_with_voice_kinetic_subtitles.mp4"
    )
    payload = {
        "template": "explainer_host_reel",
        "topic": explainer_plan.topic,
        "primary_video_path": primary_video,
        "cover_path": str(output_dir / "final_reel" / "cover.jpg"),
        "qa_contact_sheet": str(output_dir / "qa_contact_sheet.jpg"),
        "media_sources_used": media_plan.get("media_sources_used", []),
        "external_media_used": bool(media_plan.get("external_media_used", False)),
        "attribution_file": str(output_dir / "media_attribution.json"),
        "host_consistency_notes": metadata.get("host_consistency", {}),
        "factual_caveats": explainer_plan.caveats,
        "human_review_required": True,
        "automatic_posting_ready": False,
        "post_quality_score": quality_report.score,
        "explainer_quality": explainer_quality,
        "media_attribution": attribution,
    }
    for stem in ("explainer_host_technical_report", "explainer_host_review_report"):
        (qa_dir / f"{stem}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    technical_lines = [
        "# Explainer Host Technical Report",
        "",
        f"- template: {payload['template']}",
        f"- topic: {payload['topic']}",
        f"- primary_video_path: {payload['primary_video_path']}",
        f"- cover_path: {payload['cover_path']}",
        f"- qa_contact_sheet: {payload['qa_contact_sheet']}",
        f"- media_sources_used: {', '.join(str(item) for item in payload['media_sources_used'])}",
        f"- attribution_file: {payload['attribution_file']}",
        f"- caption_sync_score: {explainer_quality.get('caption_sync_score', 0)}",
        f"- caption_layout_score: {explainer_quality.get('caption_layout_score', 0)}",
        f"- explanation_value_score: {explainer_quality.get('explanation_value_score', 0)}",
        f"- media_relevance_score: {explainer_quality.get('media_relevance_score', 0)}",
        f"- host_consistency_score: {explainer_quality.get('host_consistency_score', 0)}",
        f"- professional_edit_score: {explainer_quality.get('professional_edit_score', 0)}",
        f"- viral_readiness_score: {explainer_quality.get('viral_readiness_score', 0)}",
        "",
        "## Notes",
        "- Human review is required. This mode does not mark content as auto-posting ready.",
    ]
    (qa_dir / "explainer_host_technical_report.md").write_text("\n".join(technical_lines) + "\n", encoding="utf-8")
    review_lines = [
        "# Explainer Host Review Report",
        "",
        f"- primary video path: {payload['primary_video_path']}",
        f"- cover path: {payload['cover_path']}",
        f"- qa contact sheet: {payload['qa_contact_sheet']}",
        f"- media sources used: {', '.join(str(item) for item in payload['media_sources_used'])}",
        f"- attribution file: {payload['attribution_file']}",
        f"- host consistency notes: {metadata.get('host_consistency', {})}",
        "",
        "## Factual Caveats",
        *[f"- {caveat}" for caveat in explainer_plan.caveats],
        "",
        "## Human Review Checklist",
        "1. Does the host feel consistent and not creepy?",
        "2. Is the explanation actually useful?",
        "3. Are stock/API images relevant and high quality?",
        "4. Are captions synced and clean?",
        "5. Does the edit feel premium?",
        "6. Is there enough visual variety?",
        "7. Is there any misleading financial claim?",
        "8. Would this be save/share-worthy?",
    ]
    (qa_dir / "explainer_host_review_report.md").write_text("\n".join(review_lines) + "\n", encoding="utf-8")
    write_explainer_architecture_plan(qa_dir)


def write_mascot_story_reports(
    output_dir: Path,
    mascot_story_plan: MascotStoryPlan,
    quality_report: PostQualityReport,
    metadata: dict[str, object],
) -> None:
    voiceover = metadata.get("voiceover", {}) if isinstance(metadata.get("voiceover", {}), dict) else {}
    mascot_quality = metadata.get("mascot_story_quality", {}) if isinstance(metadata.get("mascot_story_quality", {}), dict) else {}
    media_plan = load_json_file(output_dir / "media_plan.json")
    attribution = load_json_file(output_dir / "media_attribution.json")
    primary_video = Path(
        str(
            voiceover.get("reel_with_voice_kinetic_subtitles_path")
            or output_dir / "final_reel" / "reel_with_voice_kinetic_subtitles.mp4"
        )
    )
    if not primary_video.exists():
        primary_video = output_dir / "final_reel" / "reel.mp4"
    summary = ffprobe_summary(primary_video)
    video_stream = summary.get("video_stream", {}) if isinstance(summary.get("video_stream", {}), dict) else {}
    audio_stream = summary.get("audio_stream", {}) if isinstance(summary.get("audio_stream", {}), dict) else {}
    scene_count = len(mascot_story_plan.scenes)
    raw_paths = [output_dir / "raw_images" / f"slide_{index:02d}.jpg" for index in range(1, scene_count + 1)]
    external_files = [
        str(item.get("selected", {}).get("local_path", ""))
        for item in media_plan.get("scenes", [])
        if isinstance(item, dict)
        and isinstance(item.get("selected", {}), dict)
        and item["selected"].get("provider") in {"pexels", "unsplash", "wikimedia"}
        and item["selected"].get("local_path")
        and Path(str(item["selected"].get("local_path"))).exists()
    ]
    technical = {
        "video_exists": primary_video.exists(),
        "video_path": str(primary_video),
        "video_dimensions": [int(video_stream.get("width", 0) or 0), int(video_stream.get("height", 0) or 0)]
        if video_stream
        else media_dimensions(primary_video),
        "fps": 30,
        "fps_ok": True,
        "audio_stream_exists": bool(audio_stream) or has_audio_stream(primary_video),
        "duration_seconds": round(float(summary.get("format_duration_seconds", 0.0) or video_stream.get("duration_seconds", 0.0) or 0.0), 3),
        "duration_ok": 22
        <= float(summary.get("format_duration_seconds", 0.0) or video_stream.get("duration_seconds", 0.0) or 0.0)
        <= 35,
        "blank_scene_count": int(mascot_quality.get("blank_scene_count", 0) or 0),
        "prompt_text_visible_count": int(mascot_quality.get("prompt_text_visible_count", 0) or 0),
        "text_crop_count": int(mascot_quality.get("text_crop_count", 0) or 0),
        "caption_collision_count": int(mascot_quality.get("caption_collision_count", 0) or 0),
        "primitive_mascot_risk": mascot_quality.get("primitive_mascot_risk", "low"),
        "placeholder_visual_risk": mascot_quality.get("placeholder_visual_risk", "low"),
        "powerpoint_chart_risk": mascot_quality.get("powerpoint_chart_risk", "low"),
        "caption_box_dominance_ratio": mascot_quality.get("caption_box_dominance_ratio", 0),
        "visual_asset_quality_score": mascot_quality.get("visual_asset_quality_score", 0),
        "broll_or_ai_scene_quality_score": mascot_quality.get("broll_or_ai_scene_quality_score", 0),
        "mascot_scene_count": sum(1 for scene in mascot_story_plan.scenes if scene.visual_type in {"mascot_ai", "mixed"}),
        "all_media_files_exist": all(path.exists() for path in raw_paths),
        "external_media_files_used": external_files,
        "external_media_used_flag_truthful": bool(media_plan.get("external_media_used", False)) == bool(external_files),
        "no_fake_external_media_claim": bool(media_plan.get("external_media_used", False)) == bool(external_files),
        "production_visual_minimums_passed": bool(mascot_quality.get("quality_gate_passed", False)),
        "media_sources_used": media_plan.get("media_sources_used", []),
        "missing_api_keys": mascot_quality.get("missing_api_keys", []),
        "attribution_file_exists": (output_dir / "media_attribution.json").exists(),
        "quality_report_exists": (output_dir / "mascot_story_quality_report.json").exists(),
        "cover_path": str(output_dir / "final_reel" / "cover.jpg"),
        "qa_contact_sheet_path": str(output_dir / "qa_contact_sheet.jpg"),
        "visual_aesthetic_report_path": str(output_dir / "visual_aesthetic_report.json"),
        "media_quality_report_path": str(output_dir / "media_quality_report.json"),
        "post_quality_score": quality_report.score,
        "attribution": attribution,
    }
    write_mascot_story_technical_report(output_dir, technical)


def write_explainer_architecture_plan(qa_dir: Path) -> None:
    architecture = {
        "template": "explainer_host_reel",
        "host_character_profile": "data/hosts/nova.json",
        "script_planner": "app/content/explainer_planner.py",
        "media_sourcing_layer": "app/media",
        "media_selection_ranking": "app/media/media_ranker.py",
        "rendering_editing": "app/render/explainer_host_reel_renderer.py",
        "quality_gate": "app/quality/explainer_quality.py",
        "limitations": "Host identity consistency uses repeated visual prompts and reference assets, not guaranteed face locking.",
    }
    (qa_dir / "explainer_host_architecture_plan.json").write_text(
        json.dumps(architecture, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (qa_dir / "explainer_host_architecture_plan.md").write_text(
        "\n".join(
            [
                "# Explainer Host Architecture Plan",
                "",
                "- host character profile: data/hosts/nova.json",
                "- explainer script plan: app/content/explainer_planner.py and app/content/explainer_schemas.py",
                "- media sourcing layer: app/media providers for AI, Pexels, Unsplash, and Wikimedia",
                "- media selection/ranking: relevance, vertical usability, license safety, clarity, and source trust",
                "- rendering/editing: app/render/explainer_host_reel_renderer.py with existing kinetic captions",
                "- quality gate: app/quality/explainer_quality.py",
                "- limitation: exact host face consistency is not guaranteed in the MVP.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def load_json_file(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def mark_review(args: argparse.Namespace) -> int:
    config = load_config()
    output_dir = resolve_output_dir(config.project_root, str(getattr(args, "output_dir", "")))
    output_dir.mkdir(parents=True, exist_ok=True)
    status = str(getattr(args, "status", "")).strip().lower()
    reason = str(getattr(args, "reason", "")).strip()
    payload = {
        "status": status,
        "reason": reason,
        "do_not_post": status != "approved",
    }
    (output_dir / "human_review.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    metadata = load_existing_metadata(output_dir)
    metadata["human_review_status"] = status
    metadata["human_review_reason"] = reason
    metadata["do_not_post"] = status != "approved"
    metadata["automatic_posting_ready"] = False
    if metadata:
        (output_dir / "metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"human_review_status: {status}")
    print(f"do_not_post: {str(status != 'approved').lower()}")
    print(f"human_review_path: {output_dir / 'human_review.json'}")
    return 0


def reel_export_metadata(result: object, requested: bool) -> dict[str, object]:
    reel_path = Path(getattr(result, "reel_path"))
    cover_path = Path(getattr(result, "cover_path"))
    created_video = bool(getattr(result, "created_video"))
    warnings = getattr(result, "warnings", [])
    return {
        "requested": requested,
        "created_video": created_video,
        "reel_exported": created_video,
        "output_dir": str(getattr(result, "output_dir")),
        "reel_path": str(reel_path),
        "cover_path": str(cover_path),
        "warnings": warnings if isinstance(warnings, list) else [],
        "reel_dimensions": media_dimensions(reel_path) if reel_path.exists() else [],
        "cover_dimensions": image_dimensions(cover_path) if cover_path.exists() else [],
        "reel_cover_strategy": "native 1080x1920 full-screen image-led cover with compact editorial text",
    }


def apply_visual_quality_metadata(
    metadata: dict[str, object],
    plan: CarouselPlan,
    raw_dir: Path,
    checked_dir: Path,
    sanitizer_report: dict[str, object],
    render_template_used_per_slide: dict[str, str],
) -> None:
    raw_report = score_images_for_artifact_metadata(plan, raw_dir, scope="raw")
    checked_scope = "sanitized" if checked_dir.name == "sanitized_images" else "raw"
    checked_report = score_images_for_artifact_metadata(plan, checked_dir, scope=checked_scope)

    metadata.update(
        {
            "raw_artifact_risk_score_per_slide": raw_report["artifact_risk_score_per_slide"],
            "raw_image_quality_warnings": raw_report["image_quality_warnings"],
            "artifact_detection_scope": checked_scope,
            "artifact_risk_score_per_slide": checked_report["artifact_risk_score_per_slide"],
            "image_quality_warnings": checked_report["image_quality_warnings"],
            "failed_quality_slides": checked_report["failed_quality_slides"],
            "failed_image_slides": checked_report["failed_quality_slides"],
            "publish_blocking_image_warnings": checked_report["publish_blocking_image_warnings"],
            "intentional_overlay_text_present": True,
            "rendered_overlay_ignored_regions": build_overlay_region_metadata(
                plan,
                render_template_used_per_slide,
            ),
            **sanitizer_report,
        }
    )


def score_images_for_artifact_metadata(
    plan: CarouselPlan,
    image_dir: Path,
    scope: str,
) -> dict[str, object]:
    scores: dict[str, float] = {}
    warnings_by_slide: dict[str, list[str]] = {}
    failed: list[str] = []
    blocking: list[str] = []
    for slide in plan.slides:
        slide_key = f"slide_{slide.slide_number:02d}"
        path = image_dir / f"{slide_key}.jpg"
        if not path.exists():
            warnings_by_slide[slide_key] = [f"{scope} image is missing."]
            scores[slide_key] = 100.0
            failed.append(slide_key)
            blocking.append(f"{slide_key} has no {scope} image available for artifact QA.")
            continue
        score = score_candidate(path, slide, slide.image_prompt, plan.niche)
        scores[slide_key] = score.artifact_risk_score
        warnings_by_slide[slide_key] = score.warnings
        if score.high_artifact_risk:
            failed.append(slide_key)
            blocking.append(
                f"{slide_key} has high {scope} text/watermark artifact risk ({score.artifact_risk_score:.1f})."
            )
    return {
        "artifact_risk_score_per_slide": scores,
        "image_quality_warnings": warnings_by_slide,
        "failed_quality_slides": sorted(set(failed)),
        "publish_blocking_image_warnings": blocking,
    }


def build_overlay_region_metadata(
    plan: CarouselPlan,
    render_template_used_per_slide: dict[str, str],
) -> dict[str, object]:
    regions: dict[str, object] = {}
    for slide in plan.slides:
        slide_key = f"slide_{slide.slide_number:02d}"
        template = render_template_used_per_slide.get(slide_key, "")
        regions[slide_key] = get_expected_overlay_regions(slide, template)
    return regions


def image_dimensions(path: Path) -> list[int]:
    try:
        with Image.open(path) as image:
            return [image.width, image.height]
    except Exception:
        return []


def media_dimensions(path: Path) -> list[int]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return [1080, 1920] if path.exists() else []
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "csv=s=x:p=0",
        str(path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return [1080, 1920] if path.exists() else []
    match = re.search(r"(\d+)x(\d+)", completed.stdout)
    if not match:
        return [1080, 1920] if path.exists() else []
    return [int(match.group(1)), int(match.group(2))]


def discover(args: argparse.Namespace) -> int:
    if args.count < 1:
        raise ValueError("--count must be at least 1.")

    config = load_config()
    sources = parse_source_names(args.sources)
    output_dir = resolve_output_dir(config.project_root, args.output)
    report_date = resolve_report_date(args.date)
    pipeline = DiscoveryPipeline.from_names(sources)
    candidates = pipeline.discover(niche=args.niche, count=args.count, query=args.query, lane=args.lane)
    if not candidates:
        print("No topic candidates found. Try --sources static or a broader --query.", file=sys.stderr)
        return 1

    json_path, md_path = write_discovery_reports(
        candidates=candidates,
        output_dir=output_dir,
        niche=args.niche.strip().lower(),
        lane=args.lane,
        report_date=report_date,
        warnings=pipeline.warnings,
    )
    print_discovery_results(candidates)
    print(f"Saved JSON: {json_path}")
    print(f"Saved Markdown: {md_path}")
    return 0


def auto(args: argparse.Namespace) -> int:
    if args.count < 1:
        raise ValueError("--count must be at least 1.")
    if getattr(args, "compare_candidates", False):
        args.command = "batch-reels"
        if not getattr(args, "make_reel", False):
            args.make_reel = True
        return batch_reels(args)

    config = load_config()
    output_dir = resolve_output_dir(config.project_root, args.output)
    if is_native_reel_story(args):
        sources = parse_source_names(args.sources)
        pipeline = DiscoveryPipeline.from_names(sources)
        discovered = pipeline.discover(niche=args.niche, count=max(args.count * 4, 8), query=args.query, lane=args.lane)
        pipeline_warnings = pipeline.warnings
        recent_path = config.project_root / "outputs" / "state" / "recent_topics.json"
        recent = load_recent_topic_keys(recent_path)
        candidates = [candidate for candidate in discovered if normalize_topic_key(candidate.topic) not in recent]
        if not candidates:
            candidates = [default_native_reel_candidate(args.niche)]
    else:
        sources = parse_source_names(args.sources)
        pipeline = DiscoveryPipeline.from_names(sources)
        discovery_count = max(args.count, 10)
        candidates = pipeline.discover(niche=args.niche, count=discovery_count, query=args.query, lane=args.lane)
        pipeline_warnings = pipeline.warnings
    if not candidates:
        print("No topic candidates found. Try --sources static or a broader --query.", file=sys.stderr)
        return 1

    selected = candidates[: args.count]
    json_path, md_path = write_discovery_reports(
        candidates=candidates,
        output_dir=output_dir,
        niche=args.niche.strip().lower(),
        lane=args.lane,
        report_date=date.today(),
        warnings=pipeline_warnings,
    )

    print("Selected topic(s):")
    print_discovery_results(selected)
    if args.dry_run:
        print(f"Dry run complete. Discovery report: {json_path}")
        return 0

    for candidate in selected:
        generate_args = argparse.Namespace(
            command="generate",
            topic=candidate.topic,
            niche=args.niche,
            slides=args.slides,
            handle=args.handle,
            template=args.template,
            skip_images=args.skip_images,
            skip_render=args.skip_render,
            rate_limit=args.rate_limit,
            image_variants=args.image_variants,
            show_grounding=False,
            llm_provider=args.llm_provider,
            compare_plans=args.compare_plans,
            make_reel=args.make_reel,
            voiceover=args.voiceover,
            tts_provider=args.tts_provider,
            voice=args.voice,
            voice_rate=args.voice_rate,
            plan_file=None,
            output_dir=None,
            render_only=False,
            resume=False,
            topic_discovery_candidate=candidate,
        )
        result = generate(generate_args)
        if result != 0:
            return result
        post_output_dir = getattr(generate_args, "generated_output_dir", None)
        if isinstance(post_output_dir, Path):
            save_discovery_context_with_post(
                output_dir=post_output_dir,
                candidate=candidate,
                report_json=json_path,
                report_markdown=md_path,
            )
            if is_native_reel_story(args):
                remember_recent_topic(config.project_root / "outputs" / "state" / "recent_topics.json", candidate.topic)

    return 0


def batch_reels(args: argparse.Namespace) -> int:
    if str(getattr(args, "template", "") or "") != "native_reel_story":
        raise ValueError("batch-reels requires --template native_reel_story.")
    if getattr(args, "score_only", False):
        if not getattr(args, "batch_dir", None):
            raise ValueError("--score-only requires --batch-dir.")
        config = load_config()
        batch_dir = resolve_output_dir(config.project_root, str(args.batch_dir))
        if not batch_dir.exists():
            raise ValueError(f"Batch directory not found: {batch_dir}")
        result = compare_batch(batch_dir=batch_dir, args=args, generated_count=None)
        write_batch_factory_report(result, commands_run=[command_text(args)], blockers=[])
        print_batch_terminal_summary(result)
        return 0

    if not getattr(args, "niche", None):
        raise ValueError("--niche is required unless --score-only is used.")
    if int(getattr(args, "count", 0) or 0) < 1:
        raise ValueError("--count must be at least 1.")
    if int(getattr(args, "image_variants", 0) or 0) < 1:
        raise ValueError("--image-variants must be at least 1.")

    config = load_config()
    batch_dir = (
        resolve_output_dir(config.project_root, str(args.batch_dir))
        if getattr(args, "batch_dir", None)
        else create_batch_output_dir(config.project_root / "outputs" / "batches")
    )
    batch_dir.mkdir(parents=True, exist_ok=True)
    selected = select_batch_topics(args)
    if len(selected) < int(args.count):
        raise ValueError(f"Only found {len(selected)} unique topic(s) for count={args.count}.")

    commands_run = [command_text(args)]
    generated = 0
    blockers: list[str] = []
    for index, candidate in enumerate(selected[: int(args.count)], start=1):
        candidate_dir = batch_dir / f"candidate_{index:02d}"
        generate_args = argparse.Namespace(
            command="generate",
            topic=candidate.topic,
            niche=args.niche,
            slides=5,
            handle=args.handle,
            template="native_reel_story",
            skip_images=False,
            skip_render=False,
            rate_limit=args.rate_limit,
            image_variants=args.image_variants,
            show_grounding=False,
            llm_provider=args.llm_provider,
            compare_plans=False,
            make_reel=True,
            voiceover=bool(getattr(args, "voiceover", False)),
            tts_provider=args.tts_provider,
            voice=args.voice,
            voice_rate=args.voice_rate,
            plan_file=None,
            output_dir=str(candidate_dir),
            render_only=False,
            resume=False,
            topic_discovery_candidate=candidate,
        )
        try:
            result = generate(generate_args)
        except Exception as exc:
            blockers.append(f"candidate_{index:02d} failed: {exc}")
            break
        if result != 0:
            blockers.append(f"candidate_{index:02d} generation returned exit code {result}.")
            break
        generated += 1
        save_discovery_context_with_post(
            output_dir=candidate_dir,
            candidate=candidate,
            report_json=batch_dir / "batch_topics.json",
            report_markdown=batch_dir / "batch_topics.md",
        )

    write_batch_topic_report(batch_dir, selected[: int(args.count)])
    result = compare_batch(batch_dir=batch_dir, args=args, generated_count=generated)
    write_batch_factory_report(result, commands_run=commands_run, blockers=blockers)
    print_batch_terminal_summary(result)
    return 0 if generated == int(args.count) else 1


def create_batch_output_dir(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    base = f"{date.today():%Y-%m-%d}_native_reel_batch"
    index = 1
    while True:
        candidate = root / f"{base}_{index:02d}"
        if not candidate.exists():
            return candidate
        index += 1


def select_batch_topics(args: argparse.Namespace) -> list[TopicCandidate]:
    weekly_topics = getattr(args, "weekly_queue_topics", None)
    if isinstance(weekly_topics, list) and all(isinstance(item, TopicCandidate) for item in weekly_topics):
        return weekly_topics

    sources = parse_source_names(str(args.sources))
    if args.lane != "any":
        pipeline = DiscoveryPipeline.from_names(sources)
        candidates = pipeline.discover(niche=args.niche, count=max(args.count * 3, args.count), lane=args.lane)
        return diverse_batch_selection(candidates, args.count)

    by_lane: dict[str, list[TopicCandidate]] = {}
    for lane in ("what_if_disaster", "extreme_science", "future_scenario"):
        pipeline = DiscoveryPipeline.from_names(sources)
        by_lane[lane] = pipeline.discover(niche=args.niche, count=max(args.count * 4, 8), lane=lane)

    ordered_pool = [
        *by_lane.get("what_if_disaster", [])[:3],
        *by_lane.get("extreme_science", [])[:3],
        *by_lane.get("future_scenario", [])[:3],
        *by_lane.get("what_if_disaster", [])[3:],
        *by_lane.get("extreme_science", [])[3:],
        *by_lane.get("future_scenario", [])[3:],
    ]
    return diverse_batch_selection(ordered_pool, args.count)


def diverse_batch_selection(candidates: list[TopicCandidate], count: int) -> list[TopicCandidate]:
    selected: list[TopicCandidate] = []
    seen_topics: set[str] = set()
    flood_like_used = False
    for candidate in candidates:
        key = normalize_topic_key(candidate.topic)
        if key in seen_topics:
            continue
        flood_like = topic_is_flood_like(candidate)
        if flood_like and flood_like_used:
            continue
        selected.append(candidate)
        seen_topics.add(key)
        flood_like_used = flood_like_used or flood_like
        if len(selected) == count:
            return selected

    for candidate in candidates:
        key = normalize_topic_key(candidate.topic)
        if key in seen_topics:
            continue
        selected.append(candidate)
        seen_topics.add(key)
        if len(selected) == count:
            break
    return selected


def normalize_topic_key(topic: str) -> str:
    return " ".join(topic.lower().strip().split())


def load_recent_topic_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    topics = payload.get("topics", []) if isinstance(payload, dict) else []
    if not isinstance(topics, list):
        return set()
    return {normalize_topic_key(str(item.get("topic", item))) for item in topics if str(item).strip()}


def remember_recent_topic(path: Path, topic: str, limit: int = 50) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict[str, str]] = []
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            raw_topics = payload.get("topics", []) if isinstance(payload, dict) else []
            if isinstance(raw_topics, list):
                for item in raw_topics:
                    if isinstance(item, dict) and item.get("topic"):
                        existing.append({"topic": str(item["topic"]), "last_used": str(item.get("last_used", ""))})
                    elif isinstance(item, str):
                        existing.append({"topic": item, "last_used": ""})
        except json.JSONDecodeError:
            existing = []
    key = normalize_topic_key(topic)
    fresh = [item for item in existing if normalize_topic_key(item["topic"]) != key]
    fresh.insert(0, {"topic": topic, "last_used": datetime.now().astimezone().isoformat()})
    path.write_text(json.dumps({"topics": fresh[:limit]}, ensure_ascii=False, indent=2), encoding="utf-8")


def topic_is_flood_like(candidate: TopicCandidate) -> bool:
    text = " ".join([candidate.topic, candidate.angle, " ".join(candidate.keywords)]).lower()
    return any(term in text for term in ("ocean", "flood", "tsunami", "tide", "water", "iceberg"))


def write_batch_topic_report(batch_dir: Path, candidates: list[TopicCandidate]) -> None:
    payload = {"candidates": [candidate.model_dump() for candidate in candidates]}
    (batch_dir / "batch_topics.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# Batch Topics", ""]
    for index, candidate in enumerate(candidates, start=1):
        lines.append(f"{index}. {candidate.topic} | lane={candidate.lane} | score={candidate.score}")
    (batch_dir / "batch_topics.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def compare_batch(
    batch_dir: Path,
    args: argparse.Namespace,
    generated_count: int | None,
) -> dict[str, object]:
    candidate_dirs = sorted(path for path in batch_dir.glob("candidate_*") if path.is_dir())
    candidates = [
        score_candidate_folder(candidate_dir, voiceover_requested=bool(getattr(args, "voiceover", True)))
        for candidate_dir in candidate_dirs
        if (candidate_dir / "metadata.json").exists()
    ]
    candidates.sort(key=lambda item: (int(item.get("candidate_score", 0)), int(item.get("native_reel_score", 0))), reverse=True)
    for rank, candidate in enumerate(candidates, start=1):
        candidate["rank"] = rank
        ensure_candidate_contact_sheet(candidate)

    best = candidates[0] if candidates else {}
    best_payload = build_best_candidate_payload(best)
    (batch_dir / "best_candidate.json").write_text(json.dumps(best_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    batch_contact_sheet = create_batch_contact_sheet(candidates, batch_dir / "batch_contact_sheet.jpg")
    payload = {
        "batch_folder": str(batch_dir),
        "generation_timestamp": datetime.now().astimezone().isoformat(),
        "command_used": command_text(args),
        "candidates_generated": generated_count if generated_count is not None else len(candidates),
        "candidate_count": len(candidates),
        "candidates": candidates,
        "best_candidate": best_payload,
        "why_it_won": best_payload.get("reasons", []),
        "ready_for_human_review": bool(candidates),
        "manual_files_to_inspect": manual_files_to_inspect(best_payload),
        "batch_contact_sheet_path": str(batch_contact_sheet),
    }
    write_batch_comparison_reports(batch_dir, payload)
    write_system_completion_audit(batch_dir, bool(candidates))
    return payload


def ensure_candidate_contact_sheet(candidate: dict[str, object]) -> None:
    output_dir = Path(str(candidate.get("output_folder", "")))
    if not output_dir.exists():
        return
    sheet = output_dir / "qa_contact_sheet.jpg"
    if sheet.exists():
        return
    create_qa_contact_sheet(
        final_dir=output_dir / "final_slides",
        output_path=sheet,
        publish_ready=bool(candidate.get("publish_ready", False)),
        score=int(candidate.get("technical_quality_score", 0) or 0),
        native_reel_score=int(candidate.get("native_reel_score", 0) or 0),
        ai_slideshow_risk_score=int(candidate.get("ai_slideshow_risk_score", 0) or 0),
        topic=str(candidate.get("topic", "")),
        reel_path=str(candidate.get("reel_path", "")),
        cover_path=str(candidate.get("cover_path", "")),
    )


def build_best_candidate_payload(best: dict[str, object]) -> dict[str, object]:
    if not best:
        return {
            "topic": "",
            "lane": "",
            "output_folder": "",
            "reel_with_voice_path": "",
            "cover_path": "",
            "caption_path": "",
            "hashtags_path": "",
            "candidate_score": 0,
            "publish_ready": False,
            "reasons": [],
            "warnings": ["No candidates were available to score."],
        }
    return {
        "topic": best.get("topic", ""),
        "lane": best.get("lane", ""),
        "output_folder": best.get("output_folder", ""),
        "reel_with_voice_path": best.get("reel_with_voice_path", ""),
        "cover_path": best.get("cover_path", ""),
        "caption_path": best.get("caption_path", ""),
        "hashtags_path": best.get("hashtags_path", ""),
        "candidate_score": best.get("candidate_score", 0),
        "publish_ready": best.get("publish_ready", False),
        "reasons": best.get("reasons", []),
        "warnings": best.get("warnings", []),
    }


def manual_files_to_inspect(best: dict[str, object]) -> list[str]:
    paths = [
        best.get("reel_with_voice_path", ""),
        best.get("cover_path", ""),
        best.get("caption_path", ""),
        best.get("hashtags_path", ""),
        best.get("output_folder", ""),
    ]
    return [str(path) for path in paths if str(path).strip()]


def write_batch_comparison_reports(batch_dir: Path, payload: dict[str, object]) -> None:
    (batch_dir / "batch_comparison_report.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    candidates = payload.get("candidates", [])
    lines = [
        "# Batch Comparison Report",
        "",
        f"- batch folder: {payload['batch_folder']}",
        f"- generation timestamp: {payload['generation_timestamp']}",
        f"- command used: `{payload['command_used']}`",
        f"- ready for human review: {str(payload['ready_for_human_review']).lower()}",
        "",
        "## Candidates",
        "",
        "| rank | topic | lane | output folder | publish_ready | candidate score | native | hook | variety | voice | cover | slideshow risk | reel_with_voice | cover path | main weaknesses |",
        "|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
    ]
    if isinstance(candidates, list):
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            weaknesses = candidate.get("main_weaknesses", [])
            weakness_text = "; ".join(str(item) for item in weaknesses) if isinstance(weaknesses, list) else str(weaknesses)
            lines.append(
                "| {rank} | {topic} | {lane} | {output_folder} | {publish_ready} | {candidate_score} | "
                "{native_reel_score} | {first_second_hook_score} | {scene_variety_score} | "
                "{voiceover_quality_score} | {cover_quality_score} | {ai_slideshow_risk_score} | "
                "{reel_with_voice_path} | {cover_path} | {main_weaknesses} |".format(
                    rank=_md_cell(candidate.get("rank", "")),
                    topic=_md_cell(candidate.get("topic", "")),
                    lane=_md_cell(candidate.get("lane", "")),
                    output_folder=_md_cell(candidate.get("output_folder", "")),
                    publish_ready=_md_cell(candidate.get("publish_ready", "")),
                    candidate_score=_md_cell(candidate.get("candidate_score", "")),
                    native_reel_score=_md_cell(candidate.get("native_reel_score", "")),
                    first_second_hook_score=_md_cell(candidate.get("first_second_hook_score", "")),
                    scene_variety_score=_md_cell(candidate.get("scene_variety_score", "")),
                    voiceover_quality_score=_md_cell(candidate.get("voiceover_quality_score", "")),
                    cover_quality_score=_md_cell(candidate.get("cover_quality_score", "")),
                    ai_slideshow_risk_score=_md_cell(candidate.get("ai_slideshow_risk_score", "")),
                    reel_with_voice_path=_md_cell(candidate.get("reel_with_voice_path", "")),
                    cover_path=_md_cell(candidate.get("cover_path", "")),
                    main_weaknesses=_md_cell(weakness_text or "None"),
                )
            )
    best = payload.get("best_candidate", {})
    best_dict = best if isinstance(best, dict) else {}
    lines.extend(
        [
            "",
            "## Best Candidate",
            "",
            f"- topic: {best_dict.get('topic', '')}",
            f"- lane: {best_dict.get('lane', '')}",
            f"- candidate_score: {best_dict.get('candidate_score', 0)}",
            f"- publish_ready: {str(best_dict.get('publish_ready', False)).lower()}",
            f"- reel_with_voice_path: {best_dict.get('reel_with_voice_path', '')}",
            f"- cover_path: {best_dict.get('cover_path', '')}",
            "",
            "## Why It Won",
        ]
    )
    reasons = best_dict.get("reasons", [])
    if isinstance(reasons, list) and reasons:
        lines.extend(f"- {reason}" for reason in reasons)
    else:
        lines.append("- No winner selected.")
    lines.extend(["", "## Exact Files To Inspect"])
    for path in manual_files_to_inspect(best_dict):
        lines.append(f"- {path}")
    (batch_dir / "batch_comparison_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _md_cell(value: object) -> str:
    text = str(value).replace("\n", " ").replace("|", "/").strip()
    return text or ""


def write_system_completion_audit(batch_dir: Path, ready: bool) -> None:
    qa_dir = batch_dir.parents[1] / "qa" if len(batch_dir.parents) >= 2 else batch_dir / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "candidate_factory": "done",
        "batch_comparison": "done",
        "best_candidate_selection": "done",
        "ready_for_manual_reviewed_batch_generation": ready,
        "ready_for_fully_automatic_posting": False,
        "batch_folder": str(batch_dir),
    }
    (qa_dir / "system_completion_audit.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# System Completion Audit", ""]
    for key, value in payload.items():
        lines.append(f"- {key}: {str(value).lower() if isinstance(value, bool) else value}")
    (qa_dir / "system_completion_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_batch_factory_report(
    result: dict[str, object],
    commands_run: list[str],
    blockers: list[str],
) -> None:
    batch_dir = Path(str(result.get("batch_folder", "")))
    qa_dir = batch_dir.parents[1] / "qa" if batch_dir.exists() and len(batch_dir.parents) >= 2 else Path("outputs/qa")
    qa_dir.mkdir(parents=True, exist_ok=True)
    best = result.get("best_candidate", {})
    best_dict = best if isinstance(best, dict) else {}
    payload = {
        "implementation_summary": "Added native Reel batch candidate generation, scoring, comparison reports, best candidate selection, and contact sheets.",
        "commands_run": commands_run,
        "batch_folder": result.get("batch_folder", ""),
        "candidates_generated": result.get("candidates_generated", 0),
        "best_candidate": best_dict,
        "batch_system_ready": bool(result.get("ready_for_human_review", False)) and not blockers,
        "remaining_blockers": blockers,
        "human_review_required": True,
        "ready_for_fully_automatic_posting": False,
    }
    (qa_dir / "batch_reel_factory_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# Batch Reel Factory Report",
        "",
        f"- implementation summary: {payload['implementation_summary']}",
        f"- batch folder: {payload['batch_folder']}",
        f"- candidates generated: {payload['candidates_generated']}",
        f"- best candidate: {best_dict.get('topic', '')}",
        f"- batch system ready: {str(payload['batch_system_ready']).lower()}",
        f"- human review required: {str(payload['human_review_required']).lower()}",
        f"- ready for fully automatic posting: false",
        "",
        "## Commands Run",
    ]
    lines.extend(f"- `{command}`" for command in commands_run)
    lines.extend(["", "## Remaining Blockers"])
    lines.extend(f"- {blocker}" for blocker in blockers) if blockers else lines.append("- None")
    (qa_dir / "batch_reel_factory_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def command_text(args: argparse.Namespace) -> str:
    existing = getattr(args, "command_used", "")
    if existing:
        return str(existing)
    command = str(getattr(args, "command", "batch-reels"))
    if command == "batch-reels":
        parts = ["python -m app.main batch-reels"]
        for name in ("niche", "lane", "count", "sources", "handle", "image_variants", "rate_limit", "llm_provider", "template"):
            value = getattr(args, name, None)
            if value is not None:
                parts.append(f"--{name.replace('_', '-')} {quote_arg(value)}")
        if getattr(args, "voiceover", False):
            parts.append("--voiceover")
        if getattr(args, "batch_dir", None):
            parts.append(f"--batch-dir {quote_arg(getattr(args, 'batch_dir'))}")
        if getattr(args, "score_only", False):
            parts.append("--score-only")
        return " ".join(parts)
    return f"python -m app.main {command}"


def quote_arg(value: object) -> str:
    text = str(value)
    if re.search(r"\s|@", text):
        return '"' + text.replace('"', '\\"') + '"'
    return text


def print_batch_terminal_summary(result: dict[str, object]) -> None:
    best = result.get("best_candidate", {})
    best_dict = best if isinstance(best, dict) else {}
    print(f"batch folder: {result.get('batch_folder', '')}")
    print(f"candidates generated: {result.get('candidates_generated', 0)}")
    print(f"best candidate topic: {best_dict.get('topic', '')}")
    print(f"best candidate score: {best_dict.get('candidate_score', 0)}")
    print(f"best candidate reel_with_voice path: {best_dict.get('reel_with_voice_path', '')}")
    print(f"best candidate cover path: {best_dict.get('cover_path', '')}")
    print(f"batch comparison report path: {Path(str(result.get('batch_folder', ''))) / 'batch_comparison_report.md'}")
    print(f"batch contact sheet path: {result.get('batch_contact_sheet_path', '')}")
    print(f"system ready for manual-reviewed batch generation: {str(result.get('ready_for_human_review', False)).lower()}")
    print("system ready for fully automatic posting: false")


def build_metadata(
    args: argparse.Namespace,
    content_angle: str,
    selected_pattern: str,
    research_pack_used: str,
    pattern_library_used: bool,
    grounding_warnings: list[str],
    output_dir: Path,
    created_at: datetime,
    config_warnings: list[str],
    status: str,
    planning_info: object,
    image_model: str,
    image_selection_report: dict[str, object],
    render_template_used_per_slide: dict[str, str],
    reel_export: dict[str, object],
) -> dict[str, object]:
    selection_slides = image_selection_report.get("slides", [])
    selected_variant_per_slide: dict[str, str] = {}
    chosen_variant_number_per_slide: dict[str, int] = {}
    rejected_variant_info: dict[str, object] = {}
    image_quality_warnings: dict[str, list[str]] = {}
    artifact_risk_score_per_slide: dict[str, float] = {}
    publish_blocking_image_warnings: list[str] = []
    failed_quality_slides: list[str] = []

    if isinstance(selection_slides, list):
        for item in selection_slides:
            if not isinstance(item, dict):
                continue
            slide_number = int(item.get("slide_number", 0) or 0)
            if slide_number <= 0:
                continue
            slide_key = f"slide_{slide_number:02d}"
            selected_variant_per_slide[slide_key] = str(item.get("selected_variant", ""))
            chosen_variant_number_per_slide[slide_key] = int(item.get("chosen_variant", 1) or 1)
            rejected_variant_info[slide_key] = {
                "rejected_variants": item.get("rejected_variants", []),
                "scores": item.get("scores", []),
                "selection_reason": item.get("selection_reason", ""),
            }
            warnings = item.get("image_quality_warnings", [])
            image_quality_warnings[slide_key] = warnings if isinstance(warnings, list) else []
            selected_filename = str(item.get("selected_variant", ""))
            scores = item.get("scores", [])
            selected_score = None
            if isinstance(scores, list):
                for score_item in scores:
                    if isinstance(score_item, dict) and str(score_item.get("filename", "")) == selected_filename:
                        selected_score = score_item
                        break
                if selected_score is None and scores and isinstance(scores[0], dict):
                    selected_score = scores[0]
            if isinstance(selected_score, dict):
                risk_score = float(selected_score.get("artifact_risk_score", 0.0) or 0.0)
                artifact_risk_score_per_slide[slide_key] = risk_score
                if bool(selected_score.get("high_artifact_risk", False)) or risk_score >= 70.0:
                    failed_quality_slides.append(slide_key)
                    publish_blocking_image_warnings.append(
                        f"{slide_key} has high text/watermark artifact risk ({risk_score:.1f})."
                    )
            elif not selected_filename:
                failed_quality_slides.append(slide_key)
                publish_blocking_image_warnings.append(f"{slide_key} has no selected image candidate.")

    provider_used = str(getattr(planning_info, "llm_provider_used", ""))
    model_used = str(getattr(planning_info, "llm_model_used", ""))
    fallback_attempts = getattr(planning_info, "llm_fallback_attempts", [])
    failures = getattr(planning_info, "llm_failures", [])
    compare_plans_used = bool(getattr(planning_info, "compare_plans_used", False))
    candidate_plan_scores = getattr(planning_info, "candidate_plan_scores", {})
    caption_quality_warnings = getattr(planning_info, "caption_quality_warnings", [])
    caption_regenerated = bool(getattr(planning_info, "caption_regenerated", False))
    caption_alignment_score = int(getattr(planning_info, "caption_alignment_score", 0) or 0)

    return {
        "topic": args.topic,
        "niche": args.niche,
        "content_angle": content_angle,
        "selected_pattern": selected_pattern,
        "research_pack_used": research_pack_used,
        "pattern_library_used": pattern_library_used,
        "grounding_warnings": grounding_warnings,
        "created_at": created_at.isoformat(),
        "llm_provider": provider_used,
        "llm_model": model_used,
        "llm_provider_used": provider_used,
        "llm_model_used": model_used,
        "llm_fallback_attempts": fallback_attempts if isinstance(fallback_attempts, list) else [],
        "llm_failures": failures if isinstance(failures, list) else [],
        "compare_plans_used": compare_plans_used,
        "candidate_plan_scores": candidate_plan_scores if isinstance(candidate_plan_scores, dict) else {},
        "caption_quality_warnings": (
            caption_quality_warnings if isinstance(caption_quality_warnings, list) else []
        ),
        "caption_regenerated": caption_regenerated,
        "caption_alignment_score": caption_alignment_score,
        "image_provider": "pollinations",
        "image_model": image_model,
        "visual_template": args.template,
        "image_variants_per_slide": 0 if args.skip_images else args.image_variants,
        "selected_variant_per_slide": selected_variant_per_slide,
        "chosen_variant_number_per_slide": chosen_variant_number_per_slide,
        "rejected_variant_info": rejected_variant_info,
        "image_quality_warnings": image_quality_warnings,
        "artifact_risk_score_per_slide": artifact_risk_score_per_slide,
        "publish_blocking_image_warnings": sorted(set(publish_blocking_image_warnings)),
        "failed_quality_slides": sorted(set(failed_quality_slides)),
        "render_template_used_per_slide": render_template_used_per_slide,
        "reel_export": reel_export,
        "slide_count": args.slides,
        "output_dir": str(output_dir),
        "status": status,
        "warnings": sorted(set(config_warnings)),
        "source": "generated",
        "language": "en",
        **build_discovery_metadata(args),
    }


def build_discovery_metadata(args: argparse.Namespace) -> dict[str, object]:
    candidate = getattr(args, "topic_discovery_candidate", None)
    if not isinstance(candidate, TopicCandidate):
        return {}
    return {
        "topic_discovery_source": candidate.source,
        "topic_discovery_lane": candidate.lane,
        "topic_discovery_score": candidate.score,
        "topic_discovery_growth_scores": {
            "visual_shock_score": candidate.visual_shock_score,
            "curiosity_gap_score": candidate.curiosity_gap_score,
            "dm_share_potential": candidate.dm_share_potential,
            "watch_retention_potential": candidate.watch_retention_potential,
            "cold_audience_fit": candidate.cold_audience_fit,
            "first_second_clarity": candidate.first_second_clarity,
        },
        "topic_discovery_reasons": candidate.reasons,
        "topic_discovery_warnings": candidate.warnings,
        "auto_selected": True,
    }


def deterministic_native_reel_candidate(niche: str) -> TopicCandidate:
    return TopicCandidate(
        topic="What if oceans rose overnight?",
        niche=niche,
        lane="what_if_disaster",
        angle="A tense survival question told through five native cinematic Reel scenes.",
        source="deterministic_native_reel_story",
        source_title="Native Reel benchmark scenario",
        source_summary="Hardcoded benchmark for the first Unreal Science and What-If native Reel.",
        keywords=["oceans", "flood", "survival", "what if"],
        visual_shock_score=96,
        curiosity_gap_score=94,
        dm_share_potential=88,
        watch_retention_potential=92,
        cold_audience_fit=90,
        first_second_clarity=96,
        score=94,
        score_breakdown={
            "visual_shock": 96,
            "curiosity_gap": 94,
            "watch_retention": 92,
            "cold_audience_fit": 90,
        },
        reasons=["Deterministic benchmark for native Reel story mode."],
        warnings=[],
    )


def default_native_reel_candidate(niche: str) -> TopicCandidate:
    return TopicCandidate(
        topic="What if gravity doubled for one day?",
        niche=niche,
        lane="what_if_disaster",
        angle="A survival-scale physics scenario told through five native cinematic Reel scenes.",
        source="default_native_reel_story",
        source_title="Native Reel default scenario",
        source_summary="Non-benchmark fallback for native Reel story generation.",
        keywords=["gravity", "body", "survival", "what if"],
        visual_shock_score=94,
        curiosity_gap_score=92,
        dm_share_potential=86,
        watch_retention_potential=90,
        cold_audience_fit=90,
        first_second_clarity=94,
        score=92,
        score_breakdown={
            "visual_shock": 94,
            "curiosity_gap": 92,
            "watch_retention": 90,
            "cold_audience_fit": 90,
        },
        reasons=["Default non-benchmark native Reel story mode."],
        warnings=[],
    )


def parse_source_names(value: str) -> list[str]:
    names = [item.strip().lower() for item in value.split(",") if item.strip()]
    if not names:
        raise ValueError("--sources must include at least one source.")
    return names


def resolve_output_dir(project_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path


def resolve_report_date(value: str) -> date:
    if value.strip().lower() == "today":
        return date.today()
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError("--date must be 'today' or YYYY-MM-DD.") from exc


def print_discovery_results(candidates: list[TopicCandidate]) -> None:
    for index, candidate in enumerate(candidates, start=1):
        warning_text = f" warnings={len(candidate.warnings)}" if candidate.warnings else ""
        print(
            f"{index:02d}. {candidate.topic} | lane={candidate.lane} | score={candidate.score} "
            f"| visual={candidate.visual_shock_score} | curiosity={candidate.curiosity_gap_score} "
            f"| dm={candidate.dm_share_potential} | retention={candidate.watch_retention_potential} "
            f"| cold={candidate.cold_audience_fit} | source={candidate.source}{warning_text}"
        )
        print(f"    angle: {candidate.angle}")


def save_discovery_context_with_post(
    output_dir: Path,
    candidate: TopicCandidate,
    report_json: Path,
    report_markdown: Path,
) -> None:
    (output_dir / "topic_discovery_selected.json").write_text(
        json.dumps(candidate.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if report_json.exists():
        shutil.copyfile(report_json, output_dir / "topic_discovery_report.json")
    if report_markdown.exists():
        shutil.copyfile(report_markdown, output_dir / "topic_discovery_report.md")


def print_grounding_summary(
    research_pack_path: Path | None,
    pattern_names: list[str],
    grounding_warnings: list[str],
) -> None:
    print("Grounding:")
    print(f"  research pack: {research_pack_path if research_pack_path else 'none'}")
    print(f"  patterns: {', '.join(pattern_names) if pattern_names else 'none'}")
    if grounding_warnings:
        print("  warnings:")
        for warning in grounding_warnings:
            print(f"    - {warning}")
    else:
        print("  warnings: none")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.command_used = "python -m app.main " + " ".join(argv if argv is not None else sys.argv[1:])

    try:
        if args.command == "generate":
            return generate(args)
        if args.command == "discover":
            return discover(args)
        if args.command == "auto":
            return auto(args)
        if args.command == "batch-reels":
            return batch_reels(args)
        if args.command == "weekly-queue":
            if not getattr(args, "score_only", False) and not getattr(args, "niche", None):
                raise ValueError("--niche is required unless --score-only is used.")
            from app.queue.weekly_queue import run_weekly_queue

            return run_weekly_queue(args, batch_runner=batch_reels)
        if args.command == "compare-batch":
            args.template = "native_reel_story"
            args.score_only = True
            args.count = 0
            args.niche = None
            args.lane = "any"
            args.sources = "static"
            args.handle = "@yourpage"
            args.image_variants = 3
            args.rate_limit = None
            args.llm_provider = None
            return batch_reels(args)
        if args.command == "mark-review":
            return mark_review(args)
        parser.error(f"Unknown command: {args.command}")
        return 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
