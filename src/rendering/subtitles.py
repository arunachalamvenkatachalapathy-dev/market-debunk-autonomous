"""
src/rendering/subtitles.py

Clean, CapCut-Style Viral Captions

Generates Advanced SubStation Alpha (.ass) subtitles designed for high-retention:
  - Font: Inter / Montserrat / Arial (Bold, modern, aesthetic)
  - Color: Clean crisp White text with subtle black outline and drop shadow
  - Placement: Middle-Bottom (MarginV = 380px) to stay above platform overlay UI
  - Stability: 1 anchored, balanced block per scene - ZERO vertical jumping
  - Animation: The *currently spoken word* pops in Yellow with a slight scale bump (CapCut Viral Style)
"""
from __future__ import annotations

import json
from pathlib import Path

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
#  Public API
# ──────────────────────────────────────────────────────────────────────────────

def generate_ass_file(
    voice_results: list[dict],
    output_path: Path,
) -> Path:
    """
    Generate CapCut-style viral subtitles.
    The sentence stays completely locked in place (no jumping).
    Overlapping Dialogue events highlight the currently spoken word in Yellow and scale it up.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = [_ass_header()]

    cumulative_offset = 0.0
    for result in voice_results:
        duration = result.get("duration", 0.0)
        word_timings = result.get("word_timings", [])

        if word_timings:
            scene_start = max(0.0, cumulative_offset + 0.15)
            scene_end = max(scene_start + 0.5, cumulative_offset + duration - 0.15)
            
            # Format the sentence with \N if it's too long, but for exact word mapping
            # we must find the midpoint word to insert the \N correctly.
            total_chars = sum(len(w['word']) for w in word_timings)
            half_chars = total_chars // 2
            
            best_split_idx = -1
            if total_chars > 34:
                min_diff = 9999
                cur = 0
                for i, w in enumerate(word_timings[:-1]):
                    cur += len(w['word']) + 1
                    diff = abs(cur - half_chars)
                    if diff < min_diff:
                        min_diff = diff
                        best_split_idx = i
            
            # Generate one Dialogue event for each spoken word
            for i, active_w in enumerate(word_timings):
                # The word event starts when the word starts, and ends when the next word starts
                # (or when the scene ends, for the last word)
                start_t = cumulative_offset + active_w['start']
                if i + 1 < len(word_timings):
                    end_t = cumulative_offset + word_timings[i+1]['start']
                else:
                    end_t = scene_end
                    
                # Constrain to scene bounds
                start_t = max(scene_start, min(start_t, scene_end))
                end_t = max(start_t + 0.01, min(end_t, scene_end))
                
                text_parts = []
                for j, render_w in enumerate(word_timings):
                    w_text = render_w['word']
                    prefix = ""
                    if j > 0:
                        if j - 1 == best_split_idx:
                            prefix = "\\N"
                        else:
                            prefix = " "
                    
                    if j == i:
                        # Highlight active word (Yellow, 115% scale)
                        text_parts.append(f"{prefix}{{\\c&H00FFFF&}}{{\\fscx115\\fscy115}}{w_text}{{\\rDefault}}")
                    else:
                        text_parts.append(f"{prefix}{w_text}")
                
                full_text = "".join(text_parts)
                line = (
                    f"Dialogue: 0,{_fmt_time(start_t)},{_fmt_time(end_t)},"
                    f"Default,,0,0,0,,{full_text}"
                )
                lines.append(line)

        cumulative_offset += duration

    ass_content = "\n".join(lines)
    output_path.write_text(ass_content, encoding="utf-8")

    total_lines = len([l for l in lines if l.startswith("Dialogue:")])
    log.info(
        "Generated CapCut-style subtitles: %s (%d highlight events, total duration: %.1fs)",
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
