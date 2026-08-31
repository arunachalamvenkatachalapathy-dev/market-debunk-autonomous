"""
src/rendering/subtitles.py

Clean, Stable Middle-Bottom Captions (YouTube Shorts & Instagram Reels Standard)

Generates Advanced SubStation Alpha (.ass) subtitles designed for high-retention:
  - Font: Inter / Montserrat / Arial (Bold, modern, aesthetic)
  - Color: Clean crisp White text with subtle black outline and drop shadow
  - Placement: Middle-Bottom (MarginV = 380px) to stay above platform overlay UI
  - Stability: 1 anchored, balanced block per scene — ZERO vertical jumping or flashing
  - Animation: Clean instant cut synchronized with natural speech
"""
from __future__ import annotations

import json
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
    Returns the ASS header for clean, modern social video captions.

    Style Spec:
      - Font: Inter (clean, aesthetic, highly legible)
      - Font size: 76pt (perfect balance for 9:16 mobile viewing)
      - Colors: White text (&H00FFFFFF), sharp outline (&H00000000), subtle shadow (&H80000000)
      - Position: Alignment=2 (Bottom-Center), MarginV=380 (Middle-Bottom above platform UI)
      - BorderStyle=1: Text outline with shadow
    """
    font = "Inter, Montserrat, Arial"
    font_size = 76
    primary_color = "&H00FFFFFF"   # Crisp white (BGR format in ASS)
    outline_color = "&H00000000"   # Black outline
    back_color = "&H80000000"      # Semi-transparent dark shadow
    bold = -1                      # Bold on
    outline_px = 3                 # Clean 3px border
    shadow_px = 2                  # Subtle 2px drop shadow
    alignment = 2                  # Bottom-center
    margin_v = 380                 # Middle-bottom: 380px from bottom edge

    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{font_size},{primary_color},&H00FFFFFF,{outline_color},{back_color},{bold},0,0,0,100,100,1,0,1,{outline_px},{shadow_px},{alignment},70,70,{margin_v},1

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
#  Balanced Caption Text Formatter
# ──────────────────────────────────────────────────────────────────────────────

def _format_caption_text(text: str, max_chars_per_line: int = 34) -> str:
    """
    Formats scene narration into 1 or 2 clean, balanced lines with an explicit \\N break.
    This guarantees zero jumping because the text remains centered and symmetrical.
    """
    text = text.strip()
    words = text.split()
    if not words:
        return ""

    if len(text) <= max_chars_per_line:
        return text

    # Find the best whitespace split point closest to the exact middle
    total_len = len(text)
    half = total_len // 2
    best_split = 1
    min_diff = 9999

    cur = 0
    for i, w in enumerate(words[:-1]):
        cur += len(w) + 1
        diff = abs(cur - half)
        if diff < min_diff:
            min_diff = diff
            best_split = i + 1

    line1 = " ".join(words[:best_split])
    line2 = " ".join(words[best_split:])
    return f"{line1}\\N{line2}"


# ──────────────────────────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────────────────────────

def generate_ass_file(
    voice_results: list[dict],
    output_path: Path,
) -> Path:
    """
    Generate clean, stable middle-bottom subtitles.
    1 continuous, perfectly anchored subtitle event per scene — no jumping between words.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [_ass_header()]

    cumulative_offset = 0.0
    for result in voice_results:
        duration = result.get("duration", 0.0)
        narration = result.get("narration", "")

        # Fallback to word timings if narration key not present
        if not narration and "word_timings" in result:
            narration = " ".join(w["word"] for w in result["word_timings"])

        if narration:
            formatted_text = _format_caption_text(narration)
            # Offset start slightly after pre-silence and end before trailing silence
            start_time = max(0.0, cumulative_offset + 0.15)
            end_time = max(start_time + 0.5, cumulative_offset + duration - 0.15)

            line = (
                f"Dialogue: 0,{_fmt_time(start_time)},{_fmt_time(end_time)},"
                f"Default,,0,0,0,,{formatted_text}"
            )
            lines.append(line)

        cumulative_offset += duration

    ass_content = "\n".join(lines)
    output_path.write_text(ass_content, encoding="utf-8")

    total_lines = len([l for l in lines if l.startswith("Dialogue:")])
    log.info(
        "Generated clean stable subtitles: %s (%d scene dialogue events, total duration: %.1fs)",
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
