import os
import json
import logging
import subprocess
import math
import re
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from src.config import OUTPUT_DIR

# ---------------------------------------------------------
# CENTRALIZED LAYOUT CONFIGURATION
# ---------------------------------------------------------
LAYOUT_CONFIG = {
    "subtitle_margin_v": 480,       # Vertical margin from bottom for subtitles
    "host_pos_x": "(W-w)/2",        # Center
    "host_pos_y": 700,              # Lower center
}
# ---------------------------------------------------------

# Configure logging
logger = logging.getLogger(__name__)


def get_audio_duration(file_path):
    """Query duration of audio file using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())


def get_video_info(file_path):
    """Query dimensions and duration of video file using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,duration",
        "-of", "json", file_path
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    info = json.loads(result.stdout)
    stream = info["streams"][0]
    
    width = int(stream["width"])
    height = int(stream["height"])
    duration = float(stream.get("duration", 5.0))
    return width, height, duration


def format_ass_time(seconds):
    """Convert float seconds to ASS subtitle timestamp format H:MM:SS.cs."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int(round((seconds % 1) * 100))
    
    if centiseconds >= 100:
        secs += 1
        centiseconds -= 100
    if secs >= 60:
        minutes += 1
        secs -= 60
    if minutes >= 60:
        hours += 1
        minutes -= 60
        
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"


def generate_ass_file(processed_scenes, total_duration, subtitle_style=None, ass_path=None):
    if not ass_path:
        ass_path = os.path.join(OUTPUT_DIR, "subs.ass")
    """
    Write ASS subtitle file with PE-engineered style parameters.
    Now accepts subtitle_style config from the Prompt Engineer AI for:
    - Font name, size, colors
    - Emphasis word coloring
    - MarginV safe zone placement
    - Outline and shadow depth
    """
    if not subtitle_style:
        font_name = "Arial Black"
        font_size = 112
        primary_color = "&H00FFFFFF"    # Crisp White
        emphasis_color = "&H002EFFFF"   # Vibrant Gold / Yellow
        outline_color = "&H00000000"    # Deep Black Outline
        outline_width = 10
        shadow_depth = 0
        margin_v = LAYOUT_CONFIG["subtitle_margin_v"]
        alignment = 2  # Bottom center alignment
    else:
        font_name = subtitle_style.get("font_name", "Arial Black")
        font_size = 112
        primary_color = subtitle_style.get("primary_color", "&H00FFFFFF")
        emphasis_color = subtitle_style.get("emphasis_color", "&H0000FFA3") # Electric Neon Green
        outline_color = subtitle_style.get("outline_color", "&H00000000")
        outline_width = 10
        shadow_depth = 0
        margin_v = subtitle_style.get("margin_v", LAYOUT_CONFIG["subtitle_margin_v"])
        alignment = 2
        logger.info(f"📝 Using High-Retention subtitle styling: {font_name} {font_size}pt, MarginV={margin_v}")

    ass_header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1080\n"
        "PlayResY: 1920\n"
        "ScaledBorderAndShadow: yes\n"
        "WrapStyle: 1\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},{primary_color},&H000000FF,{outline_color},"
        f"&H80000000,-1,0,0,0,100,100,0,0,1,{outline_width},{shadow_depth},{alignment},"
        f"60,60,{margin_v},1\n"
        f"Style: Emphasis,{font_name},{font_size + 4},{emphasis_color},&H000000FF,{outline_color},"
        f"&H80000000,-1,0,0,0,105,105,0,0,1,{outline_width + 2},{shadow_depth},{alignment},"
        f"60,60,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    # ── Parable Style: No Narration Captions, Only Diagram Callouts ──
    dialogue_lines = []
    current_time_offset = 0.0
    
    for scene in processed_scenes:
        dur = scene.get("audio_duration", 2.0)
        start_time = current_time_offset
        end_time = start_time + dur
        
        start_str = format_ass_time(start_time)
        end_str = format_ass_time(end_time)
        
        # Only render diagram callouts. No narration subtitles.
        callouts = scene.get("diagram_callouts", [])
        if callouts:
            # Join callouts with a newline (\N in ASS syntax)
            text = "\\N".join(callouts)
            # Center alignment (\an5) for diagram labels
            pos_tag = r"{\an5}"
            
            dialogue_lines.append(
                f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{pos_tag}{text}"
            )
            
        current_time_offset += dur
        
    ass_content = ass_header + "\n".join(dialogue_lines) + "\n"
    
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_content)
        
    return ass_path


def process_single_scene_media(scene, assembly_config=None):
    """
    Renders animated media for a single host scene.
    """
    idx = scene["index"]
    dur = scene["audio_duration"]
    audio_path = scene["audio_path"]
    out_video_path = os.path.join(OUTPUT_DIR, f"scene_{idx}_processed.mp4")

    fps = 25
    if assembly_config:
        fps = assembly_config.get("output_fps", 25)

    logger.info(f"🎬 Processing Scene {idx} (duration: {dur}s, fps: {fps})")

    # ── Step 1: Render Full-Bleed B-Roll ───────────

    asset = scene.get("visual_asset")
    asset_path = None
    if isinstance(asset, str):
        asset_path = asset
    elif isinstance(asset, dict) and asset.get("path"):
        asset_path = asset.get("path")
        
    if asset_path and os.path.exists(asset_path):

        
        if asset_path.lower().endswith(('.mp4', '.mov', '.webm', '.avi')):
            # It's a video. Scale and crop to 1080x1920 to fill the entire screen (Full-Bleed)
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", asset_path,
                "-t", f"{dur:.3f}",
                "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-r", str(fps),
                "-an",
                out_video_path,
            ]
        else:
            # It's an image. Use Ken Burns effect to fill 1080x1920
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", asset_path,
                "-t", f"{dur:.3f}",
                "-vf", (
                    f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
                    f"zoompan=z='min(max(zoom,pzoom)+0.0003,1.03)':"
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                    f"d={int(fps * dur)}:s=1080x1920,fps={fps}"
                ),
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-r", str(fps),
                "-an",
                out_video_path,
            ]
    else:
        # Fallback to black screen if no asset
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:s=1080x1920:d={dur:.3f}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-an",
            out_video_path,
        ]

    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return out_video_path


def assemble_final_video(processed_scenes, subtitle_style=None, assembly_config=None, mascot_timeline=None):
    """
    Stitch clips, merge audio, generate subtitle overlays, and burn into final file.
    Now accepts PE-engineered configs for subtitle styling, assembly parameters, and mascot timeline.
    """
    logger.info("=== 🎬 Assembling Final Video ===")
    
    # Extract PE assembly parameters
    loudness_i = -14
    loudness_lra = 11
    loudness_tp = -1.5
    logo_scale = 150
    logo_padding = 30
    output_codec = "libx264"
    audio_codec = "aac"
    
    if assembly_config:
        loudness_i = assembly_config.get("loudness_target_i", -14)
        loudness_lra = assembly_config.get("loudness_lra", 11)
        loudness_tp = assembly_config.get("loudness_tp", -1.5)
        logo_scale = assembly_config.get("logo_scale_width", 150)
        logo_padding = assembly_config.get("logo_padding", 30)
        output_codec = assembly_config.get("output_codec", "libx264")
        audio_codec = assembly_config.get("audio_codec", "aac")
        logger.info(f"🎬 Using PE assembly config: loudness={loudness_i}LUFS, logo={logo_scale}px, fps={assembly_config.get('output_fps', 25)}")
    
    # 1. Process individual scene media clips matching audio lengths
    video_clips = []
    total_audio_dur = 0.0
    for scene in processed_scenes:
        audio_dur = get_audio_duration(scene["audio_path"])
        scene["audio_duration"] = audio_dur
        total_audio_dur += audio_dur
        
        out_v = process_single_scene_media(scene, assembly_config=assembly_config)
        video_clips.append(out_v)
        
    logger.info(f"Total pipeline duration: {total_audio_dur}s")

    # 2. Write file lists for FFmpeg concatenation
    video_list_path = os.path.join(OUTPUT_DIR, "video_list.txt")
    audio_list_path = os.path.join(OUTPUT_DIR, "audio_list.txt")
    
    with open(video_list_path, "w") as f:
        for clip in video_clips:
            f.write(f"file '{clip}'\n")
            
    with open(audio_list_path, "w") as f:
        for scene in processed_scenes:
            f.write(f"file '{scene['audio_path']}'\n")
            
    # 3. Concatenate video segments
    logger.info("Stitching video segments...")
    combined_video = os.path.join(OUTPUT_DIR, "combined_video.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", video_list_path, "-c", "copy", combined_video
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    
    # 4. Concatenate audio segments
    logger.info("Stitching audio segments...")
    combined_audio = os.path.join(OUTPUT_DIR, "combined_audio.mp3")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", audio_list_path, "-c", "copy", combined_audio
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

    # 4.5 Mix BGM and SFX
    logger.info("Mixing BGM and SFX with voiceover...")
    combined_audio_mixed = os.path.join(OUTPUT_DIR, "combined_audio_mixed.mp3")
    mix_script = os.path.join(os.getcwd(), "scripts", "mix_audio.py")
    subprocess.run([
        "python", mix_script, combined_audio, combined_audio_mixed
    ], check=True)

    # 5. Merge stitched video and stitched audio with playback speed synchronization
    logger.info("Merging audio and video tracks with auto duration sync...")
    video_with_audio = os.path.join(OUTPUT_DIR, "video_with_audio.mp4")

    # Check durations and adjust playback speed if there is any mismatch
    v_dur = get_audio_duration(combined_video) if os.path.exists(combined_video) else total_audio_dur
    a_dur = total_audio_dur
    
    if abs(v_dur - a_dur) > 0.05 and v_dur > 0:
        logger.info(f"Adjusting video playback speed: v_dur={v_dur:.2f}s -> target a_dur={a_dur:.2f}s")
        speed_factor = a_dur / v_dur
        subprocess.run([
            "ffmpeg", "-y", "-i", combined_video, "-i", combined_audio_mixed,
            "-filter_complex", f"[0:v]setpts={speed_factor}*PTS[v_synced]",
            "-map", "[v_synced]", "-map", "1:a:0",
            "-c:v", output_codec, "-c:a", audio_codec,
            "-t", f"{a_dur:.3f}",
            video_with_audio
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    else:
        subprocess.run([
            "ffmpeg", "-y", "-i", combined_video, "-i", combined_audio_mixed,
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", audio_codec,
            "-t", f"{a_dur:.3f}",
            video_with_audio
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    # 6. Generate subtitle ASS file with PE style config
    ass_path = generate_ass_file(processed_scenes, total_audio_dur, subtitle_style=subtitle_style)
    
    # 7. Build filter for logo, subtitles, loudness, and BGM
    final_output = os.path.join(OUTPUT_DIR, "distribution_ready.mp4")
    logger.info("Applying Logo, Subtitles, BGM, and Audio Loudness...")
    
    inputs = ["-i", video_with_audio]
    input_count = 1  # 0 is video_with_audio
    
    # Add logo as input 1
    inputs.extend(["-i", "logo_transparent.png"])
    input_count += 1
    
    filter_chains = []
    
    # Scale logo and place at top right with PE-configured size/padding
    filter_chains.append(f"[1:v]scale={logo_scale}:-1[logo];[0:v][logo]overlay=W-w-{logo_padding}:{logo_padding}[v1]")
    
    # Burn subtitles on top
    # On Windows, FFmpeg filter strings break if there's an unescaped colon (like C:\) in absolute paths.
    # It is much safer to use a relative path with forward slashes.
    ass_path_rel = os.path.relpath(ass_path, os.getcwd())
    ass_path_escaped = ass_path_rel.replace('\\', '/')
    filter_chains.append(f"[v1]subtitles='{ass_path_escaped}'[vout]")
    
    # Audio Loudness Normalization with PE-configured parameters
    a_in = "0:a"
        
    filter_chains.append(
        f"[{a_in}]loudnorm=I={loudness_i}:LRA={loudness_lra}:TP={loudness_tp}[aout]"
    )
    
    complex_filter = ";".join(filter_chains)
    
    subprocess.run([
        "ffmpeg", "-y", *inputs,
        "-filter_complex", complex_filter,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", output_codec, "-c:a", audio_codec,
        final_output
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    
    logger.info(f"✅ Final output video created at {final_output}")
    return final_output, total_audio_dur
