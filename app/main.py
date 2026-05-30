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
from app.content.planner import CarouselPlanner
from app.content.schemas import CarouselPlan
from app.discovery.discovery_pipeline import DiscoveryPipeline, write_discovery_reports
from app.discovery.schemas import TopicCandidate
from app.image.pollinations_client import PollinationsClient
from app.image.prompt_builder import build_image_prompt
from app.image.quality import score_candidate, select_best_candidate, selection_to_dict
from app.image.sanitizer import preferred_image_dir, sanitize_post_images
from app.llm.provider_factory import build_llm_providers
from app.quality.contact_sheet import create_qa_contact_sheet
from app.quality.overlay_masks import get_expected_overlay_regions
from app.quality.post_quality_gate import PostQualityReport, run_post_quality_gate
from app.render.carousel_renderer import CarouselRenderer
from app.render.reel_exporter import export_reel_package
from app.research.research_pack_loader import load_research_pack
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
        "--make-reel",
        action="store_true",
        help="Create final_reel/cover.jpg and final_reel/reel.mp4 from generated images when FFmpeg is available.",
    )
    return parser


def generate(args: argparse.Namespace) -> int:
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
    grounding_warnings: list[str] = []
    research_pack_used = "none"
    pattern_library_used = False
    existing_metadata: dict[str, object] = {}

    if args.render_only or args.resume:
        output_dir = resolve_output_dir(config.project_root, args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        plan = load_plan(output_dir / "carousel_plan.json")
        existing_metadata = load_existing_metadata(output_dir)
        apply_plan_defaults(args, plan)
    elif args.plan_file:
        plan = load_plan(resolve_output_dir(config.project_root, args.plan_file))
        apply_plan_defaults(args, plan)
        output_dir = (
            resolve_output_dir(config.project_root, args.output_dir)
            if args.output_dir
            else exporter.create_output_dir(plan.topic, created_at)
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        exporter.save_plan(output_dir, plan)
        planning_info = empty_planning_info(provider="plan_file", model=str(resolve_output_dir(config.project_root, args.plan_file)))
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

    status = "planned"
    raw_dir = output_dir / "raw_images"
    sanitized_dir = output_dir / "sanitized_images"
    final_dir = output_dir / "final_slides"
    image_selection_report: dict[str, object] = {"slides": []}
    render_template_used_per_slide: dict[str, str] = {}
    reel_export: dict[str, object] = {"requested": bool(getattr(args, "make_reel", False)), "created_video": False}
    voiceover_info: dict[str, object] = {"script_created": False, "tts_created": False}
    image_model = "none"
    resume_warnings: list[str] = []

    if args.render_only:
        missing_raw = missing_raw_images(plan, raw_dir)
        if missing_raw:
            print("Missing raw image file(s):", file=sys.stderr)
            for missing in missing_raw:
                print(f"  {missing}", file=sys.stderr)
            return 1
        print("Sanitizing selected raw images before render...")
        sanitizer_report = sanitize_post_images(plan, raw_dir=raw_dir, sanitized_dir=sanitized_dir)
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
            result = export_reel_package(
                plan=plan,
                final_dir=final_dir,
                raw_dir=raw_dir,
                output_dir=output_dir,
                handle=args.handle,
            )
            warnings.extend(result.warnings)
            reel_export = reel_export_metadata(result, requested=True)
            if result.created_video:
                print(f"Reel saved at: {result.reel_path}")
            elif result.cover_path.exists():
                print(f"Reel cover saved at: {result.cover_path}")
            else:
                print(f"Reel package notes saved at: {result.output_dir}")
            voiceover_info = write_voiceover_assets(plan, output_dir, result.reel_path)
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
        quality_report = run_post_quality_gate(output_dir, plan, metadata)
        contact_sheet = create_qa_contact_sheet(
            final_dir=final_dir,
            output_path=output_dir / "qa_contact_sheet.jpg",
            publish_ready=quality_report.publish_ready,
            score=quality_report.score,
            design_score=int(quality_report.details.get("design_score", 0) or 0),
            topic=plan.topic,
            reel_path=str(output_dir / "final_reel" / "reel.mp4") if getattr(args, "make_reel", False) else "",
            cover_path=str(output_dir / "final_reel" / "cover.jpg") if getattr(args, "make_reel", False) else "",
        )
        metadata["qa_contact_sheet"] = str(contact_sheet)
        exporter.save_metadata(output_dir, metadata)
        quality_report = run_post_quality_gate(output_dir, plan, metadata)
        print_generation_summary(output_dir, quality_report, resume_suggestion=True)
        return 0

    if not args.skip_images:
        image_client = PollinationsClient(
            rate_limit_seconds=args.rate_limit
            if args.rate_limit is not None
            else config.pollinations_rate_limit_seconds
        )
        image_model = image_client.model
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
            sanitizer_report = sanitize_post_images(plan, raw_dir=raw_dir, sanitized_dir=sanitized_dir)
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
        result = export_reel_package(
            plan=plan,
            final_dir=final_dir,
            raw_dir=raw_dir,
            output_dir=output_dir,
            handle=args.handle,
        )
        warnings.extend(result.warnings)
        reel_export = reel_export_metadata(result, requested=True)
        if result.created_video:
            print(f"Reel saved at: {result.reel_path}")
        elif result.cover_path.exists():
            print(f"Reel cover saved at: {result.cover_path}")
        else:
            print(f"Reel package notes saved at: {result.output_dir}")
        if not result.created_video:
            for warning in result.warnings:
                print(f"Warning: {warning}", file=sys.stderr)
        voiceover_info = write_voiceover_assets(plan, output_dir, result.reel_path)

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
    metadata = preserve_existing_context(existing_metadata, metadata)
    sanitizer_report = (
        sanitize_post_images(plan, raw_dir=raw_dir, sanitized_dir=sanitized_dir)
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
    quality_report = run_post_quality_gate(output_dir, plan, metadata)
    contact_sheet = create_qa_contact_sheet(
        final_dir=final_dir,
        output_path=output_dir / "qa_contact_sheet.jpg",
        publish_ready=quality_report.publish_ready,
        score=quality_report.score,
        design_score=int(quality_report.details.get("design_score", 0) or 0),
        topic=plan.topic,
        reel_path=str(output_dir / "final_reel" / "reel.mp4") if getattr(args, "make_reel", False) else "",
        cover_path=str(output_dir / "final_reel" / "cover.jpg") if getattr(args, "make_reel", False) else "",
    )
    metadata["qa_contact_sheet"] = str(contact_sheet)
    exporter.save_metadata(output_dir, metadata)
    quality_report = run_post_quality_gate(output_dir, plan, metadata)

    print("Done.")
    print_generation_summary(output_dir, quality_report, resume_suggestion=not quality_report.publish_ready)
    return 0


def write_voiceover_assets(plan: CarouselPlan, output_dir: Path, reel_path: Path) -> dict[str, object]:
    voiceover_dir = output_dir / "voiceover"
    voiceover_dir.mkdir(parents=True, exist_ok=True)
    script = build_voiceover_script(plan)
    script_path = voiceover_dir / "voiceover_script.txt"
    script_path.write_text(script + "\n", encoding="utf-8")

    info: dict[str, object] = {
        "script_created": True,
        "script_path": str(script_path),
        "tts_created": False,
        "tts_path": "",
        "reel_with_voice_path": "",
        "tts_note": "pip install edge-tts",
        "blocking_publish_ready": False,
    }
    edge_tts = shutil.which("edge-tts")
    if not edge_tts:
        return info

    mp3_path = voiceover_dir / "voiceover.mp3"
    completed = subprocess.run(
        [
            edge_tts,
            "--voice",
            "en-US-GuyNeural",
            "--text",
            script,
            "--write-media",
            str(mp3_path),
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
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg and reel_path.exists():
        voiced_path = output_dir / "final_reel" / "reel_with_voice.mp4"
        muxed = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-i",
                str(reel_path),
                "-i",
                str(mp3_path),
                "-shortest",
                "-c:v",
                "copy",
                "-c:a",
                "aac",
                str(voiced_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if muxed.returncode == 0 and voiced_path.exists():
            info["reel_with_voice_path"] = str(voiced_path)
            info["tts_note"] = "voiceover mp3 and reel_with_voice.mp4 created"
        else:
            info["tts_note"] = "voiceover mp3 created; FFmpeg audio mux failed."
            (voiceover_dir / "ffmpeg_voiceover_error.txt").write_text(
                (muxed.stderr or muxed.stdout or "Unknown FFmpeg voiceover error").strip() + "\n",
                encoding="utf-8",
            )
    return info


def build_voiceover_script(plan: CarouselPlan) -> str:
    topic = plan.topic.strip().rstrip("?")
    lower = topic.lower()
    if "ocean" in lower and "overnight" in lower:
        return (
            "What if oceans rose overnight? Streets become rivers first. Then power fails, "
            "roads vanish, and clean water becomes the real problem. You have one question left: "
            "where would you go?"
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
        if not args.resume or slide.slide_number in failed_slide_numbers or not raw_path.exists():
            slides_to_generate.append(slide.slide_number)

    total_requests = len(slides_to_generate) * args.image_variants
    request_count = 0
    for slide in plan.slides:
        built_prompt = build_image_prompt(slide, niche)
        variant_paths = existing_variant_paths(raw_dir, slide.slide_number)
        selected_raw = raw_dir / f"slide_{slide.slide_number:02d}.jpg"
        if args.resume and selected_raw.exists() and selected_raw not in variant_paths:
            variant_paths.append(selected_raw)
        should_generate = slide.slide_number in slides_to_generate

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
                image_client.generate_image(variant_prompt, variant_path)
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
        report["slides"].append(selection_to_dict(selection))
    return report


def existing_variant_paths(raw_dir: Path, slide_number: int) -> list[Path]:
    return sorted(raw_dir.glob(f"slide_{slide_number:02d}_variant_*.jpg"))


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

    config = load_config()
    sources = parse_source_names(args.sources)
    output_dir = resolve_output_dir(config.project_root, args.output)
    pipeline = DiscoveryPipeline.from_names(sources)
    discovery_count = max(args.count, 10)
    candidates = pipeline.discover(niche=args.niche, count=discovery_count, query=args.query, lane=args.lane)
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
        warnings=pipeline.warnings,
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

    return 0


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

    try:
        if args.command == "generate":
            return generate(args)
        if args.command == "discover":
            return discover(args)
        if args.command == "auto":
            return auto(args)
        parser.error(f"Unknown command: {args.command}")
        return 2
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
