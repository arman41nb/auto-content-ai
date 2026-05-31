"""Small FFprobe helpers for local Reel verification."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


def ffprobe_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"video_stream": {}, "audio_stream": {}, "format_duration_seconds": 0.0}
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"video_stream": {}, "audio_stream": {}, "format_duration_seconds": 0.0}
    completed = subprocess.run(
        [ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return {"video_stream": {}, "audio_stream": {}, "format_duration_seconds": 0.0}
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {"video_stream": {}, "audio_stream": {}, "format_duration_seconds": 0.0}

    video_stream: dict[str, Any] = {}
    audio_stream: dict[str, Any] = {}
    for stream in payload.get("streams", []):
        if not isinstance(stream, dict):
            continue
        if stream.get("codec_type") == "video" and not video_stream:
            video_stream = {
                "codec_name": stream.get("codec_name", ""),
                "width": int(stream.get("width", 0) or 0),
                "height": int(stream.get("height", 0) or 0),
                "duration_seconds": _float_or_zero(stream.get("duration")),
            }
        elif stream.get("codec_type") == "audio" and not audio_stream:
            audio_stream = {
                "codec_name": stream.get("codec_name", ""),
                "duration_seconds": _float_or_zero(stream.get("duration")),
            }
    format_payload = payload.get("format", {})
    format_duration = _float_or_zero(format_payload.get("duration")) if isinstance(format_payload, dict) else 0.0
    if video_stream and not video_stream.get("duration_seconds"):
        video_stream["duration_seconds"] = format_duration
    if audio_stream and not audio_stream.get("duration_seconds"):
        audio_stream["duration_seconds"] = format_duration
    return {
        "video_stream": video_stream,
        "audio_stream": audio_stream,
        "format_duration_seconds": format_duration,
    }


def media_duration_seconds(path: Path) -> float:
    summary = ffprobe_summary(path)
    return round(float(summary.get("format_duration_seconds", 0.0) or 0.0), 3)


def video_duration_seconds(path: Path) -> float:
    summary = ffprobe_summary(path)
    video = summary.get("video_stream", {})
    if isinstance(video, dict) and video.get("duration_seconds"):
        return round(float(video.get("duration_seconds", 0.0) or 0.0), 3)
    return media_duration_seconds(path)


def audio_duration_seconds(path: Path) -> float:
    summary = ffprobe_summary(path)
    audio = summary.get("audio_stream", {})
    if isinstance(audio, dict) and audio.get("duration_seconds"):
        return round(float(audio.get("duration_seconds", 0.0) or 0.0), 3)
    return media_duration_seconds(path)


def has_audio_stream(path: Path) -> bool:
    audio = ffprobe_summary(path).get("audio_stream", {})
    return isinstance(audio, dict) and bool(audio)


def media_dimensions(path: Path) -> list[int]:
    video = ffprobe_summary(path).get("video_stream", {})
    if not isinstance(video, dict):
        return [1080, 1920] if path.exists() else []
    width = int(video.get("width", 0) or 0)
    height = int(video.get("height", 0) or 0)
    if width and height:
        return [width, height]
    return [1080, 1920] if path.exists() else []


def _float_or_zero(value: object) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
