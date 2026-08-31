"""
src/rendering/subtitles.py

ASS Subtitle Generator

Converts word-level timing data (from edge-tts) into an Advanced SubStation
Alpha (.ass) subtitle file with high-retention styling.

Subtitle Style Spec:
  - Font: Arial Bold
  - Size: 112pt
  - Color: White with black outline (high contrast)
  - Position: Bottom-third (Margin V = 120px from bottom)
  - Alignment: Centered (horizontal)
  - Word highlighting: Each word appears as it is spoken (karaoke-style)

Why .ass over .srt?
  .ass supports per-word timing, custom fonts, outlines, and exact positioning —
  essential for the High-Retention shorts look.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="subtitle_generation")


# ──────────────────────────────────────────────────────────────────────────────
#  ASS File Header
# ──────────────────────────────────────────────────────────────────────────────

def _ass_header(
    video_width: int = settings.VIDEO_WIDTH,
    video_height: int = settings.VIDEO_HEIGHT,
) -> str:
    """
    Returns the ASS file header with City-of-Finance style subtitle definition.

    Style: Bold white text, thick black border, bottom-centered, 3-word chunks.
    Alignment=2 = bottom-center (standard bottom subtitles).
    Outline=5 = very thick black stroke for mobile readability.
    Shadow=2 = subtle drop shadow for depth.
    MarginV=160 = keeps text well above bottom edge on 9:16 vertical.
    """
    font = "Arial Black"
    font_size = 110        # Larger — readable on mobile in 9:16
    primary_color = "&H0000FFFF"   # Yellow text (BGR format in ASS)
    outline_color = "&H00000000"   # Black outline
    back_color = "&H00000000"      # Shadow color (black, mostly transparent)
    bold = -1              # Bold on
    outline_px = 6         # Very thick black border
    shadow_px = 3          # Substantial drop shadow
    alignment = 2          # Bottom-center
    margin_v = 180         # Pixels from bottom edge

    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{primary_color},&H00FFFFFF,{outline_color},{back_color},{bold},0,0,0,100,100,1,0,1,{outline_px},{shadow_px},{alignment},80,80,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


# ──────────────────────────────────────────────────────────────────────────────
#  Time Formatting
# ──────────────────────────────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    """Convert float seconds to ASS timestamp format: H:MM:SS.cs"""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ──────────────────────────────────────────────────────────────────────────────
#  Dialogue Line Builder
# ──────────────────────────────────────────────────────────────────────────────

def _build_dialogue_lines(
    word_timings: list[dict],
    scene_audio_offset: float = 0.0,
    max_words_per_line: int = 2,
) -> list[str]:
    """
    Groups word timings into subtitle lines (max N words per line).
    Each line is a single ASS Dialogue event.

    Args:
        word_timings: list of {"word": str, "start": float, "end": float}
        scene_audio_offset: the audio start time (seconds) of this scene in the full video
        max_words_per_line: how many words appear per subtitle card
    """
    if not word_timings:
        return []

    lines = []
    chunks = [
        word_timings[i : i + max_words_per_line]
        for i in range(0, len(word_timings), max_words_per_line)
    ]

    for chunk in chunks:
        start = scene_audio_offset + chunk[0]["start"]
        end = scene_audio_offset + chunk[-1]["end"]
        # Add a small gap so adjacent lines don't bleed into each other
        end = min(end + 0.05, start + 4.0)

        text = " ".join(w["word"] for w in chunk)
        text = text.upper()  # high-retention style: all caps

        line = (
            f"Dialogue: 0,{_fmt_time(start)},{_fmt_time(end)},"
            f"Default,,0,0,0,,{text}"
        )
        lines.append(line)

    return lines


# ──────────────────────────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────────────────────────

def generate_ass_file(
    voice_results: list[dict],
    output_path: Path,
) -> Path:
    """
    Generate the full .ass subtitle file from all scene voice results.

    Args:
        voice_results: output of voice_agent.synthesize_all_scenes()
                       Each item has: scene_id, duration, word_timings
        output_path: where to write the .ass file

    Returns:
        The output_path (for chaining)
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build the full ASS file
    lines: list[str] = [_ass_header()]

    cumulative_offset = 0.0
    for result in voice_results:
        word_timings = result.get("word_timings", [])
        duration = result.get("duration", 0.0)

        dialogue_lines = _build_dialogue_lines(
            word_timings=word_timings,
            scene_audio_offset=cumulative_offset,
        )
        lines.extend(dialogue_lines)
        cumulative_offset += duration

    ass_content = "\n".join(lines)
    output_path.write_text(ass_content, encoding="utf-8")

    total_lines = len([l for l in lines if l.startswith("Dialogue:")])
    log.info(
        "Generated subtitle file: %s (%d dialogue events, total duration: %.1fs)",
        output_path.name, total_lines, cumulative_offset
    )
    return output_path


def generate_ass_from_timings_files(
    timings_dir: Path,
    scene_durations: list[float],
    output_path: Path,
) -> Path:
    """
    Alternative: generate .ass by loading per-scene timing JSON files from disk.
    Useful if voice synthesis was run separately.
    """
    all_results = []
    for i, duration in enumerate(scene_durations, start=1):
        timings_file = timings_dir / f"scene_{i}_timings.json"
        word_timings = []
        if timings_file.exists():
            word_timings = json.loads(timings_file.read_text(encoding="utf-8"))
        all_results.append({
            "scene_id": i,
            "duration": duration,
            "word_timings": word_timings,
        })
    return generate_ass_file(all_results, output_path)
