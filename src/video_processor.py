import os
import json
import logging
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from src.config import OUTPUT_DIR
from src.lip_sync import run_wav2lip_hf

# ---------------------------------------------------------
# CENTRALIZED LAYOUT CONFIGURATION
# ---------------------------------------------------------
LAYOUT_CONFIG = {
    "subtitle_margin_v": 480,       # Vertical margin from bottom for subtitles
    "mascot_pos_x": "(W-w)/2",      # Mascot X position
    "mascot_pos_y": "300",          # Mascot Y position
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


def render_debate_studio_frame(scene, scene_index, skip_avatar=False):
    """
    Renders a high-definition 1080x1920 Split-Screen Debate Studio frame.
    Top: The Skeptic (Red Team / Myth Speaker)
    Bottom: The Analyst (Green Team / Truth Speaker)
    Center: VS Divider & Dynamic Stat/Data Callout

    Parameters
    ----------
    skip_avatar : bool
        When True, avatars are NOT pasted into the frame.  The active speaker's
        half is left as a plain coloured rectangle so that the Wav2Lip talking-
        face video can be composited on top afterwards via FFmpeg overlay.
        The listening speaker's avatar IS still painted (static, dimmed).
    """
    from scripts.generate_studio_avatars import ensure_studio_avatars
    ensure_studio_avatars()
    
    w, h = 1080, 1920
    frame = Image.new("RGB", (w, h), (13, 17, 23))  # Deep Studio Dark background
    draw = ImageDraw.Draw(frame)
    
    # Determine who is active speaker
    arrow_state = scene.get("arrow_state", "arrow_up")
    speaker = scene.get("speaker")
    if not speaker:
        speaker = "skeptic" if arrow_state == "arrow_down" else "analyst"
    speaker = speaker.lower()
    
    stat_callout = scene.get("stat_callout", "")
    
    # Paths for avatars
    avatars_dir = os.path.join(os.getcwd(), "assets", "avatars")
    skeptic_open   = os.path.join(avatars_dir, "skeptic_open.png")
    skeptic_closed = os.path.join(avatars_dir, "skeptic_closed.png")
    analyst_open   = os.path.join(avatars_dir, "analyst_open.png")
    analyst_closed = os.path.join(avatars_dir, "analyst_closed.png")

    # When skip_avatar=True the *speaking* half gets no avatar painted here;
    # the Wav2Lip clip is overlaid by FFmpeg later.
    # The *listening* half always gets its static dimmed avatar.
    skeptic_file = skeptic_open   if speaker == "skeptic" else skeptic_closed
    analyst_file = analyst_open   if speaker == "analyst" else analyst_closed
    
    # Top Panel Background (The Skeptic Studio)
    top_bg_color = (25, 20, 28) if speaker == "skeptic" else (16, 18, 24)
    draw.rectangle([0, 0, w, 955], fill=top_bg_color)
    
    # Bottom Panel Background (The Analyst Studio)
    bot_bg_color = (15, 28, 22) if speaker == "analyst" else (16, 18, 24)
    draw.rectangle([0, 965, w, h], fill=bot_bg_color)
    
    # ── Skeptic avatar ──────────────────────────────────────────────────────
    # Paint the skeptic only if: (a) not skipping, OR (b) they are not the speaker
    paint_skeptic = (not skip_avatar) or (speaker != "skeptic")
    if paint_skeptic and os.path.exists(skeptic_file):
        sk_img = Image.open(skeptic_file).convert("RGBA")
        if speaker != "skeptic":
            # Dim the listening character slightly
            r, g, b, a = sk_img.split()
            a = a.point(lambda p: int(p * 0.60))
            sk_img = Image.merge("RGBA", (r, g, b, a))
        sk_size = (620, 620)
        sk_img = sk_img.resize(sk_size, Image.Resampling.LANCZOS)
        frame.paste(sk_img, ((w - sk_size[0]) // 2, 140), sk_img)

    # ── Analyst avatar ──────────────────────────────────────────────────────
    # Paint the analyst only if: (a) not skipping, OR (b) they are not the speaker
    paint_analyst = (not skip_avatar) or (speaker != "analyst")
    if paint_analyst and os.path.exists(analyst_file):
        an_img = Image.open(analyst_file).convert("RGBA")
        if speaker != "analyst":
            # Dim the listening character slightly
            r, g, b, a = an_img.split()
            a = a.point(lambda p: int(p * 0.60))
            an_img = Image.merge("RGBA", (r, g, b, a))
        an_size = (620, 620)
        an_img = an_img.resize(an_size, Image.Resampling.LANCZOS)
        frame.paste(an_img, ((w - an_size[0]) // 2, 1020), an_img)

    # Top Banner Badge (Speaker Status)
    sk_badge_color = (255, 46, 84) if speaker == "skeptic" else (80, 85, 100)
    sk_text = "🔴 THE SKEPTIC  [SPEAKING]" if speaker == "skeptic" else "⚪ THE SKEPTIC"
    draw.rounded_rectangle([40, 40, 360, 95], radius=12, fill=(20, 24, 33), outline=sk_badge_color, width=3)
    
    # Bottom Banner Badge (Speaker Status)
    an_badge_color = (0, 255, 163) if speaker == "analyst" else (80, 85, 100)
    an_text = "🟢 THE ANALYST  [SPEAKING]" if speaker == "analyst" else "⚪ THE ANALYST"
    draw.rounded_rectangle([40, 990, 360, 1045], radius=12, fill=(20, 24, 33), outline=an_badge_color, width=3)

    try:
        badge_font = ImageFont.truetype("arial.ttf", 22)
        vs_font = ImageFont.truetype("arial.ttf", 28)
        stat_font = ImageFont.truetype("arial.ttf", 32)
    except Exception:
        badge_font = ImageFont.load_default()
        vs_font = ImageFont.load_default()
        stat_font = ImageFont.load_default()

    draw.text((60, 55), sk_text, fill=(255, 255, 255), font=badge_font)
    draw.text((60, 1005), an_text, fill=(255, 255, 255), font=badge_font)

    # Active Speaker Border Glow around the respective half
    if speaker == "skeptic":
        draw.rectangle([4, 4, w - 4, 955], outline=(255, 46, 84), width=6)
    else:
        draw.rectangle([4, 965, w - 4, h - 4], outline=(0, 255, 163), width=6)

    # Center Divider Bar (Y: 955 to 965)
    divider_color = (255, 215, 0)
    draw.rectangle([0, 955, w, 965], fill=divider_color)
    
    # Center VS Emblem
    vs_box_w, vs_box_h = 120, 50
    draw.rounded_rectangle(
        [(w - vs_box_w) // 2, 960 - vs_box_h // 2, (w + vs_box_w) // 2, 960 + vs_box_h // 2],
        radius=14,
        fill=(15, 18, 25),
        outline=divider_color,
        width=3
    )
    vs_bbox = draw.textbbox((0, 0), "VS", font=vs_font)
    vsw = vs_bbox[2] - vs_bbox[0]
    draw.text(((w - vsw) // 2, 946), "VS", fill=(255, 215, 0), font=vs_font)

    # Optional Center Floating Stat/Data Callout Box
    if stat_callout and stat_callout.strip():
        callout_text = f"📊 {stat_callout.strip().upper()}"
        c_bbox = draw.textbbox((0, 0), callout_text, font=stat_font)
        cw, ch = c_bbox[2] - c_bbox[0], c_bbox[3] - c_bbox[1]
        callout_pad = 25
        card_w = cw + callout_pad * 2
        card_h = ch + 20
        draw.rounded_rectangle(
            [(w - card_w) // 2, 870, (w + card_w) // 2, 870 + card_h],
            radius=16,
            fill=(10, 14, 20),
            outline=(0, 255, 163),
            width=3
        )
        draw.text(((w - cw) // 2, 878), callout_text, fill=(255, 255, 255), font=stat_font)

    out_frame_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}_debate_frame.png")
    frame.save(out_frame_path, format="PNG")
    logger.info(f"🎨 Rendered Debate Studio Frame for Scene {scene_index} (Speaker: {speaker}, skip_avatar={skip_avatar}) -> {os.path.basename(out_frame_path)}")
    return out_frame_path, speaker


# ---------------------------------------------------------------------------
# Layout constants for lip-sync overlay positions
# ---------------------------------------------------------------------------
# The studio frame is 1080×1920.
# Top half (skeptic):   y=140, height=620  → centre y ≈ 140 + 310 = 450
# Bottom half (analyst): y=1020, height=620 → centre y ≈ 1020 + 310 = 1330
_LIPSYNC_OVERLAY = {
    "skeptic": {"x": (1080 - 620) // 2, "y": 140, "w": 620, "h": 620},
    "analyst": {"x": (1080 - 620) // 2, "y": 1020, "w": 620, "h": 620},
}


def process_single_scene_media(scene, assembly_config=None):
    """
    Renders animated media for a single debate-studio scene.

    Pipeline:
      1. Render studio background PNG with the *listening* avatar painted
         statically, but the *speaking* avatar slot left empty.
      2. Generate a talking-face video for the speaker via Hugging Face
         Wav2Lip (or audio-reactive fallback).
      3. FFmpeg: loop background PNG + overlay talking-face video → scene MP4.
    """
    idx = scene["index"]
    dur = scene["audio_duration"]
    audio_path = scene["audio_path"]
    out_video_path = os.path.join(OUTPUT_DIR, f"scene_{idx}_processed.mp4")

    fps = 25
    if assembly_config:
        fps = assembly_config.get("output_fps", 25)

    logger.info(f"🎬 Processing AI Debate Studio Scene {idx} (duration: {dur}s, fps: {fps})")

    # ── Step 1: Render background frame (speaking slot left blank) ───────────
    studio_frame_path, speaker = render_debate_studio_frame(scene, idx, skip_avatar=True)

    # ── Step 2: Generate talking-face lip-sync video ─────────────────────────
    avatars_dir = os.path.join(os.getcwd(), "assets", "avatars")
    speaker_open_img   = os.path.join(avatars_dir, f"{speaker}_open.png")
    speaker_closed_img = os.path.join(avatars_dir, f"{speaker}_closed.png")
    # Use the closed/neutral face as the source for Wav2Lip (cleaner input)
    speaker_src_img    = speaker_closed_img if os.path.exists(speaker_closed_img) else speaker_open_img

    hf_token = os.environ.get("HF_API_KEY", "")
    lipsync_video_path = os.path.join(OUTPUT_DIR, f"scene_{idx}_lipsync.mp4")

    try:
        run_wav2lip_hf(
            image_path=speaker_src_img,
            audio_path=audio_path,
            output_path=lipsync_video_path,
            hf_token=hf_token,
            open_img_path=speaker_open_img,
            closed_img_path=speaker_closed_img,
        )
        logger.info(f"✅ Lip-sync generated for scene {idx}")
    except Exception as exc:
        logger.error(f"❌ Lip-sync failed for scene {idx}: {exc}")
        # Last-resort: paint a static open-mouth frame as a minimal fallback
        lipsync_video_path = None

    # ── Step 3: Composite background + talking-face → final scene MP4 ────────
    overlay = _LIPSYNC_OVERLAY.get(speaker, _LIPSYNC_OVERLAY["analyst"])
    ov_x, ov_y, ov_w, ov_h = overlay["x"], overlay["y"], overlay["w"], overlay["h"]

    num_frames = max(10, int(fps * dur))

    if lipsync_video_path and os.path.exists(lipsync_video_path):
        # Scale the lipsync clip to avatar slot size, then overlay onto background loop
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", studio_frame_path,           # input 0: bg image (looped)
            "-stream_loop", "-1", "-i", lipsync_video_path,   # input 1: lipsync video (looped)
            "-filter_complex",
            (
                # Scale lipsync face to match the avatar slot dimensions
                f"[1:v]scale={ov_w}:{ov_h}[face];"
                # Loop background for the exact audio duration, add subtle zoom
                f"[0:v]zoompan="
                f"z='min(max(zoom,pzoom)+0.0002,1.02)':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={num_frames}:s=1080x1920,fps={fps}[bg];"
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
