"""
src/agents/voice_agent.py

Phase 3 — Voice Synthesis (Google Cloud TTS)

Uses Google Cloud Text-to-Speech API for high-quality Neural voices.
Generates per-scene MP3 files and produces estimated word-level 
timestamp data for subtitle rendering.

Default voice: en-IN-Chirp3-HD-Fenrir (Look F — Dark Editorial)
"""
import html
import json
import re
import subprocess
from pathlib import Path

try:
    from google.cloud import texttospeech
except ImportError:
    texttospeech = None

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
    """
    Trims leading silence and trailing silence cleanly, adding a natural 300ms (0.3s)
    breath pad so inter-scene transitions have comfortable breathing room without
    sounding rushed, robotic, or clipped at word endings.
    """
    try:
        af = (
            "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB,"
            "areverse,"
            "silenceremove=start_periods=1:start_duration=0.05:start_threshold=-45dB,"
            "areverse,"
            "apad=pad_dur=0.30"
        )
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(input_path),
                "-af", af,
                "-c:a", "libmp3lame", "-b:a", "192k",
                str(output_path)
            ],
            capture_output=True, check=True
        )
    except subprocess.CalledProcessError as e:
        log.error("FFmpeg silence removal failed: %s", e.stderr)
        # Fallback to the original file if trimming fails
        import shutil
        shutil.copy(input_path, output_path)


def normalize_english_for_tts(text: str) -> str:
    """
    Normalizes numbers, financial currency symbols, percentages, and acronyms
    so Google Neural TTS speaks with clear, natural cadence and zero phonetic glitches.
    """
    t = text.strip()
    t = re.sub(r"<[^>]+>", "", t)

    # 1. Currency with units (e.g. ₹1.2 Cr -> 1.2 crore rupees)
    t = re.sub(r"(?:₹|Rs\.?)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:Cr|Crores?|crores?)\b", r"\1 crore rupees", t)
    t = re.sub(r"(?:₹|Rs\.?)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:L|Lakhs?|lakhs?)\b", r"\1 lakh rupees", t)
    t = re.sub(r"(?:₹|Rs\.?)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*[Kk]\b", r"\1 thousand rupees", t)

    # 2. Currency amount alone (e.g. ₹50,000 -> 50,000 rupees)
    t = re.sub(r"(?:₹|Rs\.?)\s*(\d+(?:,\d+)*(?:\.\d+)?)", r"\1 rupees", t)
    t = t.replace("₹", " rupees ")

    # 3. Percentages: 6.8% -> 6.8 percent
    t = re.sub(r"(\d+(?:\.\d+)?)\s*%", r"\1 percent", t)

    # 4. Financial acronyms & spaced pronunciations
    t = re.sub(r"\bF&O\b|\bf&o\b", "F and O", t)
    t = re.sub(r"\bP/E\b|\bp/e\b", "P E", t)
    t = re.sub(r"\bFD\b", "F D", t)
    t = re.sub(r"\bFDs\b", "F Ds", t)
    t = re.sub(r"\bIPO\b", "I P O", t)
    t = re.sub(r"\bIPOs\b", "I P Os", t)
    t = re.sub(r"\bSIP\b", "S I P", t)
    t = re.sub(r"\bSIPs\b", "S I Ps", t)
    t = re.sub(r"\bEMI\b", "E M I", t)
    t = re.sub(r"\bEMIs\b", "E M Is", t)
    t = re.sub(r"\bGST\b", "G S T", t)
    t = re.sub(r"\bATM\b", "A T M", t)
    t = re.sub(r"\bAMC\b", "A M C", t)
    t = re.sub(r"\bRBI\b", "R B I", t)
    t = re.sub(r"\bSEBI\b", "SEBI", t)
    t = re.sub(r"\bNIFTY\b", "Nifty", t)
    t = re.sub(r"\bSENSEX\b", "Sensex", t)
    t = re.sub(r"\bvs\.?\b", "versus", t, flags=re.IGNORECASE)

    # 5. Convert colons and semicolons to natural spoken pause markers (commas)
    t = re.sub(r"[:;]\s*", ", ", t)

    t = re.sub(r"\s+", " ", t).strip()
    return t


def _build_ssml(narration: str, scene_id: int = 1) -> str:
    """
    Build natural conversational SSML with controlled clause-level breath breaks:
    - 180ms breath pause at commas and em-dashes.
    - 280ms breath pause between sentences within the scene.
    - Normalizes currencies, percentages, and financial acronyms before synthesis.
    """
    norm_text = normalize_english_for_tts(narration)
    # Use quote=False so ' and " remain literal characters in XML text content,
    # preventing XML entity mangling (e.g., &#x27; or &quot;).
    escaped = html.escape(norm_text, quote=False)

    # Replace em-dashes and en-dashes with clause breath break
    escaped = re.sub(r"\s*[—–]\s*", ', <break time="180ms"/> ', escaped)
    # Micro-break after commas (protecting commas inside numbers like 50,000)
    escaped = re.sub(r",(?!\d)\s*", ', <break time="180ms"/> ', escaped)
    # Sentence boundary breath break if multiple sentences exist within scene
    escaped = re.sub(r"([.!?])\s+(?=[A-Z0-9])", r'\1 <break time="280ms"/> ', escaped)
    # Clean up duplicate break tags
    escaped = re.sub(r'(<break time="\d+ms"/>\s*)+', r'\1', escaped)

    rate_pct = int(settings.VOICE_SPEAKING_RATE * 100)
    rate = f"{rate_pct}%"
    # Chirp voices reject pitch parameter in prosody
    if "chirp" in settings.VOICE_NAME.lower():
        prosody_open = f'<prosody rate="{rate}">'
    else:
        pitch = f"{settings.VOICE_PITCH:+.1f}st"
        prosody_open = f'<prosody rate="{rate}" pitch="{pitch}">'
    ssml = f"<speak>{prosody_open}{escaped}</prosody></speak>"

    # Enforce max SSML length (Google limit ~5000 chars). If exceeded, fall back to plain escaped text.
    max_len = getattr(settings, "MAX_SSML_LENGTH", 4800)
    if len(ssml) > max_len:
        log.warning("SSML length %d exceeds max %d, falling back to plain text for scene %d", len(ssml), max_len, scene_id)
        return f"<speak>{escaped}</speak>"
    return ssml


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
    
    # Extract language code from voice name (e.g. "en-IN-Wavenet-B" -> "en-IN")
    lang_code = "-".join(voice_name.split("-")[:2])
    
    voice = texttospeech.VoiceSelectionParams(
        language_code=lang_code,
        name=voice_name
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
    )
    
    # Attempt SSML synthesis first; fall back cleanly to normalized plain text if SSML fails
    try:
        synthesis_input = texttospeech.SynthesisInput(ssml=_build_ssml(narration, scene_id))
        request = texttospeech.SynthesizeSpeechRequest(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config
        )
        response = client.synthesize_speech(request=request)
    except Exception as ssml_err:
        log.warning("Scene %d SSML synthesis failed (%s), falling back to plain text", scene_id, ssml_err)
        clean_text = normalize_english_for_tts(narration)
        request = texttospeech.SynthesizeSpeechRequest(
            input=texttospeech.SynthesisInput(text=clean_text),
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

    target_duration = float(getattr(settings, "VIDEO_DURATION_TARGET", 25.0))
    max_duration_cap = float(getattr(settings, "MAX_VIDEO_DURATION", 58.0)) - 6.0  # ~52.0s

    if total_duration > max_duration_cap:
        speedup = min(1.35, max(1.02, total_duration / target_duration))
        log.info(
            "⏱️ Total voice duration (%.1fs) exceeds %.1fs cap. Applying automatic FFmpeg atempo speedup of %.3fx to reach ~%.1fs target...",
            total_duration, max_duration_cap, speedup, target_duration
        )
        for r in results:
            mp3_path = Path(r["mp3_path"])
            if mp3_path.exists():
                tmp_mp3 = mp3_path.with_name(f"{mp3_path.stem}_speed.mp3")
                cmd = [
                    "ffmpeg", "-y", "-i", str(mp3_path),
                    "-af", f"atempo={speedup:.4f}",
                    "-c:a", "libmp3lame", "-b:a", "192k",
                    "-vn", str(tmp_mp3)
                ]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0 and tmp_mp3.exists():
                    tmp_mp3.replace(mp3_path)
                    r["duration"] = get_audio_duration(mp3_path)
                else:
                    log.warning("FFmpeg atempo failed for %s: %s", mp3_path, res.stderr)
                    r["duration"] = round(r["duration"] / speedup, 2)
            else:
                r["duration"] = round(r["duration"] / speedup, 2)

            for wt in r.get("word_timings", []):
                if "start" in wt:
                    wt["start"] = round(wt["start"] / speedup, 3)
                if "end" in wt:
                    wt["end"] = round(wt["end"] / speedup, 3)

            timings_path = Path(r["timings_path"])
            if timings_path.exists():
                timings_path.write_text(
                    json.dumps(r["word_timings"], indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )

    min_duration_floor = float(getattr(settings, "MIN_VIDEO_DURATION", 20.0))
    if total_duration < min_duration_floor:
        slowdown = max(0.85, total_duration / 24.0)
        log.info(
            "⏱️ Total voice duration (%.1fs) is below %.1fs floor. Applying automatic FFmpeg atempo slowdown of %.3fx to reach ~24.0s target...",
            total_duration, min_duration_floor, slowdown
        )
        for r in results:
            mp3_path = Path(r["mp3_path"])
            if mp3_path.exists():
                tmp_mp3 = mp3_path.with_name(f"{mp3_path.stem}_slow.mp3")
                cmd = [
                    "ffmpeg", "-y", "-i", str(mp3_path),
                    "-af", f"atempo={slowdown:.4f}",
                    "-c:a", "libmp3lame", "-b:a", "192k",
                    "-vn", str(tmp_mp3)
                ]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if res.returncode == 0 and tmp_mp3.exists():
                    tmp_mp3.replace(mp3_path)
                    r["duration"] = get_audio_duration(mp3_path)
                else:
                    r["duration"] = round(r["duration"] / slowdown, 2)
            else:
                r["duration"] = round(r["duration"] / slowdown, 2)

            for wt in r.get("word_timings", []):
                if "start" in wt:
                    wt["start"] = round(wt["start"] / slowdown, 3)
                if "end" in wt:
                    wt["end"] = round(wt["end"] / slowdown, 3)

            timings_path = Path(r["timings_path"])
            if timings_path.exists():
                timings_path.write_text(
                    json.dumps(r["word_timings"], indent=2, ensure_ascii=False),
                    encoding="utf-8"
                )

    new_total = sum(r["duration"] for r in results)
    log.info("✅ Auto-compressed voice track duration: %.1fs -> %.1fs", total_duration, new_total)

    return results


def get_available_voices() -> list[str]:
    """Return available Google Cloud TTS voices for English/India and English/US."""
    client = texttospeech.TextToSpeechClient()
    voices = client.list_voices().voices
    return [
        voice.name for voice in voices
        if voice.language_codes and any(code in {"en-IN", "en-US"} for code in voice.language_codes)
    ]
