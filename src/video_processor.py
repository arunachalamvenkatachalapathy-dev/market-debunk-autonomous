"""
Video processor — stitches clips, burns subtitles, overlays mascots, normalizes audio.
Now accepts configs from the Prompt Engineer AI for subtitle styling and assembly parameters.
"""
import os
import json
import logging
import subprocess
from src.config import OUTPUT_DIR

# ---------------------------------------------------------
# CENTRALIZED LAYOUT CONFIGURATION
# ---------------------------------------------------------
# Edit these variables to adjust the visual layout of the final video.
LAYOUT_CONFIG = {
    "subtitle_margin_v": 450,       # Vertical margin from bottom for subtitles (higher number = higher up)
    "mascot_pos_x": "(W-w)/2",      # Mascot X position (default: centered)
    "mascot_pos_y": "300",      # Mascot Y position (default: comfortably above subtitles)
    "mascot_height": 400,           # Mascot overlay height (pixels)
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
    # Hormozi-style defaults
    if not subtitle_style:
        font_name = "Arial Black"
        font_size = 110
        primary_color = "&H00FFFFFF" # White
        emphasis_color = "&H0000D7FF" # Gold/Yellow
        outline_color = "&H00000000"
        outline_width = 8
        shadow_depth = 0
        margin_v = LAYOUT_CONFIG["subtitle_margin_v"] # Safe zone margin from bottom
        alignment = 5  # Middle center alignment
    else:
        font_name = subtitle_style.get("font_name", "Arial Black")
        font_size = 110
        primary_color = subtitle_style.get("primary_color", "&H00FFFFFF")
        emphasis_color = subtitle_style.get("emphasis_color", "&H0000D7FF")
        outline_color = subtitle_style.get("outline_color", "&H00000000")
        outline_width = 8
        shadow_depth = 0
        margin_v = subtitle_style.get("margin_v", LAYOUT_CONFIG["subtitle_margin_v"])
        alignment = 5
        logger.info(f"📝 Using Hormozi-style subtitle overrides: {font_name} {font_size}pt, MarginV={margin_v}")

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
        f"Style: Emphasis,{font_name},{font_size},{emphasis_color},&H000000FF,{outline_color},"
        f"&H80000000,-1,0,0,0,100,100,0,0,1,{outline_width},{shadow_depth},{alignment},"
        f"60,60,{margin_v},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    
    # Collect emphasis words from PE voice config
    all_emphasis_words = set()
    for scene in processed_scenes:
        for word in scene.get("emphasis_words", []):
            all_emphasis_words.add(word.upper())
    
    # Flatten all word timings with absolute offsets
    flat_timings = []
    current_time_offset = 0.0
    
    for scene in processed_scenes:
        dur = scene["audio_duration"]
        for item in scene["word_timings"]:
            word = item["word"].upper()
            flat_timings.append({
                "word": word,
                "abs_time": current_time_offset + item["time_seconds"],
                "is_emphasis": word in all_emphasis_words
            })
        current_time_offset += dur
        
    dialogue_lines = []
    for idx, item in enumerate(flat_timings):
        start = item["abs_time"]
        if idx + 1 < len(flat_timings):
            end = flat_timings[idx+1]["abs_time"]
            # Prevent lingering text during natural pauses
            if end - start > 1.2:
                end = start + 0.8
        else:
            end = start + 1.0
            
        if end > total_duration:
            end = total_duration
            
        start_str = format_ass_time(start)
        end_str = format_ass_time(end)
        word_text = item["word"]
        
        # Use Emphasis style for PE-flagged words
        style = "Emphasis" if item["is_emphasis"] else "Default"
        
        # Add a pop-in scale animation using ASS override tags (scales from 80% to 100% in 100ms)
        pop_tag = r"{\fscx80\fscy80\t(0,100,\fscx100\fscy100)}"
        
        dialogue_lines.append(
            f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{pop_tag}{word_text}"
        )
        
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header)
        f.write("\n".join(dialogue_lines))
        
    logger.info(f"Subtitles written to {ass_path} — {len(dialogue_lines)} events, {len(all_emphasis_words)} emphasis words")
    return ass_path


def process_single_scene_media(scene, assembly_config=None):
    """
    Crop, loop, and scale scene visual asset to 9:16 portrait matching audio duration.
    Now accepts assembly_config from the PE for Ken Burns zoom rate.
    """
    idx = scene["index"]
    dur = scene["audio_duration"]
    asset = scene["visual_asset"]
    out_video_path = os.path.join(OUTPUT_DIR, f"scene_{idx}_processed.mp4")
    
    # Get PE-configured zoom rate
    zoom_rate = 0.0005  # default
    fps = 25
    if assembly_config:
        zoom_rate = assembly_config.get("ken_burns_zoom_rate", 0.0005)
        fps = assembly_config.get("output_fps", 25)
    
    logger.info(f"Processing media for Scene {idx} (duration: {dur}s, asset type: {asset['type']}, zoom: {zoom_rate})")
    
    if asset["type"] == "video":
        raw_path = asset["path"]
        start_time = scene.get("start_time", 0.0)
        
        logger.info(f"Full stretch background video loop for Scene {idx} (timeline start: {start_time:.2f}s, duration: {dur:.2f}s)")
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-ss", f"{start_time:.3f}",
            "-i", raw_path,
            "-t", f"{dur:.3f}",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-an",
            out_video_path
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
    elif asset["type"] == "image":
        raw_path = asset["path"]
        # Step 1: Crop the image to portrait
        cropped_img_path = os.path.join(OUTPUT_DIR, f"scene_{idx}_cropped.jpg")
        crop_cmd = [
            "ffmpeg", "-y",
            "-i", raw_path,
            "-vf", "crop=ih*9/16:ih",
            cropped_img_path
        ]
        subprocess.run(crop_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
        # Step 2: Ken Burns zoom with PE-configured zoom rate
        num_frames = int(fps * dur)
        logger.info(f"Ken Burns: zoom_rate={zoom_rate}, frames={num_frames}, fps={fps}")
        
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", cropped_img_path,
            "-t", f"{dur:.3f}",
            "-vf", (
                f"zoompan=z='zoom+{zoom_rate}':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={num_frames}:s=1080x1920"
            ),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-an",
            out_video_path
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
    else:  # placeholder
        logger.info("Using relevant trading background fallback.")
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", "assets/fallback.png",
            "-t", f"{dur:.3f}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-an",
            out_video_path
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
    current_timeline_pos = 0.0
    for scene in processed_scenes:
        audio_dur = get_audio_duration(scene["audio_path"])
        scene["audio_duration"] = audio_dur
        scene["start_time"] = current_timeline_pos
        current_timeline_pos += audio_dur
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
    
    # 5. Merge stitched video and stitched audio
    logger.info("Merging audio and video tracks...")
    video_with_audio = os.path.join(OUTPUT_DIR, "video_with_audio.mp4")
    subprocess.run([
        "ffmpeg", "-y", "-i", combined_video, "-i", combined_audio,
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", audio_codec,
        "-shortest", video_with_audio
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    
    # 6. Generate subtitle ASS file with PE style config
    ass_path = generate_ass_file(processed_scenes, total_audio_dur, subtitle_style=subtitle_style)
    
    # 7. Build complex filter for mascot overlay, logo, subtitles, and loudness
    final_output = os.path.join(OUTPUT_DIR, "distribution_ready.mp4")
    logger.info("Applying Mascot Overlays, Logo, Subtitles, and Audio Loudness...")
    
    inputs = ["-i", video_with_audio]
    mascot_paths = {
        "arrow_up": "assets/mascot/arrow_up.png",
        "arrow_down": "assets/mascot/arrow_down.png"
    }
    
    input_count = 1  # 0 is video_with_audio
    
    # Add logo as input 1
    inputs.extend(["-i", "logo_transparent.png"])
    input_count += 1
    
    # Add BGM as input 2
    bgm_input_idx = -1
    if os.path.exists("assets/audio/bgm.mp3"):
        inputs.extend(["-stream_loop", "-1", "-i", "assets/audio/bgm.mp3"])
        bgm_input_idx = input_count
        input_count += 1
    
    filter_chains = []
    
    # Scale logo and place at top right with PE-configured size/padding
    filter_chains.append(f"[1:v]scale={logo_scale}:-1[logo];[0:v][logo]overlay=W-w-{logo_padding}:{logo_padding}[v1]")
    
    current_time = 0.0
    last_v = "v1"
    input_idx = 2
    
    for i, scene in enumerate(processed_scenes):
        dur = scene["audio_duration"]
        start_t = current_time
        end_t = current_time + dur
        
        # Use PE mascot timeline if available, otherwise fallback to scene arrow_state
        if mascot_timeline:
            segments = mascot_timeline.get("segments", [])
            state = "arrow_up"
            pos_x = LAYOUT_CONFIG["mascot_pos_x"]
            pos_y = LAYOUT_CONFIG["mascot_pos_y"]
            for seg in segments:
                if seg.get("scene_number") == i + 1:
                    state = seg.get("arrow_state", "arrow_up")
                    pos_x = seg.get("position_x", LAYOUT_CONFIG["mascot_pos_x"])
                    pos_y = seg.get("position_y", LAYOUT_CONFIG["mascot_pos_y"])
                    break
        else:
            state = scene.get("arrow_state", "arrow_up")
            pos_x = LAYOUT_CONFIG["mascot_pos_x"]
            pos_y = LAYOUT_CONFIG["mascot_pos_y"]
        
        mascot_file = mascot_paths.get(state, mascot_paths["arrow_up"])
        if not os.path.exists(mascot_file):
            logger.warning(f"Mascot file not found: {mascot_file}. Using logo as fallback.")
            mascot_file = "logo_transparent.png"
            
        inputs.extend(["-i", mascot_file])
        input_idx = input_count
        input_count += 1
        
        next_v = f"v{input_idx}"
        # No bobbing animation, just straight cut per framework document
        filter_chains.append(
            f"[{input_idx}:v]format=rgba,scale=-1:400[m_{input_idx}];"
            f"[{last_v}][m_{input_idx}]overlay={pos_x}:{pos_y}:"
            f"enable='between(t,{start_t},{end_t})'[{next_v}]"
        )
        
        last_v = next_v
        input_idx += 1
        current_time += dur
        
    # Burn subtitles on top of everything
    # On Windows, FFmpeg filter strings break if there's an unescaped colon (like D:\)
    ass_path_escaped = ass_path.replace('\\', '/').replace(':', '\\:')
    filter_chains.append(f"[{last_v}]subtitles='{ass_path_escaped}'[vout]")
    
    # Audio Loudness Normalization with PE-configured parameters and BGM mix
    a_in = "0:a"
    if bgm_input_idx != -1:
        filter_chains.append(f"[0:a][{bgm_input_idx}:a]amix=inputs=2:duration=first:dropout_transition=2:weights=1.0 0.15[a_mixed]")
        a_in = "a_mixed"
        
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
