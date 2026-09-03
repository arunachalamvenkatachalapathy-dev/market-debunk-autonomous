"""
src/rendering/assembler.py

Phase 5 — FFmpeg Video Assembly

Takes per-scene audio + visual assets and assembles the final
distribution-ready YouTube Short (1080×1920, 30fps, H.264/AAC).

Pipeline:
  1. For each scene:
     a. If asset is a VIDEO: crop/scale to 1080×1920, loop to match audio duration
     b. If asset is an IMAGE: convert to video (ken-burns pan effect), match audio duration
     c. Merge scene video + scene audio → scene_clip.mp4
  2. Concatenate all scene clips → raw_video.mp4
  3. Burn .ass subtitles into raw_video → subtitled_video.mp4
  4. Mix BGM audibly under voice with sidechain ducking → final.mp4
  5. Rename to distribution_ready.mp4
"""
from __future__ import annotations

import subprocess
import sys
import shutil
import time
from pathlib import Path
from typing import Optional

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="video_assembly")

# ──────────────────────────────────────────────────────────────────────────────
#  FFmpeg Helper
# ──────────────────────────────────────────────────────────────────────────────

def _ffmpeg(*args: str, description: str = "") -> None:
    """Run an ffmpeg command; raise on non-zero exit."""
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *args]
    log.debug("ffmpeg: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log.error("ffmpeg FAILED (%s):\n  stderr: %s", description, result.stderr[:500])
        raise RuntimeError(f"ffmpeg error in '{description}': {result.stderr[-300:]}")
    if description:
        log.info("✓ %s", description)


# ──────────────────────────────────────────────────────────────────────────────
#  Step 1 — Per-Scene Clip Builder
# ──────────────────────────────────────────────────────────────────────────────

def _build_scene_from_video(
    video_path: Path,
    duration: float,
    output_path: Path,
) -> None:
    """
    Crop and loop a stock video to match duration, scale to 1080×1920.
    Builds a pure video clip without audio so voice track remains continuous.
    """
    w, h = settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT
    fps = settings.VIDEO_FPS

    # Crop rather than pad: empty bars are a release-quality failure for Shorts.
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase,"
        f"crop={w}:{h},"
        f"setsar=1,"
        f"zoompan=z='min(zoom+0.0005,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(duration*fps)}:s={w}x{h}:fps={fps}"
    )

    _ffmpeg(
        "-stream_loop", "-1",          # loop video if shorter than duration
        "-i", str(video_path),
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-an",
        str(output_path),
        description=f"build scene clip from video: {output_path.name}"
    )


def _build_scene_from_image(
    image_path: Path,
    duration: float,
    output_path: Path,
    scene_id: int = 1,
) -> None:
    """
    Scale image to fill (no black bars), crop to 1080x1920, and apply varied ken-burns zoom.
    Builds a pure video clip without audio so voice track remains continuous.
    """
    w, h = settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT
    fps = settings.VIDEO_FPS
    n_frames = int(duration * fps)

    # Vary the zoom direction based on scene_id to prevent repetitive motion
    pan_type = scene_id % 3
    if pan_type == 0:
        # Straight slow zoom in
        zp_motion = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif pan_type == 1:
        # Zoom in while panning slightly right
        zp_motion = "x='iw/2-(iw/zoom/2)+2':y='ih/2-(ih/zoom/2)'"
    else:
        # Zoom in while panning slightly left
        zp_motion = "x='iw/2-(iw/zoom/2)-2':y='ih/2-(ih/zoom/2)'"

    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=increase," # Fill frame, no black bars
        f"crop={w}:{h},"
        f"setsar=1,"
        f"zoompan=z='min(zoom+0.0008,1.05)':{zp_motion}:d={n_frames}:s={w}x{h}:fps={fps}"
    )

    _ffmpeg(
        "-loop", "1",
        "-framerate", str(fps),
        "-i", str(image_path),
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
        description=f"build scene clip from image: {output_path.name}"
    )


def build_scene_clips(
    voice_results: list[dict],
    visual_results: list[dict],
    clips_dir: Path,
) -> list[Path]:
    """
    Build a video-only clip for each scene (video or image → looped/animated video).
    Returns list of clip paths in scene order.
    """
    clips_dir.mkdir(parents=True, exist_ok=True)
    clip_paths: list[Path] = []

    # Index by scene_id for easy lookup
    voice_map = {r["scene_id"]: r for r in voice_results}
    visual_map = {r["scene_id"]: r for r in visual_results}

    for scene_id in sorted(voice_map.keys()):
        voice = voice_map[scene_id]
        visual = visual_map[scene_id]

        duration = voice["duration"]
        asset_path = Path(visual["asset_path"])
        asset_type = visual["asset_type"]

        clip_path = clips_dir / f"scene_{scene_id}_clip.mp4"

        log.info(
            "Building scene %d clip | type: %s | duration: %.1fs",
            scene_id, asset_type, duration
        )

        if asset_type == "video":
            _build_scene_from_video(asset_path, duration, clip_path)
        else:
            _build_scene_from_image(asset_path, duration, clip_path, scene_id=scene_id)

        clip_paths.append(clip_path)

    return clip_paths


# ──────────────────────────────────────────────────────────────────────────────
#  Step 2 — Concatenation & Master Voice Track
# ──────────────────────────────────────────────────────────────────────────────

def concatenate_voice_audio(voice_results: list[dict], output_path: Path) -> Path:
    """
    Concatenate all scene voice tracks into a single continuous 48kHz stereo WAV track.
    This prevents audio frame mismatches, clipping, or pops between scene cuts.
    """
    concat_list = output_path.parent / "voice_concat_list.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for r in voice_results:
            p = Path(r["mp3_path"]).resolve()
            f.write(f"file '{p}'\n")

    _ffmpeg(
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-ar", "48000",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(output_path),
        description="concatenate voice audio tracks"
    )
    return output_path


def mux_video_and_audio(video_path: Path, audio_path: Path, output_path: Path) -> Path:
    """Mux concatenated video with continuous master voice audio at standard 48kHz AAC."""
    _ffmpeg(
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-shortest",
        str(output_path),
        description="mux continuous video and master voice track"
    )
    return output_path


def concatenate_clips(clip_paths: list[Path], output_path: Path) -> Path:
    """Concatenate all scene clips into a single continuous video."""
    # Write FFmpeg concat list
    concat_list = output_path.parent / "concat_list.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for clip in clip_paths:
            f.write(f"file '{clip.resolve()}'\n")

    _ffmpeg(
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(output_path),
        description="concatenate all scene clips"
    )
    return output_path


# ──────────────────────────────────────────────────────────────────────────────
#  Step 3 — Subtitle Burning
# ──────────────────────────────────────────────────────────────────────────────

def burn_subtitles(video_path: Path, ass_path: Path, output_path: Path) -> Path:
    """
    Hard-burn .ass subtitles into video frames.
    Must re-encode video for subtitle burn-in.
    """
    # escape Windows path separators for FFmpeg filter
    ass_str = str(ass_path.resolve()).replace("\\", "/").replace(":", "\\:")

    _ffmpeg(
        "-i", str(video_path),
        "-vf", f"ass='{ass_str}'",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "copy",
        str(output_path),
        description="burn subtitles into video"
    )
    return output_path


def overlay_brand_mark(video_path: Path, output_path: Path) -> Path:
    """Overlay the channel protection mark at the top-right corner."""
    logo_path = settings.BRAND_MARK_PATH
    if not logo_path.is_file():
        log.warning("Brand protection mark not found at %s — skipping overlay", logo_path)
        shutil.copy2(video_path, output_path)
        return output_path

    pad = settings.BRAND_MARK_PADDING
    vf = f"[1:v]scale={settings.BRAND_MARK_WIDTH}:-1[logo];[0:v][logo]overlay=W-w-{pad}:{pad}"
    _ffmpeg(
        "-i", str(video_path),
        "-i", str(logo_path),
        "-filter_complex", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "20",
        "-c:a", "copy",
        str(output_path),
        description="overlay brand protection mark"
    )
    return output_path


# ──────────────────────────────────────────────────────────────────────────────
#  Step 4 — BGM Mixing
# ──────────────────────────────────────────────────────────────────────────────

def mix_bgm(
    video_path: Path,
    bgm_path: Optional[Path],
    output_path: Path,
    bgm_volume_db: Optional[float] = None,
    use_ducking: bool = True,
) -> Path:
    """
    Layer BGM under the voiceover and normalise the mix.
    BGM is looped to match video duration and mixed at bgm_volume_db.
    The final mix is normalised to -14 LUFS.

    If bgm_path is None or doesn't exist, only applies loudness normalisation.
    """
    if bgm_volume_db is None:
        bgm_volume_db = settings.BGM_VOLUME_DB

    if not bgm_path or not bgm_path.exists():
        message = f"BGM track not found at {bgm_path}"
        if settings.BGM_MIX_REQUIRED:
            raise FileNotFoundError(message)
        log.warning("%s — applying voice-only loudness normalisation", message)
        # Just normalise loudness
        _ffmpeg(
            "-i", str(video_path),
            "-af", "loudnorm=I=-14:TP=-1:LRA=11",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            str(output_path),
            description="loudness normalisation (no BGM)"
        )
        return output_path

    # Mix: voice (0dB) + audible BGM. The primary path ducks BGM under speech;
    # a simpler fallback is used by the caller if a platform FFmpeg build balks.
    vol_factor = 10 ** (bgm_volume_db / 20)
    if use_ducking:
        audio_filter = (
            "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,asplit=2[voice_mix][voice_key];"
            f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume={vol_factor:.4f}[bgm];"
            "[bgm][voice_key]sidechaincompress=threshold=0.08:ratio=3:attack=50:release=450[ducked];"
            "[voice_mix][ducked]amix=inputs=2:duration=first:dropout_transition=0,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            "loudnorm=I=-14:TP=-1:LRA=11[out]"
        )
        description = "BGM ducking mix + loudness normalisation"
    else:
        audio_filter = (
            "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[voice];"
            f"[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,volume={vol_factor:.4f}[bgm];"
            "[voice][bgm]amix=inputs=2:duration=first:dropout_transition=0,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            "loudnorm=I=-14:TP=-1:LRA=11[out]"
        )
        description = "BGM simple mix + loudness normalisation"

    _ffmpeg(
        "-i", str(video_path),
        "-stream_loop", "-1",
        "-i", str(bgm_path),
        "-filter_complex", audio_filter,
        "-map", "0:v",
        "-map", "[out]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        str(output_path),
        description=description
    )
    return output_path


def mix_bgm_with_retries(video_path: Path, bgm_path: Optional[Path], output_path: Path) -> Path:
    """
    Retry the preferred ducked BGM mix, then a simpler BGM mix. BGM remains the
    target output; voice-only finalization is reserved for the outer emergency
    fallback so the run still produces an inspectable artifact.
    """
    retry_count = max(settings.BGM_MIX_RETRIES, 1)
    last_exc: Optional[Exception] = None
    for attempt in range(1, retry_count + 1):
        try:
            log.info("BGM mix attempt %d/%d with ducking", attempt, retry_count)
            return mix_bgm(video_path, bgm_path, output_path, use_ducking=True)
        except Exception as exc:
            last_exc = exc
            log.warning("BGM ducking mix attempt %d failed: %s", attempt, exc)
            time.sleep(min(5 * attempt, 20))

    try:
        log.warning("Retrying with simpler BGM mix after ducking failures")
        return mix_bgm(video_path, bgm_path, output_path, use_ducking=False)
    except Exception as exc:
        last_exc = exc

    raise RuntimeError(f"BGM mix failed after retries: {last_exc}")


def finalize_without_bgm(video_path: Path, output_path: Path) -> Path:
    """
    Last-resort finalization. Keeps the completed subtitled voice video rather
    than failing the whole run because the optional BGM stage had a problem.
    """
    try:
        _ffmpeg(
            "-i", str(video_path),
            "-af", "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,loudnorm=I=-14:TP=-1:LRA=11",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "48000",
            str(output_path),
            description="fallback loudness normalisation without BGM"
        )
    except Exception as exc:
        log.warning("Fallback loudness normalisation failed; copying subtitled video: %s", exc)
        shutil.copy2(video_path, output_path)
    return output_path


# ──────────────────────────────────────────────────────────────────────────────
#  Master Assembly Function
# ──────────────────────────────────────────────────────────────────────────────

def assemble_video(
    voice_results: list[dict],
    visual_results: list[dict],
    ass_path: Path,
    run_dir: Path,
    bgm_path: Optional[Path] = None,
) -> Path:
    """
    Full video assembly pipeline.

    Returns path to distribution_ready.mp4
    """
    clips_dir = run_dir / "clips"
    raw_video_only = run_dir / "raw_video_only.mp4"
    master_voice_wav = run_dir / "master_voice.wav"
    raw_video = run_dir / "raw_video.mp4"
    subtitled_video = run_dir / "subtitled_video.mp4"
    branded_video = run_dir / "branded_video.mp4"
    final_video = run_dir / "distribution_ready.mp4"

    # Step 1: Build per-scene clips (video-only)
    log.info("Step 1/5: Building %d scene clips …", len(voice_results))
    clip_paths = build_scene_clips(voice_results, visual_results, clips_dir)

    # Step 2: Concatenate video clips
    log.info("Step 2/5: Concatenating video clips …")
    concatenate_clips(clip_paths, raw_video_only)

    # Step 2b: Create continuous master voice track and mux with video
    log.info("Step 2b/5: Creating unified master voice track …")
    concatenate_voice_audio(voice_results, master_voice_wav)
    mux_video_and_audio(raw_video_only, master_voice_wav, raw_video)

    # Step 3: Burn subtitles
    log.info("Step 3/5: Burning subtitles …")
    burn_subtitles(raw_video, ass_path, subtitled_video)

    # Step 4: Add brand mark
    log.info("Step 4/5: Adding brand protection mark …")
    overlay_brand_mark(subtitled_video, branded_video)

    # Step 5: Mix BGM
    import random
    if not bgm_path or not Path(bgm_path).is_file():
        bgm_dir = settings.ASSETS_DIR / "bgm"
        available_bgm = [
            track for track in bgm_dir.glob("*.mp3")
            if track.stat().st_size >= settings.BGM_MIN_BYTES
        ]
        bgm = random.choice(available_bgm) if available_bgm else settings.BGM_PATH
    else:
        bgm = bgm_path
    log.info(
        "Step 5/5: Mixing BGM (%s at %.1f dB) and normalising loudness …",
        bgm.name,
        settings.BGM_VOLUME_DB,
    )
    try:
        mix_bgm_with_retries(branded_video, bgm, final_video)
    except Exception as exc:
        log.error("BGM mix failed after retries; finalizing without BGM as emergency artifact: %s", exc)
        finalize_without_bgm(branded_video, final_video)

    # Duration safety guard: Ensure final duration does not exceed settings.MAX_VIDEO_DURATION
    try:
        from src.agents.quality_gate import _probe_video
        probe = _probe_video(final_video)
        final_dur = float(probe.get("format", {}).get("duration", 0.0))
        if final_dur > settings.MAX_VIDEO_DURATION:
            clamp_dur = settings.MAX_VIDEO_DURATION - 0.2
            log.warning(
                "Final video duration (%.2fs) exceeds max (%.1fs); clamping cleanly to %.2fs",
                final_dur,
                settings.MAX_VIDEO_DURATION,
                clamp_dur,
            )
            clamped_path = run_dir / "distribution_ready_clamped.mp4"
            fade_start = max(clamp_dur - 0.3, 0)
            _ffmpeg(
                "-i", str(final_video),
                "-t", f"{clamp_dur:.2f}",
                "-c:v", "copy",
                "-af", f"afade=t=out:st={fade_start:.2f}:d=0.3",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                str(clamped_path),
                description="clamping final video duration to Shorts limit"
            )
            shutil.move(str(clamped_path), str(final_video))
    except Exception as clamp_err:
        log.warning("Duration clamp check non-fatal notice: %s", clamp_err)

    log.info(
        "🎬 Assembly complete → %s  (%d KB)",
        final_video.name,
        final_video.stat().st_size // 1024
    )
    return final_video
