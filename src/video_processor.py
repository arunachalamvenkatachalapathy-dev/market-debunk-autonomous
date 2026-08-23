import os
import json
import logging
import subprocess
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
        alignment = 5  # Middle center alignment
    else:
        font_name = subtitle_style.get("font_name", "Arial Black")
        font_size = 112
        primary_color = subtitle_style.get("primary_color", "&H00FFFFFF")
        emphasis_color = subtitle_style.get("emphasis_color", "&H0000FFA3") # Electric Neon Green
        outline_color = subtitle_style.get("outline_color", "&H00000000")
        outline_width = 10
        shadow_depth = 0
        margin_v = subtitle_style.get("margin_v", LAYOUT_CONFIG["subtitle_margin_v"])
        alignment = 5
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
    
    # Collect emphasis words from PE voice config
    all_emphasis_words = set()
    for scene in processed_scenes:
        for word in scene.get("emphasis_words", []):
            all_emphasis_words.add(word.upper())
    
    # Flatten all word timings with absolute offsets
    flat_timings = []
    current_time_offset = 0.0
    
    for scene in processed_scenes:
        dur = scene.get("audio_duration")
        if not dur:
            try:
                cmd = [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", scene["audio_path"]
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
                dur = float(res.stdout.strip())
            except Exception:
                dur = 5.0
        scene["audio_duration"] = dur
        for item in scene.get("word_timings", []):
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
            if end - start > 1.0:
                end = start + 0.75
        else:
            end = start + 0.9
            
        if end > total_duration:
            end = total_duration
            
        start_str = format_ass_time(start)
        end_str = format_ass_time(end)
        word_text = item["word"]
        
        # Use Emphasis style for PE-flagged words
        style = "Emphasis" if item["is_emphasis"] else "Default"
        
        # Dynamic micro-bounce pop tag anchored at safe zone (540, 1400)
        pos_tag = r"{\an5\pos(540,1400)\fscx85\fscy85\t(0,70,\fscx108\fscy108)\t(70,140,\fscx100\fscy100)}"
        
        dialogue_lines.append(
            f"Dialogue: 0,{start_str},{end_str},{style},,0,0,0,,{pos_tag}{word_text}"
        )
        
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(ass_header)
        f.write("\n".join(dialogue_lines))
        
    logger.info(f"Subtitles written to {ass_path} — {len(dialogue_lines)} events, {len(all_emphasis_words)} emphasis words")
    return ass_path


def render_single_host_frame(scene, scene_index, skip_avatar=False):
    """
    Renders a high-definition 1080x1920 Single Host frame.
    Bottom/Center: The Host
    Top: Dynamic Popups (text or generated assets)
    """
    w, h = 1080, 1920
    
    # Grab the avatar to extract its background color
    host_file = os.path.join(os.getcwd(), "assets", "avatars", "host_closed.png")
    if not os.path.exists(host_file):
        host_file = os.path.join(os.getcwd(), "assets", "avatars", "host_closed.jpg")
        
    bg_color = (240, 242, 245) # Default light studio wall
    h_img = None
    if os.path.exists(host_file):
        h_img = Image.open(host_file).convert("RGBA")
        # Extract the background color from the top-left pixel of the avatar
        bg_color = h_img.getpixel((10, 10))[:3]
        
    frame = Image.new("RGB", (w, h), bg_color)
    draw = ImageDraw.Draw(frame)
    
    # Visual Asset (if provided in scene) -> SPLIT SCREEN B-ROLL (Top Half)
    asset = scene.get("visual_asset")
    if asset and asset.get("path") and os.path.exists(asset.get("path")):
        try:
            asset_path = asset.get("path")
            if asset_path.lower().endswith(('.mp4', '.mov', '.webm', '.avi')):
                import tempfile
                import subprocess
                temp_frame = os.path.join(tempfile.gettempdir(), f"frame_extract_{scene_index}.jpg")
                subprocess.run([
                    "ffmpeg", "-y", "-i", asset_path, "-vframes", "1", "-q:v", "2", temp_frame
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
                img = Image.open(temp_frame).convert("RGBA")
            else:
                img = Image.open(asset_path).convert("RGBA")
            # The top half is Y=0 to Y=840, width=1080.
            target_bw, target_bh = 1080, 840
            # Use ImageOps.fit to perfectly crop/resize the asset to fill the top half
            from PIL import ImageOps
            img_fitted = ImageOps.fit(img, (target_bw, target_bh), method=Image.Resampling.LANCZOS)
            
            # Paste at the top
            frame.paste(img_fitted, (0, 0))
            
            # Draw a sleek dividing line
            draw.line([(0, target_bh), (w, target_bh)], fill=(255, 255, 255), width=8)
            draw.line([(0, target_bh+4), (w, target_bh+4)], fill=(200, 200, 200), width=2)
        except Exception as e:
            logger.warning(f"Could not load asset image {asset.get('path')}: {e}")
            
    # Popup Text (Optional overlay on B-Roll)
    popup_text = scene.get("popup_text", "")
    if popup_text and popup_text.strip():
        # Load a nice bold font for stats
        try:
            stat_font = ImageFont.truetype(os.path.join("assets", "fonts", "Montserrat-Bold.ttf"), 65)
        except:
            stat_font = ImageFont.load_default()
            
        bbox = stat_font.getbbox(popup_text.upper())
        cw = bbox[2] - bbox[0]
        ch = bbox[3] - bbox[1]
        
        callout_pad = 40
        card_w = cw + callout_pad * 2
        card_h = ch + 40
        
        # Draw modern, clean popup box (iOS style rounded rectangle) centered in the top half
        box_y = (840 - card_h) // 2
        draw.rounded_rectangle(
            [(w - card_w) // 2, box_y, (w + card_w) // 2, box_y + card_h],
            radius=30, fill=(255, 255, 255), outline=(200, 200, 200), width=2
        )
        # Add subtle shadow (simulated)
        draw.rounded_rectangle(
            [(w - card_w) // 2 + 5, box_y + 5, (w + card_w) // 2 + 5, box_y + 5 + card_h],
            radius=30, fill=None, outline=(220, 220, 220), width=2
        )
        
        draw.text(((w - cw) // 2, box_y + 15), popup_text.upper(), fill=(30, 30, 30), font=stat_font)

    # Draw host slot (if skip_avatar is False)
    host_file = os.path.join(os.getcwd(), "assets", "avatars", "host_closed.png")
    if not os.path.exists(host_file):
        host_file = os.path.join(os.getcwd(), "assets", "avatars", "host_closed.jpg")

    # Draw host slot seamlessly
    if not skip_avatar and h_img:
        # Scale width to fill the screen (or close to it)
        target_w = 1080
        scale_ratio = target_w / float(h_img.width)
        target_h = int(h_img.height * scale_ratio)
        
        h_img = h_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        # Paste at the very bottom of the screen
        y_pos = h - target_h
        frame.paste(h_img, (0, y_pos), h_img)

    out_frame_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}_host_frame.png")
    frame.save(out_frame_path, format="PNG")
    return out_frame_path


_LIPSYNC_OVERLAY = {
    # Since we scaled the avatar to width=1080 and placed it at bottom
    # we need the same coordinates for Wav2Lip scaling
    "host": {"x": 0, "y": -1, "w": 1080, "h": -1}, # -1 signifies we will compute it dynamically
}


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

    # ── Step 1: Render background frame ───────────
    studio_frame_path = render_single_host_frame(scene, idx, skip_avatar=True)

    # ── Step 2: Generate talking-face lip-sync video ─────────────────────────
    avatars_dir = os.path.join(os.getcwd(), "assets", "avatars")
    
    speaker_src_img = os.path.join(avatars_dir, "host_closed.jpg")
    if not os.path.exists(speaker_src_img):
        speaker_src_img = os.path.join(avatars_dir, "host_closed.png")
        
    speaker_open_img = os.path.join(avatars_dir, "host_open.jpg")
    if not os.path.exists(speaker_open_img):
        speaker_open_img = os.path.join(avatars_dir, "host_open.png")

    hf_token = os.environ.get("HF_API_KEY", "")
    lipsync_video_path = os.path.join(OUTPUT_DIR, f"scene_{idx}_lipsync.mp4")

    # Legacy lip-sync generation was here. Now bypassed by FaceClone API which generates the entire custom_avatar.mp4 directly.
    lipsync_video_path = None

    # ── Step 3: Composite background + talking-face → final scene MP4 ────────
    overlay = _LIPSYNC_OVERLAY.get("host")
    ov_x, ov_y, ov_w, ov_h = overlay["x"], overlay["y"], overlay["w"], overlay["h"]

    num_frames = max(10, int(fps * dur))

    if lipsync_video_path and os.path.exists(lipsync_video_path):
        # We need the aspect ratio of the lipsync video to compute height
        h_img = Image.open(speaker_src_img)
        target_w = 1080
        scale_ratio = target_w / float(h_img.width)
        target_h = int(h_img.height * scale_ratio)
        ov_x = 0
        ov_y = 1920 - target_h
        ov_w = target_w
        ov_h = target_h
        
        # Scale the lipsync clip to avatar slot size, then overlay onto background loop
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", studio_frame_path,           # input 0: bg image (looped)
            "-stream_loop", "-1", "-i", lipsync_video_path,   # input 1: lipsync video (looped)
            "-filter_complex",
            (
                # Scale lipsync face to match the avatar slot dimensions
                f"[1:v]scale={ov_w}:{ov_h}[face];"
                # Loop background for the exact audio duration
                f"[0:v]trim=duration={dur}:start=0[bg];"
                # Overlay the talking face onto the correct studio slot
                f"[bg][face]overlay={ov_x}:{ov_y}[vout]"
            ),
            "-map", "[vout]",
            "-t", f"{dur:.3f}",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            "-an",
            out_video_path,
        ]
    else:
        # Full static fallback — Ken Burns zoom on the full studio frame
        logger.warning(f"⚠️  No lipsync video for scene {idx} — using static Ken Burns fallback.")
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", studio_frame_path,
            "-t", f"{dur:.3f}",
            "-vf", (
                f"zoompan=z='min(max(zoom,pzoom)+0.0003,1.03)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={num_frames}:s=1080x1920,fps={fps}"
            ),
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
    
    # Check for Custom Avatar
    custom_avatar = os.path.join(os.getcwd(), "custom_avatar.mp4")
    using_custom_avatar = os.path.exists(custom_avatar)
    
    video_clips = []
    total_audio_dur = 0.0
    current_timeline_pos = 0.0
    for scene in processed_scenes:
        audio_dur = get_audio_duration(scene["audio_path"])
        scene["audio_duration"] = audio_dur
        scene["start_time"] = current_timeline_pos
        current_timeline_pos += audio_dur
        total_audio_dur += audio_dur
        
        if not using_custom_avatar:
            out_v = process_single_scene_media(scene, assembly_config=assembly_config)
            video_clips.append(out_v)
            
    logger.info(f"Total pipeline duration: {total_audio_dur}s")
    
    if using_custom_avatar:
        logger.info("🎭 Custom Avatar detected! Bypassing scene stitching and applying B-Roll overlays directly.")
        combined_video = os.path.join(OUTPUT_DIR, "combined_video.mp4")
        
        # Build complex filter to overlay B-rolls on custom_avatar
        inputs = ["-i", custom_avatar]
        filter_chains = []
        for i, scene in enumerate(processed_scenes):
            b_roll = scene["visual_asset"]["path"]
            start_t = scene["start_time"]
            end_t = start_t + scene["audio_duration"]
            inputs.extend(["-stream_loop", "-1", "-i", b_roll])
            
            # Scale and crop B-roll
            filter_chains.append(f"[{i+1}:v]scale=1080:840:force_original_aspect_ratio=increase,crop=1080:840,setpts=PTS-STARTPTS[b{i}]")
            
        # Chain the overlays
        last_out = "0:v"
        for i, scene in enumerate(processed_scenes):
            start_t = scene["start_time"]
            end_t = start_t + scene["audio_duration"]
            out_node = f"v{i}"
            
            # 1. Overlay the B-Roll
            overlay_expr = f"[{last_out}][b{i}]overlay=0:0:enable='between(t,{start_t},{end_t})'"
            
            # 2. Add Dividing Line (white and gray)
            overlay_expr += f",drawbox=x=0:y=840:w=1080:h=8:color=white:t=fill:enable='between(t,{start_t},{end_t})'"
            overlay_expr += f",drawbox=x=0:y=844:w=1080:h=2:color=gray:t=fill:enable='between(t,{start_t},{end_t})'"
            
            # 3. Add Popup Text (if present)
            popup = scene.get("popup_text", "").strip().upper()
            if popup:
                # Basic text rendering in the center of the top half
                font_path = "assets/fonts/Montserrat-Bold.ttf"
                if not os.path.exists(font_path):
                    font_path = "/Windows/Fonts/arial.ttf" # Fallback
                # Escape text for ffmpeg
                popup_escaped = popup.replace("'", "\\'").replace(":", "\\:")
                # Draw rounded rectangle behind text (using drawbox with transparency as a simple alternative)
                # Then draw text
                overlay_expr += f",drawbox=x=(1080-tw-80)/2:y=(840-th-40)/2:w=tw+80:h=th+40:color=white@0.9:t=fill:enable='between(t,{start_t},{end_t})'"
                overlay_expr += f",drawtext=fontfile='{font_path}':text='{popup_escaped}':fontsize=65:fontcolor=black:x=(1080-tw)/2:y=(840-th)/2:enable='between(t,{start_t},{end_t})'"
            
            filter_chains.append(f"{overlay_expr}[{out_node}]")
            last_out = out_node
            
        complex_filter = ";".join(filter_chains)
        
        subprocess.run([
            "ffmpeg", "-y", *inputs,
            "-filter_complex", complex_filter,
            "-map", f"[{last_out}]", "-map", "0:a",
            "-c:v", output_codec, "-c:a", "copy", "-t", f"{total_audio_dur:.3f}",
            combined_video
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        
        combined_audio = combined_video # Audio is already in the combined video
        video_with_audio = combined_video
        
    else:
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
    
    if not using_custom_avatar:
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
                "ffmpeg", "-y", "-i", combined_video, "-i", combined_audio,
                "-filter_complex", f"[0:v]setpts={speed_factor}*PTS[v_synced]",
                "-map", "[v_synced]", "-map", "1:a:0",
                "-c:v", output_codec, "-c:a", audio_codec,
                "-t", f"{a_dur:.3f}",
                video_with_audio
            ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        else:
            subprocess.run([
                "ffmpeg", "-y", "-i", combined_video, "-i", combined_audio,
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
    
    # Add BGM as input 2
    bgm_input_idx = -1
    if os.path.exists("assets/audio/bgm.mp3"):
        inputs.extend(["-stream_loop", "-1", "-i", "assets/audio/bgm.mp3"])
        bgm_input_idx = input_count
        input_count += 1
    
    filter_chains = []
    
    # Scale logo and place at top right with PE-configured size/padding
    filter_chains.append(f"[1:v]scale={logo_scale}:-1[logo];[0:v][logo]overlay=W-w-{logo_padding}:{logo_padding}[v1]")
    
    # Burn subtitles on top
    # On Windows, FFmpeg filter strings break if there's an unescaped colon (like D:\)
    ass_path_escaped = ass_path.replace('\\', '/').replace(':', '\\:')
    filter_chains.append(f"[v1]subtitles='{ass_path_escaped}'[vout]")
    
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
