"""
src/rendering/assembler.py

Phase 5 — FFmpeg Video Assembly

Takes per-scene audio + visual assets and assembles the final
distribution-ready YouTube Short (1080×1920, 30fps, H.264/AAC).

Pipeline:
  1. For each of 8 scenes:
     a. If asset is a VIDEO: crop/scale to 1080×1920, loop to match audio duration
     b. If asset is an IMAGE: convert to video (ken-burns pan effect), match audio duration
     c. Merge scene video + scene audio → scene_clip.mp4
  2. Concatenate all 8 scene clips → raw_video.mp4
  3. Burn .ass subtitles into raw_video → subtitled_video.mp4
  4. Mix BGM at -18dBFS under voice, normalise voice to -14 LUFS → final.mp4
  5. Rename to distribution_ready.mp4
"""
from __future__ import annotations

import subprocess
import sys
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
    audio_path: Path,
    duration: float,
    output_path: Path,
) -> None:
    """
    Crop and loop a stock video to match audio duration, scale to 1080×1920.
    Scale down to fit inside 1080x1920, pad with black, loop to match audio.
    Applies a subtle slow-zoom (1.04x) for visual energy.
    """
    w, h = settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT
    fps = settings.VIDEO_FPS

    # Video filter chain:
    #   1. Scale down to fit inside 1080x1920
    #   2. Pad with black to exactly 1080x1920
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,"
        f"zoompan=z='min(zoom+0.0005,1.04)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(duration*fps)}:s={w}x{h}:fps={fps}"
    )

    _ffmpeg(
        "-stream_loop", "-1",          # loop video if shorter than audio
        "-i", str(video_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        str(output_path),
        description=f"build scene clip from video: {output_path.name}"
    )


def _build_scene_from_image(
    image_path: Path,
    audio_path: Path,
    duration: float,
    output_path: Path,
) -> None:
    """
    Scale image to fit, pad to 1080x1920, and apply a slow ken-burns zoom.
    """
    w, h = settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT
    fps = settings.VIDEO_FPS
    n_frames = int(duration * fps)

    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,"
        f"setsar=1,"
        f"zoompan=z='min(zoom+0.0008,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n_frames}:s={w}x{h}:fps={fps}"
    )

    _ffmpeg(
        "-loop", "1",
        "-framerate", str(fps),
        "-i", str(image_path),
        "-i", str(audio_path),
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-shortest",
        str(output_path),
        description=f"build scene clip from image: {output_path.name}"
    )


def build_scene_clips(
    voice_results: list[dict],
    visual_results: list[dict],
    clips_dir: Path,
) -> list[Path]:
    """
    Build a clip for each scene (video or image → looped video + audio).
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

        audio_path = Path(voice["mp3_path"])
        duration = voice["duration"]
        asset_path = Path(visual["asset_path"])
        asset_type = visual["asset_type"]

        clip_path = clips_dir / f"scene_{scene_id}_clip.mp4"

        log.info(
            "Building scene %d clip | type: %s | duration: %.1fs",
            scene_id, asset_type, duration
        )

        if asset_type == "video":
            _build_scene_from_video(asset_path, audio_path, duration, clip_path)
        else:
            _build_scene_from_image(asset_path, audio_path, duration, clip_path)

        clip_paths.append(clip_path)

    return clip_paths


# ──────────────────────────────────────────────────────────────────────────────
#  Step 2 — Concatenation
# ──────────────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────────────
#  Step 4 — BGM Mixing
# ──────────────────────────────────────────────────────────────────────────────

def mix_bgm(
    video_path: Path,
    bgm_path: Optional[Path],
    output_path: Path,
    bgm_volume_db: float = -18.0,
) -> Path:
    """
    Layer BGM under the voiceover and normalise the mix.
    BGM is looped to match video duration and mixed at bgm_volume_db.
    Voice is normalised to -14 LUFS (YouTube's recommended level).

    If bgm_path is None or doesn't exist, only applies loudness normalisation.
    """
    if not bgm_path or not bgm_path.exists():
        log.warning("BGM track not found at %s — skipping BGM mix", bgm_path)
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

    # Mix: voice (0dB) + BGM (at bgm_volume_db), loop BGM, normalise
    vol_factor = 10 ** (bgm_volume_db / 20)
    audio_filter = (
        f"[0:a]loudnorm=I=-14:TP=-1:LRA=11[voice];"
        f"[1:a]volume={vol_factor:.4f},aloop=loop=-1:size=2e+09[bgm];"
        f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[out]"
    )

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
        "-shortest",
        str(output_path),
        description="BGM mix + loudness normalisation"
    )
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
    raw_video = run_dir / "raw_video.mp4"
    subtitled_video = run_dir / "subtitled_video.mp4"
    final_video = run_dir / "distribution_ready.mp4"

    # Step 1: Build per-scene clips
    log.info("Step 1/4: Building %d scene clips …", len(voice_results))
    clip_paths = build_scene_clips(voice_results, visual_results, clips_dir)

    # Step 2: Concatenate
    log.info("Step 2/4: Concatenating clips …")
    concatenate_clips(clip_paths, raw_video)

    # Step 3: Burn subtitles
    log.info("Step 3/4: Burning subtitles …")
    burn_subtitles(raw_video, ass_path, subtitled_video)

    # Step 4: Mix BGM
    bgm = bgm_path or settings.BGM_PATH
    log.info("Step 4/4: Mixing BGM and normalising loudness …")
    mix_bgm(subtitled_video, bgm, final_video)

    log.info(
        "🎬 Assembly complete → %s  (%d KB)",
        final_video.name,
        final_video.stat().st_size // 1024
    )
    return final_video
