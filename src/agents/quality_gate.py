"""Release gates that must pass before a generated Short can be published."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from src.utils.config import settings
from src.utils.logger import get_logger


log = get_logger(__name__, phase="quality_gate")


def validate_duration(total_seconds: float) -> None:
    """Reject a render outside the channel's intentional Shorts duration range."""
    # YouTube Shorts allow up to 60s; allow a 0.5s tolerance for audio padding and container rounding
    min_allowed = settings.MIN_VIDEO_DURATION - 0.5
    max_allowed = settings.MAX_VIDEO_DURATION + 0.5
    if not min_allowed <= total_seconds <= max_allowed:
        raise RuntimeError(
            f"Release blocked: {total_seconds:.1f}s is outside the allowed "
            f"{settings.MIN_VIDEO_DURATION:.0f}-{settings.MAX_VIDEO_DURATION:.0f}s range."
        )
    log.info("Duration gate passed: %.1fs (target %s-%ss)", total_seconds, settings.MIN_VIDEO_DURATION, settings.MAX_VIDEO_DURATION)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _mean_luma(path: Path) -> float:
    """Return average brightness of the first decoded frame."""
    frame_w, frame_h = 64, 114
    frame_size = frame_w * frame_h
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(path),
        "-frames:v", "1", "-vf", f"scale={frame_w}:{frame_h},format=gray",
        "-f", "rawvideo", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0 or len(result.stdout) < frame_size:
        raise RuntimeError(f"Release blocked: could not inspect visual asset {path.name}.")
    frame = result.stdout[:frame_size]
    return sum(frame) / frame_size


def validate_visual_assets(visual_results: list[dict], expected_scene_ids: set[int]) -> None:
    """Reject missing, repeated, or known placeholder scene assets."""
    seen_ids: set[int] = set()
    seen_hashes: dict[str, int] = {}
    placeholder = settings.ASSETS_DIR / "host_original.png"
    placeholder_hash = _sha256(placeholder) if placeholder.exists() else None

    for visual in visual_results:
        scene_id = visual.get("scene_id")
        asset_path = Path(visual.get("asset_path", ""))
        if scene_id in seen_ids:
            raise RuntimeError(f"Release blocked: duplicate visual result for scene {scene_id}.")
        if scene_id not in expected_scene_ids:
            raise RuntimeError(f"Release blocked: unexpected visual scene id {scene_id}.")
        if not asset_path.is_file() or asset_path.stat().st_size == 0:
            raise RuntimeError(f"Release blocked: scene {scene_id} has no usable visual asset.")

        asset_hash = _sha256(asset_path)
        if placeholder_hash and asset_hash == placeholder_hash:
            raise RuntimeError(f"Release blocked: scene {scene_id} is the forbidden placeholder image.")
        if asset_hash in seen_hashes:
            prev_scene = seen_hashes[asset_hash]
            log.warning(
                "Scenes %d and %d used identical visual asset %s. Applying auto-differentiation...",
                prev_scene, scene_id, asset_path.name
            )
            diff_path = asset_path.parent / f"{asset_path.stem}_diff_{scene_id}{asset_path.suffix}"
            try:
                # Apply horizontal flip via FFmpeg to make the scene visually unique and alter the hash
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(asset_path), "-vf", "hflip", "-c:a", "copy", str(diff_path)],
                    capture_output=True, timeout=30, check=True
                )
                if diff_path.exists() and diff_path.stat().st_size > 0:
                    visual["asset_path"] = str(diff_path.resolve())
                    asset_path = diff_path
                    asset_hash = _sha256(asset_path)
                    log.info("✓ Auto-differentiated duplicate asset for scene %d (new hash: %s)", scene_id, asset_hash[:8])
                else:
                    raise RuntimeError(
                        f"Release blocked: scenes {seen_hashes[asset_hash]} and {scene_id} use identical visual assets."
                    )
            except RuntimeError:
                raise
            except Exception as e:
                log.warning("Asset auto-differentiation failed (%s)", e)
                raise RuntimeError(
                    f"Release blocked: scenes {seen_hashes[asset_hash]} and {scene_id} use identical visual assets."
                )
        if _mean_luma(asset_path) < 12:
            raise RuntimeError(f"Release blocked: scene {scene_id} visual asset is mostly black/empty.")
        seen_ids.add(scene_id)
        seen_hashes[asset_hash] = scene_id

    if seen_ids != expected_scene_ids:
        missing = sorted(expected_scene_ids - seen_ids)
        raise RuntimeError(f"Release blocked: missing visual assets for scenes {missing}.")
    log.info("Visual-asset gate passed: %d distinct scene assets", len(seen_ids))


def _probe_video(video_path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_entries", "format=duration:stream=width,height,codec_type",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError("Release blocked: could not probe final video.")
    return json.loads(result.stdout)


def validate_rendered_video(video_path: Path) -> None:
    """Reject a final MP4 containing visually empty/black sampled frames.

    Sampling twice per second catches failed scene clips and blank transitions
    without a heavyweight vision-model call. It runs before the upload function.
    """
    probe = _probe_video(video_path)
    duration = float(probe.get("format", {}).get("duration", 0.0))
    validate_duration(duration)

    video_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "video"]
    audio_streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
    if not video_streams:
        raise RuntimeError("Release blocked: final MP4 has no video stream.")
    if not audio_streams:
        raise RuntimeError("Release blocked: final MP4 has no audio stream.")
    stream = video_streams[0]
    expected_size = (settings.VIDEO_WIDTH, settings.VIDEO_HEIGHT)
    actual_size = (int(stream.get("width", 0)), int(stream.get("height", 0)))
    if actual_size != expected_size:
        raise RuntimeError(
            f"Release blocked: final video is {actual_size[0]}x{actual_size[1]}, expected "
            f"{expected_size[0]}x{expected_size[1]}."
        )

    frame_w, frame_h = 64, 114
    frame_size = frame_w * frame_h
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(video_path), "-vf",
        f"fps=2,scale={frame_w}:{frame_h},format=gray", "-f", "rawvideo", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=90)
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("Release blocked: could not sample final video frames for visual QA.")

    frames = [result.stdout[i:i + frame_size] for i in range(0, len(result.stdout), frame_size)]
    frames = [frame for frame in frames if len(frame) == frame_size]
    dark_frames = [index for index, frame in enumerate(frames) if sum(frame) / frame_size < 12]
    if dark_frames:
        seconds = [round(index / 2, 1) for index in dark_frames[:8]]
        raise RuntimeError(
            f"Release blocked: final video has black/empty sampled frames near {seconds}s."
        )

    # A missing final scene soundtrack is easy to miss in a visual-only check.
    # Inspect the final three seconds and reject a genuinely silent tail.
    tail_cmd = [
        "ffmpeg", "-v", "info", "-sseof", "-3", "-i", str(video_path),
        "-vn", "-af", "volumedetect", "-f", "null", "-",
    ]
    tail_result = subprocess.run(tail_cmd, capture_output=True, text=True, timeout=45)
    if tail_result.returncode != 0:
        raise RuntimeError("Release blocked: could not inspect final audio tail.")
    max_volume = None
    for line in tail_result.stderr.splitlines():
        if "max_volume:" in line:
            try:
                max_volume = float(line.split("max_volume:", 1)[1].strip().split()[0])
            except (ValueError, IndexError):
                pass
    if max_volume is None or max_volume <= -45.0:
        raise RuntimeError("Release blocked: final three seconds are silent or missing audio.")
    log.info("Rendered-video gate passed: %d sampled frames contain visible imagery", len(frames))
