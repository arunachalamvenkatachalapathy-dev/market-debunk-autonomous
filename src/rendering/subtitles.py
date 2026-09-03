"""
src/rendering/subtitles.py

ASS Subtitle Generator

Converts word-level timing data into an Advanced SubStation
Alpha (.ass) subtitle file with high-retention styling.

Subtitle Style Spec:
  - Font: Bebas Neue (cinematic impact style)
  - Size: 112pt
  - Color: White with black outline (high contrast)
  - Position: lower-middle safe zone, above YouTube Shorts handle/description UI
  - Alignment: Centered (horizontal), 80% text width
  - Word highlighting: CapCut-style active word emphasis (5 words per group)

Why .ass over .srt?
  .ass supports per-word timing, custom fonts, outlines, and exact positioning -
  essential for the High-Retention shorts look.
"""
from __future__ import annotations

import json
from pathlib import Path

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="subtitle_generation")


# ------------------------------------------------------------------------------
#  ASS File Header
# ------------------------------------------------------------------------------

def _ass_header(
    video_width: int = settings.VIDEO_WIDTH,
    video_height: int = settings.VIDEO_HEIGHT,
) -> str:
    """
    Returns the ASS file header with modern short-form subtitle styling.

    Style: chunky white Bebas Neue text, strong black stroke, amber active-word emphasis.
    Captions sit in the lower-middle safe zone so YouTube Shorts UI does not
    cover them after upload.
    Alignment=2 = bottom-center. WrapStyle=2 = no auto-wrap (we control grouping).
    MarginL/R = 108px each => 80% of 1080px canvas used for text.
    """
    font = settings.SUBTITLE_FONT
    font_size = settings.SUBTITLE_FONT_SIZE
    primary_color = "&H00FFFFFF"   # Pure white text
    outline_color = "&H00000000"   # Black border
    back_color = "&H7A000000"      # Soft shadow color
    bold = -1
    outline_px = 5
    shadow_px = 2
    alignment = 2                  # Bottom-center
    margin_v = settings.SUBTITLE_MARGIN_V
    margin_h = settings.SUBTITLE_MARGIN_H
    border_style = 1

    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {video_width}\n"
        f"PlayResY: {video_height}\n"
        "ScaledBorderAndShadow: yes\n"
        "YCbCr Matrix: TV.709\n"
        "WrapStyle: 2\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font},{font_size},{primary_color},&H00FFFFFF,{outline_color},{back_color},{bold},0,0,0,100,100,2,0,{border_style},{outline_px},{shadow_px},{alignment},{margin_h},{margin_h},{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )


# ------------------------------------------------------------------------------
#  Time Formatting
# ------------------------------------------------------------------------------

def _fmt_time(seconds: float) -> str:
    """Convert float seconds to ASS timestamp format: H:MM:SS.cs"""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds % 1) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


# ------------------------------------------------------------------------------
#  Dialogue Line Builder
# ------------------------------------------------------------------------------

def _build_dialogue_lines(
    word_timings: list[dict],
    scene_audio_offset: float = 0.0,
    max_words_per_line: int = 5,
) -> list[str]:
    """
    Groups word timings into subtitle chunks and creates dynamic word-by-word highlighting.
    Creates multiple ASS Dialogue lines for the same chunk, shifting the highlight color
    to the actively spoken word.

    Uses 5 words per group (up from 3) so captions stay on screen long enough to read
    naturally without feeling choppy.
    """
    if not word_timings:
        return []

    lines = []
    chunks = [
        word_timings[i : i + max_words_per_line]
        for i in range(0, len(word_timings), max_words_per_line)
    ]

    highlight_color = r"{\c&H55A8E8&\fscx112\fscy112\t(0,120,\fscx100\fscy100)}"
    dim_color = r"{\c&HFFFFFF&}"
    reset_color = r"{\rDefault}"

    for chunk in chunks:
        chunk_start = scene_audio_offset + chunk[0]["start"]
        chunk_end = scene_audio_offset + chunk[-1]["end"]
        if chunk_end <= chunk_start:
            chunk_end = chunk_start + 0.6

        for i, active_word_data in enumerate(chunk):
            start = scene_audio_offset + active_word_data["start"]
            next_start = (
                scene_audio_offset + chunk[i + 1]["start"]
                if i + 1 < len(chunk)
                else chunk_end
            )
            end = max(next_start, start + 0.12)

            formatted_words = []
            for j, w in enumerate(chunk):
                word = w["word"].upper()
                if i == j:
                    formatted_words.append(f"{highlight_color}{word}{reset_color}")
                else:
                    formatted_words.append(f"{dim_color}{word}{reset_color}")

            text = " ".join(formatted_words)
            line = (
                f"Dialogue: 0,{_fmt_time(start)},{_fmt_time(end)},"
                f"Default,,0,0,0,,{text}"
            )
            lines.append(line)

    return lines


# ------------------------------------------------------------------------------
#  Public API
# ------------------------------------------------------------------------------

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
