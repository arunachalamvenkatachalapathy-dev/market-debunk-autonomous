"""
src/agents/voice_agent.py

Phase 3 — Voice Synthesis (Google Cloud TTS)

Uses Google Cloud Text-to-Speech API for high-quality Neural voices.
Generates per-scene MP3 files and produces estimated word-level 
timestamp data for subtitle rendering.

Default voice: en-IN-Chirp3-HD-Orus
"""
import html
import json
import re
import subprocess
from pathlib import Path

from google.cloud import texttospeech
from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="voice_synthesis")

DEFAULT_VOICE = settings.VOICE_NAME

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

def trim_audio_silence(input_path: Path, output_path: Path):
    """Aggressively trims leading and trailing silence to prevent robotic stitching pauses."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(input_path),
                "-af", "silenceremove=start_periods=1:start_threshold=-45dB:start_duration=0.03,areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_duration=0.03,areverse",
                str(output_path)
            ],
            capture_output=True, check=True
        )
    except subprocess.CalledProcessError as e:
        log.error("FFmpeg silence removal failed: %s", e.stderr)
        # Fallback to the original file if trimming fails
        import shutil
        shutil.copy(input_path, output_path)


def _build_ssml(narration: str) -> str:
    """Add light SSML direction for smoother, less robotic delivery."""
    text = html.escape(" ".join(narration.split()))
    text = re.sub(r"([.!?])\s+", r'\1 <break time="180ms"/> ', text)
    text = re.sub(r"([,:;])\s+", r'\1 <break time="90ms"/> ', text)
    rate_pct = int(settings.VOICE_SPEAKING_RATE * 100)
    pitch = settings.VOICE_PITCH
    return (
        "<speak>"
        f"<prosody rate=\"{rate_pct}%\" pitch=\"{pitch:+.1f}st\">"
        f"{text}"
        "</prosody>"
        "</speak>"
    )


def synthesize_scene(
    scene_id: int,
    narration: str,
    audio_dir: Path,
    voice_name: str = DEFAULT_VOICE,
) -> dict:
    """Synthesize a single scene's narration using Google TTS."""
    log.info("Synthesizing scene %d with Google TTS...", scene_id)
    audio_dir.mkdir(parents=True, exist_ok=True)
    
    raw_mp3_path = audio_dir / f"scene_{scene_id}_raw.mp3"
    mp3_path = audio_dir / f"scene_{scene_id}.mp3"
    timings_path = audio_dir / f"scene_{scene_id}_timings.json"

    client = texttospeech.TextToSpeechClient()
    synthesis_input = texttospeech.SynthesisInput(ssml=_build_ssml(narration))
    
    # Extract language code from voice name (e.g. "en-IN-Wavenet-B" -> "en-IN")
    lang_code = "-".join(voice_name.split("-")[:2])
    
    voice = texttospeech.VoiceSelectionParams(
        language_code=lang_code,
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
    raw_mp3_path.write_bytes(response.audio_content)
    
    # Trim silence to ensure fluid pacing across scene cuts
    trim_audio_silence(raw_mp3_path, mp3_path)
    # Cleanup raw file
    raw_mp3_path.unlink(missing_ok=True)
    
    duration = get_audio_duration(mp3_path)
    
    # Generate approximate word timings for subtitles based on character length
    words = narration.split()
    # Strip punctuation for length calculation to be more accurate
    clean_words = ["".join(c for c in w if c.isalnum()) for w in words]
    total_chars = sum(len(w) for w in clean_words)
    
    word_timings = []
    current_time = 0.0
    
    for i, w in enumerate(words):
        # Give each word a duration proportional to its letter count (plus a tiny baseline)
        c_len = max(len(clean_words[i]), 1)
        word_duration = duration * (c_len / max(total_chars, 1))
        
        word_timings.append({
            "word": w,
            "start": current_time,
            "end": current_time + word_duration
        })
        current_time += word_duration
        
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
    """Return available Google Cloud TTS voices for English/India and English/US."""
    client = texttospeech.TextToSpeechClient()
    voices = client.list_voices().voices
    return [
        voice.name for voice in voices
        if voice.language_codes and any(code in {"en-IN", "en-US"} for code in voice.language_codes)
    ]
