"""
src/agents/voice_agent.py

Phase 3 — Voice Synthesis (Microsoft Edge TTS)

Uses `edge-tts` (Microsoft Edge Neural TTS) — completely free, no API key,
high-quality Neural voices. Generates per-scene MP3 files and produces
word-level timestamp data for subtitle rendering.

Phase 3 — Voice Synthesis (Google Cloud TTS)

Uses Google Cloud Text-to-Speech API for high-quality Neural voices.
Generates per-scene MP3 files and produces estimated word-level 
timestamp data for subtitle rendering.

Default voice: en-US-Journey-D (Neutral male)
"""
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

def synthesize_scene(
    scene_id: int,
    narration: str,
    audio_dir: Path,
    voice_name: str = DEFAULT_VOICE,
) -> dict:
    """Synthesize a single scene's narration using Google TTS."""
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
    
    duration = get_audio_duration(mp3_path)
    
    # Generate approximate word timings for subtitles
    words = narration.split()
    word_duration = duration / max(len(words), 1)
    word_timings = []
    
    for i, w in enumerate(words):
        word_timings.append({
            "word": w,
            "start": i * word_duration,
            "end": (i + 1) * word_duration
        })
        
    timings_path.write_text(json.dumps(word_timings, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "scene_id": scene_id,
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


def get_available_voices() -> list[str]:
    """Returns list of available edge-tts voices (cached after first call)."""
    async def _list():
        voices = await edge_tts.list_voices()
        return [v["ShortName"] for v in voices if "en-IN" in v["ShortName"] or "en-US" in v["ShortName"]]

    return asyncio.run(_list())
