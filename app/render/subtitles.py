"""Subtitle cue creation and SRT/ASS writing for native Reels."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.content.reel_schemas import ReelPlan


def build_subtitle_cues(reel_plan: ReelPlan, scene_timings: list[dict[str, object]]) -> list[dict[str, object]]:
    cues: list[dict[str, object]] = []
    for scene, timing in zip(reel_plan.scenes, scene_timings):
        start = float(timing.get("start_seconds", 0.0) or 0.0)
        end = float(timing.get("end_seconds", start + scene.duration_seconds) or start + scene.duration_seconds)
        cues.append(
            {
                "index": scene.scene_number,
                "start_seconds": round(start, 3),
                "end_seconds": round(max(start + 0.8, end), 3),
                "text": scene.voiceover_line,
            }
        )
    return cues


def write_subtitle_files(voiceover_dir: Path, cues: list[dict[str, object]]) -> dict[str, object]:
    voiceover_dir.mkdir(parents=True, exist_ok=True)
    srt_path = voiceover_dir / "subtitles.srt"
    ass_path = voiceover_dir / "subtitles.ass"
    srt_path.write_text(_srt_text(cues), encoding="utf-8")
    ass_path.write_text(_ass_text(cues), encoding="utf-8")
    return {
        "subtitles_created": srt_path.exists() and ass_path.exists(),
        "subtitles_srt_path": str(srt_path),
        "subtitles_ass_path": str(ass_path),
        "subtitle_style": "bold white lower-middle ASS/Pillow style with subtle black stroke and shadow",
        "subtitle_sync_ok": bool(cues),
    }


def _srt_text(cues: list[dict[str, object]]) -> str:
    blocks: list[str] = []
    for index, cue in enumerate(cues, start=1):
        start = _srt_timestamp(float(cue.get("start_seconds", 0.0) or 0.0))
        end = _srt_timestamp(float(cue.get("end_seconds", 0.0) or 0.0))
        text = "\n".join(_wrap_subtitle(str(cue.get("text", "")), 34))
        blocks.append(f"{index}\n{start} --> {end}\n{text}")
    return "\n\n".join(blocks).strip() + "\n"


def _ass_text(cues: list[dict[str, object]]) -> str:
    header = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,54,&H00FFFFFF,&H00FFFFFF,&HAA000000,&H66000000,-1,0,0,0,100,100,0,0,1,4,1,2,96,96,430,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header.rstrip()]
    for cue in cues:
        start = _ass_timestamp(float(cue.get("start_seconds", 0.0) or 0.0))
        end = _ass_timestamp(float(cue.get("end_seconds", 0.0) or 0.0))
        text = r"\N".join(_wrap_subtitle(_escape_ass(str(cue.get("text", ""))), 34))
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
    return "\n".join(lines).strip() + "\n"


def _wrap_subtitle(text: str, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and len(candidate) > max_chars and len(lines) < 1:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    if len(lines) > 2:
        return [" ".join(lines[:-1]), lines[-1]]
    return lines


def _srt_timestamp(seconds: float) -> str:
    millis = int(round(max(0.0, seconds) * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _ass_timestamp(seconds: float) -> str:
    centis = int(round(max(0.0, seconds) * 100))
    hours, remainder = divmod(centis, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, cs = divmod(remainder, 100)
    return f"{hours:d}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _escape_ass(text: str) -> str:
    return text.replace("{", r"\{").replace("}", r"\}")
