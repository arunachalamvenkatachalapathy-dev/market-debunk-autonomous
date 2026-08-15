"""
Neural Lip-Sync Engine — Hugging Face Wav2Lip Integration
==========================================================
Sends an avatar image + scene audio to the Hugging Face Inference API (synclab/wav2lip)
and returns a short animated talking-face video clip.

Fallback: If the HF API is unavailable or rate-limited, falls back to an audio-reactive
syllable lip-sync that generates individual frames driven by audio RMS energy.
"""
import os
import io
import time
import logging
import subprocess
import struct
import wave

import requests
import numpy as np
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HF_WAV2LIP_URL = "https://api-inference.huggingface.co/models/synclab/wav2lip"
MAX_RETRIES = 3
RETRY_DELAY = 20          # seconds to wait on 503 (model loading)
MIN_VALID_BYTES = 5_000   # response smaller than this is treated as an error
FPS = 25
RMS_THRESHOLD = 0.012     # audio energy threshold for "mouth open" frames


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _read_audio_rms(audio_path: str, hop_ms: int = 40) -> list[float]:
    """
    Read an audio file (MP3 or WAV) and return a list of RMS energy values,
    one value per `hop_ms` milliseconds.  Used for the fallback lip-sync.
    """
    # Convert to WAV first so we can use stdlib wave module
    wav_path = audio_path.replace(".mp3", "_tmp.wav").replace(".ogg", "_tmp.wav")
    if not wav_path.endswith(".wav"):
        wav_path = audio_path + "_tmp.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", audio_path, "-ac", "1", "-ar", "16000", wav_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        )
        with wave.open(wav_path, "rb") as wf:
            framerate = wf.getframerate()
            hop_frames = int(framerate * hop_ms / 1000)
            rms_list = []
            while True:
                raw = wf.readframes(hop_frames)
                if not raw:
                    break
                samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
                rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) > 0 else 0.0
                rms_list.append(rms)
        return rms_list
    except Exception as exc:
        logger.warning(f"⚠️  RMS extraction failed ({exc}), using uniform 'open' state")
        return []
    finally:
        if os.path.exists(wav_path):
            try:
                os.remove(wav_path)
            except Exception:
                pass


def _audio_duration(audio_path: str) -> float:
    """Return duration of audio file in seconds via ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
        return float(result.stdout.strip())
    except Exception:
        return 5.0


# ---------------------------------------------------------------------------
# Fallback: Audio-Reactive Syllable Lip-Sync
# ---------------------------------------------------------------------------

def _generate_lipsync_fallback(
    open_img_path: str,
    closed_img_path: str,
    audio_path: str,
    output_path: str,
    fps: int = FPS
) -> str:
    """
    Generates an animated talking-face video by alternating between
    `open_img_path` and `closed_img_path` driven by the audio RMS energy.

    Each 40ms hop decides whether the mouth is open or closed.
    Returns path to the generated video file.
    """
    logger.info("🔄 Using fallback audio-reactive lip-sync...")

    duration = _audio_duration(audio_path)
    rms_values = _read_audio_rms(audio_path, hop_ms=40)

    open_img = Image.open(open_img_path).convert("RGBA")
    closed_img = Image.open(closed_img_path).convert("RGBA")

    frames_dir = output_path.replace(".mp4", "_frames")
    os.makedirs(frames_dir, exist_ok=True)

    total_frames = max(1, int(fps * duration))
    hop_ms = 40
    hops_per_frame = max(1, int(1000 / (fps * hop_ms)))  # ~1 hop per frame at 25fps

    for frame_idx in range(total_frames):
        # Map frame to RMS hop index
        time_ms = (frame_idx / fps) * 1000
        hop_idx = int(time_ms / hop_ms)

        if rms_values and hop_idx < len(rms_values):
            rms = rms_values[hop_idx]
            mouth_open = rms > RMS_THRESHOLD
        else:
            # No RMS data — alternate open/closed every 3 frames (rough talking rhythm)
            mouth_open = (frame_idx % 6) < 3

        # Add subtle head-bob when speaking: shift image up 3px on open frames
        y_shift = -3 if mouth_open else 0
        img = open_img if mouth_open else closed_img
        frame = Image.new("RGBA", img.size, (0, 0, 0, 0))
        frame.paste(img, (0, y_shift))

        frame_path = os.path.join(frames_dir, f"frame_{frame_idx:05d}.png")
        frame.convert("RGB").save(frame_path, format="PNG")

    # Encode frames → video (no audio — audio is merged later in the pipeline)
    frame_pattern = os.path.join(frames_dir, "frame_%05d.png")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", frame_pattern,
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            output_path
        ],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
    )

    # Clean up frame images
    for f in os.listdir(frames_dir):
        try:
            os.remove(os.path.join(frames_dir, f))
        except Exception:
            pass
    try:
        os.rmdir(frames_dir)
    except Exception:
        pass

    logger.info(f"✅ Fallback lip-sync video saved: {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Main: Hugging Face Wav2Lip API
# ---------------------------------------------------------------------------

def run_wav2lip_hf(
    image_path: str,
    audio_path: str,
    output_path: str,
    hf_token: str,
    open_img_path: str = None,
    closed_img_path: str = None
) -> str:
    """
    Sends `image_path` (PNG face) + `audio_path` (MP3/WAV) to the HF Wav2Lip API.
    Saves the resulting talking-face video to `output_path` and returns that path.

    Falls back to audio-reactive syllable lip-sync if the API call fails.

    Parameters
    ----------
    image_path      : path to the face image (PNG)
    audio_path      : path to the scene audio (MP3 or WAV)
    output_path     : where to save the output .mp4
    hf_token        : Hugging Face API token
    open_img_path   : path to open-mouth avatar (for fallback)
    closed_img_path : path to closed-mouth avatar (for fallback)
    """
    if not hf_token:
        logger.warning("⚠️  HF_API_KEY not set — skipping Wav2Lip, using fallback.")
        return _run_fallback(open_img_path, closed_img_path, audio_path, output_path)

    headers = {"Authorization": f"Bearer {hf_token}"}

    # Read both files as bytes
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        with open(audio_path, "rb") as f:
            audio_bytes = f.read()
    except Exception as exc:
        logger.error(f"❌ Could not read input files: {exc}")
        return _run_fallback(open_img_path, closed_img_path, audio_path, output_path)

    # Determine audio MIME type
    audio_mime = "audio/mpeg" if audio_path.lower().endswith(".mp3") else "audio/wav"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"🎤 Calling HF Wav2Lip API (attempt {attempt}/{MAX_RETRIES})...")

            response = requests.post(
                HF_WAV2LIP_URL,
                headers=headers,
                files={
                    "image": ("avatar.png", image_bytes, "image/png"),
                    "audio": ("speech.mp3", audio_bytes, audio_mime),
                },
                timeout=120
            )

            if response.status_code == 503:
                logger.warning(f"⏳ HF model loading (503) — waiting {RETRY_DELAY}s before retry...")
                time.sleep(RETRY_DELAY)
                continue

            if response.status_code == 429:
                logger.warning("⏳ HF rate limit (429) — waiting 30s before retry...")
                time.sleep(30)
                continue

            if response.status_code != 200:
                logger.warning(
                    f"⚠️  HF returned {response.status_code}: {response.text[:300]}"
                )
                if attempt == MAX_RETRIES:
                    break
                time.sleep(10)
                continue

            # Validate the response is a real video
            video_bytes = response.content
            if len(video_bytes) < MIN_VALID_BYTES:
                logger.warning(
                    f"⚠️  HF response too small ({len(video_bytes)} bytes) — likely an error JSON, not a video."
                )
                if attempt == MAX_RETRIES:
                    break
                time.sleep(10)
                continue

            # Save the video
            with open(output_path, "wb") as f:
                f.write(video_bytes)

            logger.info(
                f"✅ Wav2Lip lip-sync generated: {output_path} ({len(video_bytes) // 1024}KB)"
            )
            return output_path

        except requests.exceptions.Timeout:
            logger.warning(f"⏱️  HF API timeout on attempt {attempt}")
            if attempt < MAX_RETRIES:
                time.sleep(10)
        except Exception as exc:
            logger.error(f"❌ HF API error on attempt {attempt}: {exc}")
            if attempt < MAX_RETRIES:
                time.sleep(10)

    # All retries exhausted — use fallback
    logger.warning("⚠️  HF Wav2Lip failed after all retries — switching to audio-reactive fallback.")
    return _run_fallback(open_img_path, closed_img_path, audio_path, output_path)


def _run_fallback(open_img_path, closed_img_path, audio_path, output_path):
    """Thin wrapper that validates paths and calls the fallback generator."""
    if not open_img_path or not closed_img_path:
        # Derive fallback paths from the output path convention
        avatars_dir = os.path.join(os.getcwd(), "assets", "avatars")
        # Default to analyst (most common speaker), can be overridden by caller
        open_img_path = open_img_path or os.path.join(avatars_dir, "analyst_open.png")
        closed_img_path = closed_img_path or os.path.join(avatars_dir, "analyst_closed.png")

    if not os.path.exists(open_img_path) or not os.path.exists(closed_img_path):
        logger.error("❌ Avatar fallback images not found. Cannot generate lip-sync.")
        raise FileNotFoundError(f"Avatar images missing: {open_img_path}, {closed_img_path}")

    return _generate_lipsync_fallback(open_img_path, closed_img_path, audio_path, output_path)
