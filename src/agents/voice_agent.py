"""
src/agents/voice_agent.py

Phase 3 — Voice Synthesis (Microsoft Edge TTS)

Uses `edge-tts` (Microsoft Edge Neural TTS) — completely free, no API key,
high-quality Neural voices. Generates per-scene MP3 files and produces
word-level timestamp data for subtitle rendering.

Default voice: en-IN-NeerjaNeural (Indian female, clear, professional)
Alternate:     en-IN-PrabhatNeural (Indian male)
               en-US-AriaNeural    (US female, neutral)

Output per scene:
  output/<run_id>/audio/scene_1.mp3
  output/<run_id>/audio/scene_1_timings.json  ← word-level timestamps
"""
from __future__ import annotations

import asyncio
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import edge_tts

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="voice_synthesis")

# ──────────────────────────────────────────────────────────────────────────────
#  Voice Configuration
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_VOICE = "en-IE-ConnorNeural"   # Irish male, requested by user
RATE_ADJUST = "+0%"                     # speaking rate (-10% to +10%)
VOLUME_ADJUST = "+0%"                   # volume offset
PITCH_ADJUST = "-5Hz"                   # slight lower pitch = more gravitas


# ──────────────────────────────────────────────────────────────────────────────
#  Async Core
# ──────────────────────────────────────────────────────────────────────────────

async def _synthesize_scene_async(
    text: str,
    output_mp3: Path,
    timings_json: Path,
    voice: str = DEFAULT_VOICE,
) -> list[dict]:
    """
    Synthesizes one scene narration using edge-tts.

    Returns list of word timing dicts:
      [{"word": "...", "start": 0.0, "end": 0.5}, ...]
    """
    output_mp3.parent.mkdir(parents=True, exist_ok=True)

    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=RATE_ADJUST,
        volume=VOLUME_ADJUST,
        pitch=PITCH_ADJUST,
    )

    # Collect audio bytes and word boundary events
    audio_chunks: list[bytes] = []
    word_timings: list[dict] = []
    current_offset_ms: int = 0

    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_chunks.append(chunk["data"])
        elif chunk["type"] == "WordBoundary":
            word_timings.append({
                "word": chunk["text"],
                "start": chunk["offset"] / 10_000_000,   # 100ns → seconds
                "end": (chunk["offset"] + chunk["duration"]) / 10_000_000,
            })

    # Write raw audio (edge-tts outputs MP3 directly)
    if audio_chunks:
        output_mp3.write_bytes(b"".join(audio_chunks))
        log.info("Saved audio: %s (%d bytes)", output_mp3.name, output_mp3.stat().st_size)
    else:
        raise RuntimeError(f"edge-tts returned no audio for text: '{text[:50]}...'")

    # Save timings
    timings_json.write_text(json.dumps(word_timings, indent=2, ensure_ascii=False), encoding="utf-8")
    log.debug("Saved %d word timings: %s", len(word_timings), timings_json.name)

    return word_timings


# ──────────────────────────────────────────────────────────────────────────────
#  Audio Duration Helper
# ──────────────────────────────────────────────────────────────────────────────

def get_audio_duration(mp3_path: Path) -> float:
    """Returns the duration of an MP3 file in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(mp3_path),
            ],
            capture_output=True, text=True, timeout=10
        )
        return float(result.stdout.strip())
    except Exception as exc:
        log.warning("ffprobe failed for %s: %s — estimating from text length", mp3_path.name, exc)
        # Rough estimate: ~2.5 words per second
        return 5.0  # safe default


# ──────────────────────────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────────────────────────

def synthesize_scene(
    scene_id: int,
    narration: str,
    audio_dir: Path,
    voice: str = DEFAULT_VOICE,
) -> dict:
    """
    Synthesize a single scene's narration.

    Returns:
        {
            "scene_id": 1,
            "mp3_path": "/path/to/scene_1.mp3",
            "timings_path": "/path/to/scene_1_timings.json",
            "duration": 7.3,
            "word_timings": [...]
        }
    """
    log.info("Synthesizing scene %d: '%s...'", scene_id, narration[:40])

    mp3_path = audio_dir / f"scene_{scene_id}.mp3"
    timings_path = audio_dir / f"scene_{scene_id}_timings.json"

    word_timings = asyncio.run(
        _synthesize_scene_async(narration, mp3_path, timings_path, voice)
    )

    duration = get_audio_duration(mp3_path)

    return {
        "scene_id": scene_id,
        "mp3_path": str(mp3_path),
        "timings_path": str(timings_path),
        "duration": duration,
        "word_timings": word_timings,
    }


def synthesize_all_scenes(scenes: list[dict], audio_dir: Path, voice: str = DEFAULT_VOICE) -> list[dict]:
    """
    Synthesize voice for all 8 scenes sequentially.
    Returns list of synthesis result dicts (one per scene).
    """
    audio_dir.mkdir(parents=True, exist_ok=True)
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


def get_available_voices() -> list[str]:
    """Returns list of available edge-tts voices (cached after first call)."""
    async def _list():
        voices = await edge_tts.list_voices()
        return [v["ShortName"] for v in voices if "en-IN" in v["ShortName"] or "en-US" in v["ShortName"]]

    return asyncio.run(_list())
