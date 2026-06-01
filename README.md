# Auto Carousel AI

Local-first AI content engine for Unreal Science & What-If Instagram/Reel content.

Auto Carousel AI is an experimental Growth MVP that discovers science and what-if topics, scores them for short-form growth potential, plans carousel posts with optional LLM fallback, generates images with Pollinations, renders portrait carousel slides, and can export a Reel package with local FFmpeg.

Manual review is required before posting. The project does not auto-publish to Instagram.

## Features

- Topic discovery from static packs and optional external sources.
- Lane scoring for `what_if_disaster`, `extreme_science`, `future_scenario`, and `any`.
- LLM fallback across configured providers.
- Pollinations image generation with multiple image variants.
- Carousel rendering with Pillow.
- Native `native_reel_story` output for 1080x1920, five-scene cinematic Reels.
- Reel export with FFmpeg or the bundled `imageio-ffmpeg` fallback.
- Optional `edge-tts` voiceover generation and audio muxing.
- Quality gate reports for generated post packages.
- Recovery flags for render-only and resume workflows.

## Setup

From this folder:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Then edit `.env` and add only the keys you want to use.

Required environment keys are all optional at runtime:

- `GROQ_API_KEY` optional
- `GEMINI_API_KEY` optional
- `OPENROUTER_API_KEY` optional
- `CEREBRAS_API_KEY` optional

The app skips missing LLM providers in `auto` mode. Discovery can also use `NASA_API_KEY`; if it is empty, the NASA source falls back to public demo access where supported.

## FFmpeg and Voiceover

Reel MP4 export uses FFmpeg on `PATH` when available:

```bash
ffmpeg -version
```

If the system command is unavailable, the app falls back to `imageio-ffmpeg`.
Voiceover uses `edge-tts` when installed and writes `voiceover/voiceover_script.txt` even if TTS fails. Native Reel voiceover also asks edge-tts for `voiceover/voiceover_raw.srt` so kinetic captions can be timed from the same synthesis request.

## Example Commands

Discover static science topics:

```bash
python -m app.main discover --niche science --lane any --count 10 --sources static
```

Run discovery, generation, carousel rendering, and Reel export:

```bash
python -m app.main auto --niche science --lane any --count 1 --sources static --handle "@yourpage" --image-variants 3 --rate-limit 25 --llm-provider auto --make-reel
```

Generate a native Reel story with synced kinetic captions:

```bash
python -m app.main auto --niche science --lane any --count 1 --sources static --handle "@yourpage" --image-variants 3 --rate-limit 25 --llm-provider auto --make-reel --template native_reel_story --voiceover
```

Native Reel outputs include `final_reel/reel.mp4`, `final_reel/reel_with_voice_kinetic_subtitles.mp4`, `final_reel/reel_with_voice_subtitled.mp4`, `final_reel/cover.jpg`, `final_reel/edit_beats.json`, `final_reel/scene_timing.json`, `final_reel/frames/frame_01.jpg` through `frame_05.jpg`, `reel_plan.json`, and voiceover timing assets when requested.

Re-render an existing package without calling an LLM or image provider:

```bash
python -m app.main generate --output-dir "outputs/posts/..." --render-only
```

Resume a partial package, regenerate missing image variants, and make a Reel:

```bash
python -m app.main generate --output-dir "outputs/posts/..." --resume --image-variants 3 --rate-limit 25 --make-reel
```

## Project Layout

```text
app/                  CLI, planning, discovery, rendering, quality, and provider code
data/research/        Local research packs
data/patterns/        Carousel pattern library
tests/                Unit tests
outputs/posts/        Generated post packages, ignored by git
outputs/discovery/    Generated discovery reports, ignored by git
outputs/qa/           Local QA/audit reports, ignored by git
```

## Dependencies

Core Python dependencies are listed in `requirements.txt`:

- `requests`
- `python-dotenv`
- `pydantic`
- `Pillow`

Optional tools and libraries:

- `edge-tts` for optional voiceover generation.
- `imageio-ffmpeg` for local FFmpeg fallback.
- `pytesseract` optional for OCR-based accidental text detection when Tesseract is installed locally.
- `pyttsx3` is not required by the current CLI.

No unnecessary heavy dependencies are required for the MVP.

## Current Status

This is an experimental Growth MVP. It is designed for local iteration, manual QA, and manual posting only.

Current limitations:

- Manual review required before posting.
- No Instagram auto-publishing.
- No scheduling, dashboard, database, or deployment configuration.
- LLM providers and Pollinations require internet access at runtime.
- Generated image quality can vary and should be reviewed.
- Lightweight quality gates are helpful but not a substitute for editorial review.

## Safety

Do not commit `.env` or generated outputs.

Ignored local artifacts include generated posts, discovery reports, QA reports, logs, caches, virtual environments, and generated media files.
