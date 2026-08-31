"""
src/agents/voice_agent.py

Phase 3 — Voice Synthesis (Google Cloud TTS with Anti-Clipping Padding)

Uses Google Cloud Text-to-Speech API for natural voice generation.
Automatically adds pre- and post-silence padding to guarantee that
words are never cut off at the start or ending of scenes.

Default voice: en-US-Journey-D (Natural male)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from google.cloud import texttospeech
from src.utils.logger import get_logger

log = get_logger(__name__, phase="voice_synthesis")

DEFAULT_VOICE = "en-US-Journey-D"  # Natural male voice from Google TTS


def get_audio_duration(mp3_path: Path) -> float:
    """Returns the duration of an MP3 file in seconds using ffprobe."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(mp3_path)],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception as exc:
        log.warning("ffprobe failed: %s", exc)
        return 5.0


def _add_audio_padding(mp3_path: Path, pre_silence_ms: int = 180, post_silence_ms: int = 350) -> None:
    """
    Add silence before and after TTS audio to prevent beginning/ending clipping.
    pre_silence_ms: 180ms delay before speech starts
    post_silence_ms: 350ms acoustic decay pad after speech ends
    """
    temp_padded = mp3_path.with_name(f"{mp3_path.stem}_padded.mp3")
    try:
        cmd = [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", str(mp3_path),
            "-af", f"adelay={pre_silence_ms}|{pre_silence_ms},apad=pad_dur={post_silence_ms / 1000.0}",
            "-c:a", "libmp3lame",
            "-b:a", "192k",
            str(temp_padded)
        ]
        subprocess.run(cmd, check=True)
        temp_padded.replace(mp3_path)
    except Exception as exc:
        log.warning("Audio padding failed (%s) — keeping original file", exc)
        if temp_padded.exists():
            temp_padded.unlink()


def synthesize_scene(
    scene_id: int,
    narration: str,
    audio_dir: Path,
    voice_name: str = DEFAULT_VOICE,
) -> dict:
    """Synthesize a single scene's narration using Google TTS with padding."""
    log.info("Synthesizing scene %d with Google TTS...", scene_id)
    audio_dir.mkdir(parents=True, exist_ok=True)

    mp3_path = audio_dir / f"scene_{scene_id}.mp3"
    timings_path = audio_dir / f"scene_{scene_id}_timings.json"

    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(text=narration)

    voice = texttospeech.VoiceSelectionParams(
        language_code="en-US",
        name=voice_name
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
    )

    request = texttospeech.SynthesizeSpeechRequest(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )

    response = client.synthesize_speech(request=request)
    mp3_path.write_bytes(response.audio_content)

    # Apply anti-clipping audio padding
    _add_audio_padding(mp3_path, pre_silence_ms=180, post_silence_ms=350)

    duration = get_audio_duration(mp3_path)

    # Word timings for any downstream reference
    words = narration.split()
    clean_words = ["".join(c for c in w if c.isalnum()) for w in words]
    total_chars = sum(len(w) for w in clean_words)

    word_timings = []
    current_time = 0.18  # Offset by pre_silence_ms

    for i, w in enumerate(words):
        c_len = max(len(clean_words[i]), 1) if i < len(clean_words) else 1
        word_duration = (duration - 0.53) * (c_len / max(total_chars, 1))
        word_duration = max(word_duration, 0.1)

        word_timings.append({
            "word": w,
            "start": current_time,
            "end": current_time + word_duration
        })
        current_time += word_duration

    timings_path.write_text(json.dumps(word_timings, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "scene_id": scene_id,
        "narration": narration,
        "mp3_path": str(mp3_path),
        "timings_path": str(timings_path),
        "duration": duration,
        "word_timings": word_timings,
    }


def synthesize_all_scenes(scenes: list[dict], audio_dir: Path, voice: str = DEFAULT_VOICE) -> list[dict]:
    """Synthesize voice for all scenes using Google TTS."""
    results = []

    for scene in scenes:
        sid = scene["scene_id"]
        narration = scene["narration"]

        try:
            result = synthesize_scene(sid, narration, audio_dir, voice)
            results.append(result)
            log.info(
                "✓ Scene %d synthesized | duration: %.1fs | words: %d",
                sid, result["duration"], len(result["word_timings"])
            )
        except Exception as exc:
            log.error("✗ Scene %d synthesis FAILED: %s", sid, exc)
            raise

    total_duration = sum(r["duration"] for r in results)
    log.info("All %d scenes synthesized | total audio: %.1fs", len(results), total_duration)
    return results
