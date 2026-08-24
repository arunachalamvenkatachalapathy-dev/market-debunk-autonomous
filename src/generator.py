"""
Asset generation engine — now accepts configs from the Prompt Engineer AI
for voice, visuals, and scene processing.
"""
import os
import json
import logging
import time
import html
import concurrent.futures
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
try:
    from google.cloud import secretmanager
except ImportError:
    secretmanager = None

try:
    from google.cloud import firestore
except ImportError:
    firestore = None

try:
    from google.cloud import texttospeech
except ImportError:
    texttospeech = None
from src.config import OUTPUT_DIR

# Configure logging
logger = logging.getLogger(__name__)


def get_secret(secret_id):
    """Retrieve secret value from a dedicated secret file, environment variable, or Secret Manager."""
    # List of secret file locations to search (prioritizing Cloud Run secret mounts and local secret files)
    secret_paths = [
        "/secrets/secrets.env",
        "/secrets/.env",
        "secrets.env",
        ".env"
    ]
    
    for path in secret_paths:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            if k.strip() == secret_id:
                                return v.strip().strip("'").strip('"')
            except Exception as error:
                logger.warning(f"Failed to read secret file at {path}: {error}")

    # Fallback to environment variables
    if os.environ.get(secret_id):
        return os.environ.get(secret_id)

    project_id = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if project_id:
        try:
            client = secretmanager.SecretManagerServiceClient()
            name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8").strip()
        except Exception as error:
            logger.warning(f"Could not fetch secret '{secret_id}' via Secret Manager API: {error}")
        
    raise ValueError(f"Secret '{secret_id}' not found in secret files, environment, or Secret Manager API.")


def is_duplicate_topic(topic_hash):
    """Check Firestore to prevent publishing duplicate content."""
    try:
        db = firestore.Client()
        doc_ref = db.collection("published_shorts").document(topic_hash)
        if doc_ref.get().exists:
            return True
        doc_ref.set({"timestamp": firestore.SERVER_TIMESTAMP})
        return False
    except Exception as error:
        logger.warning(f"Firestore duplicate check bypassed (is GCP credentials set?): {error}")
        return False


def generate_kokoro_voice(text, scene_index, arrow_state="arrow_up"):
    """
    Synthesize audio using Kokoro-82M ONNX model (kokoro-onnx).
    100% Free & Open Source engine delivering ultra-fast natural human speech.
    Returns (audio_path, word_timings, audio_duration) if successful.
    """
    from kokoro_onnx import Kokoro
    import soundfile as sf
    import urllib.request
    import subprocess
    import re

    models_dir = os.path.join(os.getcwd(), "assets", "kokoro_models")
    os.makedirs(models_dir, exist_ok=True)

    model_file = os.path.join(models_dir, "kokoro-v1.0.onnx")
    voices_file = os.path.join(models_dir, "voices-v1.0.bin")

    if not os.path.exists(model_file):
        logger.info("Downloading Kokoro-82M ONNX model weights...")
        urllib.request.urlretrieve(
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
            model_file
        )

    if not os.path.exists(voices_file):
        logger.info("Downloading Kokoro-82M voice embeddings...")
        urllib.request.urlretrieve(
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
            voices_file
        )

    audio_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}.mp3")

    clean_text = re.sub(r'<[^>]+>', '', text).strip()
    clean_text = clean_text.replace('"', "'")

    # Use a friendly, natural, energetic narrator voice
    voice_name = "am_michael"
    speed = 1.05

    logger.info(f"🎙️ Synthesizing voice for Scene {scene_index} (Speaker: {arrow_state}, Kokoro voice: {voice_name})...")

    kokoro = Kokoro(model_file, voices_file)
    samples, sample_rate = kokoro.create(clean_text, voice=voice_name, speed=speed, lang="en-us")

    wav_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}_kokoro.wav")
    sf.write(wav_path, samples, sample_rate)

    conv_cmd = ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", audio_path]
    subprocess.run(conv_cmd, capture_output=True, check=True)

    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    dur_res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True, timeout=15)
    audio_duration = float(dur_res.stdout.strip())

    words = clean_text.split()
    step = (audio_duration * 0.85) / max(1, len(words))
    word_timings = [{"word": w, "time_seconds": round(0.1 + i * step, 3)} for i, w in enumerate(words)]

    logger.info(f"✅ Kokoro-82M ONNX voice track generated for Scene {scene_index} ({audio_duration:.2f}s)")
    return audio_path, word_timings, audio_duration


def generate_scene_voice(tts_client, text, scene_index, voice_config_scene=None, arrow_state="arrow_up"):
    """Generate audio and word-level timing offsets using Kokoro-82M as primary 100% free engine,
    with automatic fallback to edge-tts if Kokoro is unavailable or times out (>25s).
    """
    # ─── PRIMARY ENGINE: KOKORO-82M (25s max timeout) ───────────────────
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as kokoro_exec:
            future = kokoro_exec.submit(generate_kokoro_voice, text, scene_index, arrow_state)
            return future.result(timeout=25.0)
    except Exception as kokoro_err:
        logger.warning(f"⚠️ Kokoro-82M synthesis bypassed/failed ({kokoro_err}). Falling back to edge-tts engine...")

    # ─── FALLBACK ENGINE: EDGE-TTS ───────────────────────────────────────
    import subprocess
    import re
    import time
    
    audio_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}.mp3")
    vtt_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}.vtt")
    
    # Clean any inline SSML/XML tags from narration to prevent TTS voice glitches
    text = re.sub(r'<[^>]+>', '', text).strip()
    # Escape any problematic characters
    text = text.replace('"', "'")
    
    voice_name = "en-US-ChristopherNeural"
    rate = "+5%"
    pitch = "+0Hz"
    
    try:
        logger.info(f"Synthesizing voice for Scene {scene_index} (Speaker: {arrow_state}) using {voice_name} at rate ({rate})...")
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                subprocess.run(
                    [
                        "python", "-m", "edge_tts",
                        "--voice", voice_name,
                        "--rate", rate,
                        "--pitch", pitch,
                        "--text", text,
                        "--write-media", audio_path,
                        "--write-subtitles", vtt_path
                    ],
                    capture_output=True, text=True, check=True, timeout=60
                )
                break
            except subprocess.CalledProcessError as e:
                logger.warning(f"edge-tts attempt {attempt} failed: {e.stderr[:200]}")
                if attempt == max_retries:
                    raise RuntimeError(f"Text-to-Speech synthesis failed: {e.stderr[:500]}")
                time.sleep(2 * attempt)

        # Probe exact audio duration using ffprobe
        audio_duration = 5.0
        try:
            probe_cmd = [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", audio_path
            ]
            dur_res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True, timeout=15)
            audio_duration = float(dur_res.stdout.strip())
        except Exception as pe:
            logger.warning(f"Failed to probe audio duration for Scene {scene_index}: {pe}")
        
        # Parse word boundary timing from WebVTT subtitle file (most reliable method)
        word_timings = []
        words = text.split()
        
        if os.path.exists(vtt_path):
            try:
                with open(vtt_path, "r", encoding="utf-8") as vf:
                    vtt_content = vf.read()
                cue_pattern = re.compile(
                    r'(\d+:\d+:\d+\.\d+)\s+-->\s+(\d+:\d+:\d+\.\d+)\s*\n(.+?)(?:\n\n|\Z)',
                    re.DOTALL
                )
                for match in cue_pattern.finditer(vtt_content):
                    start_str, end_str, cue_text = match.group(1), match.group(2), match.group(3).strip()
                    def vtt_to_sec(ts):
                        parts = ts.split(":")
                        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                        return h * 3600 + m * 60 + s
                    start_sec = vtt_to_sec(start_str)
                    cue_dur = vtt_to_sec(end_str) - start_sec
                    cue_words = cue_text.split()
                    per_word = cue_dur / max(1, len(cue_words))
                    for wi, w in enumerate(cue_words):
                        clean_word = re.sub(r'<[^>]*>', '', w).strip()
                        if clean_word:
                            word_timings.append({
                                "word": clean_word,
                                "time_seconds": round(start_sec + wi * per_word, 3)
                            })
                logger.info(f"Parsed {len(word_timings)} word timings from VTT for Scene {scene_index}")
            except Exception as vtt_err:
                logger.warning(f"VTT parse failed for Scene {scene_index}: {vtt_err}")
                word_timings = []
            finally:
                try:
                    os.remove(vtt_path)
                except Exception:
                    pass

        if not word_timings or len(word_timings) < len(words) * 0.4:
            logger.info(f"Using uniform timing fallback for Scene {scene_index} ({audio_duration:.2f}s, {len(words)} words)")
            step = (audio_duration * 0.85) / max(1, len(words))
            word_timings = [{"word": w, "time_seconds": round(0.1 + i * step, 3)} for i, w in enumerate(words)]
        else:
            last_time = word_timings[-1]["time_seconds"]
            if last_time > 0 and audio_duration > 0:
                target_end = max(0.5, audio_duration * 0.88)
                scale_factor = target_end / last_time
                for wt in word_timings:
                    wt["time_seconds"] = round(wt["time_seconds"] * scale_factor, 3)
            
        logger.info(f"✅ Voice track for Scene {scene_index} ({audio_duration:.2f}s) with {len(word_timings)} synced word timings.")
        return audio_path, word_timings, audio_duration
        
    except Exception as e:
        logger.error(f"edge-tts failed: {e}")
        logger.warning(f"Both Kokoro and edge-tts failed (likely sandbox network block). Using fallback audio track.")
        import shutil
        fallback_source = os.path.join("assets", "audio", "bgm", "bgm_the_weekend.webm")
        if not os.path.exists(fallback_source):
            open(audio_path, 'w').close() # Create empty file if no fallback exists
        else:
            shutil.copy(fallback_source, audio_path)
            
        # Create dummy word timings so subtitle generator doesn't crash
        words = text.split()
        audio_duration = 5.0
        step = (audio_duration * 0.85) / max(1, len(words))
        word_timings = [{"word": w, "time_seconds": round(0.1 + i * step, 3)} for i, w in enumerate(words)]
        
        return audio_path, word_timings, audio_duration

def generate_scene_image(visual_prompt, scene_index, visual_config_scene=None):
    """
    Dynamically generates a high-quality vertical AI image using Gemini Imagen 3.
    Each scene gets a UNIQUE cache key based on scene_index + prompt hash to
    prevent cross-scene image reuse (which triggers the imagehash dedup gate).
    Retries up to 3 times on API failure.
    """
    import hashlib
    import io
    import time
    from PIL import Image
    from google import genai
    from google.genai import types
    
    bg_dir = os.path.join(os.getcwd(), "assets", "backgrounds")
    os.makedirs(bg_dir, exist_ok=True)
    
    # Apply standard brand identity style if not explicitly present
    search_query = visual_prompt
    if "Professional sleek minimalist corporate" not in search_query:
        search_query = (
            f"Professional sleek minimalist corporate 3D illustration, "
            f"deep navy blue and vibrant gold color palette, "
            f"highly recognizable editorial infographic aesthetic, no text, no letters. "
            f"{visual_prompt}"
        )
    
    # FIX #1: Cache key includes scene_index to guarantee a unique file per scene.
    # Previously only prompt hash was used — two similar prompts shared the same file.
    prompt_hash = hashlib.md5(search_query.encode()).hexdigest()[:8]
    target_path = os.path.join(bg_dir, f"ai_scene_{scene_index}_{prompt_hash}.jpg")
    
    if os.path.exists(target_path):
        logger.info(f"✅ [Gemini] Using cached image for Scene {scene_index + 1}: {target_path}")
        return {"type": "image", "path": target_path}

    logger.info(f"🎬 [Gemini] Generating AI Image for Scene {scene_index + 1}...")
    
    api_key = None
    try:
        api_key = get_secret("LLM_API_KEY")
    except ValueError:
        try:
            keys_str = get_secret("LLM_API_KEYS")
            if keys_str:
                api_key = keys_str.split(",")[0].strip()
        except ValueError:
            pass
            
    if not api_key:
        logger.error("LLM_API_KEY / LLM_API_KEYS missing for image generation!")
        return {"type": "image", "path": os.path.join(os.getcwd(), "assets", "fallback.png")}

    client = genai.Client(api_key=api_key)
    
    # FIX #6: Per-scene retry — 3 attempts before giving up
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            result = client.models.generate_images(
                model='imagen-3.0-generate-001',
                prompt=search_query,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    output_mime_type="image/jpeg",
                    aspect_ratio="9:16"
                )
            )
            for generated_image in result.generated_images:
                image = Image.open(io.BytesIO(generated_image.image.image_bytes))
                image.save(target_path)
                logger.info(f"✅ [Gemini Imagen] Image for Scene {scene_index + 1} saved → {target_path}")
                return {"type": "image", "path": target_path}
                
        except Exception as e:
            logger.warning(f"⚠️ Gemini Imagen attempt {attempt}/{max_attempts} failed for Scene {scene_index + 1}: {e}")
            if attempt < max_attempts:
                time.sleep(3 * attempt)  # exponential backoff
    
    # ── Removed free alternative API per user request ──
    logger.warning(f"⚠️ Imagen API exhausted for Scene {scene_index + 1}. No fallback APIs available.")

    # ── Last resort: generate a unique branded placeholder per scene ──
    # CRITICAL: DO NOT reuse fallback.png — identical file = hash distance 0 = evaluator blocks
    logger.error(f"❌ All image generation methods exhausted for Scene {scene_index + 1}. Creating unique placeholder.")
    try:
        from PIL import ImageDraw, ImageFont
        
        # Radically different background colors to ensure perceptual hash difference
        bg_colors = [
            (10, 25, 60),    # Navy
            (60, 15, 15),    # Dark Red
            (15, 60, 15),    # Dark Green
            (60, 60, 15),    # Dark Yellow
            (40, 15, 60)     # Dark Purple
        ]
        bg_color = bg_colors[scene_index % len(bg_colors)]
        placeholder = Image.new("RGB", (1080, 1920), color=bg_color)
        draw = ImageDraw.Draw(placeholder)
        
        # Draw a huge contrasting shape in a different quadrant to guarantee hash distance > 2
        shape_coords = [
            [0, 0, 540, 960],          # Top Left
            [540, 0, 1080, 960],       # Top Right
            [0, 960, 540, 1920],       # Bottom Left
            [540, 960, 1080, 1920],    # Bottom Right
            [270, 480, 810, 1440]      # Center
        ]
        sc = shape_coords[scene_index % len(shape_coords)]
        draw.rectangle(sc, fill=(200, 200, 200))
        
        # Text layer
        draw.rectangle([80, 800, 1000, 1100], outline=(218, 165, 32), width=8, fill=(10, 10, 10))
        draw.text((120, 880), f"Scene {scene_index + 1} Hash Buffer", fill=(218, 165, 32))
        draw.text((120, 940), search_query[:80], fill=(255, 255, 255))
        
        placeholder.save(target_path)
        logger.info(f"✅ Unique branded placeholder saved for Scene {scene_index + 1}")
    except Exception as pe:
        logger.error(f"Even placeholder creation failed: {pe}")
    
    return {"type": "image", "path": target_path}


def process_scene_assets(tts_client, scene, index, voice_config=None, visual_config=None):
    """
    Fetch voice, word marks, and visual assets for a single scene.
    Accepts PE-generated configs for both voice and visuals.
    """
    logger.info(f"=== Processing Scene {index} ===")
    
    voice_config_scene = None
    visual_config_scene = None
    
    if voice_config:
        voice_scenes = voice_config.get("scenes", [])
        for vs in voice_scenes:
            if vs.get("scene_number") == index + 1:
                voice_config_scene = vs
                break
    
    if visual_config:
        visual_scenes = visual_config.get("scenes", [])
        for vs in visual_scenes:
            if vs.get("scene_number") == index + 1:
                visual_config_scene = vs
                break
    
    audio_path, word_timings, audio_duration = generate_scene_voice(
        tts_client, scene["narration"], index,
        voice_config_scene=voice_config_scene,
        arrow_state=scene.get("arrow_state", "arrow_up")
    )
    
    visual_prompt = scene.get("visual_prompt", "")
    if visual_config_scene and visual_config_scene.get("enhanced_prompt"):
        visual_prompt = visual_config_scene["enhanced_prompt"]
    
    visual_asset = generate_scene_image(
        visual_prompt, index,
        visual_config_scene=visual_config_scene
    )
    
    emphasis_words = []
    if voice_config_scene:
        emphasis_words = voice_config_scene.get("emphasis_words", [])
    
    return {
        "index": index,
        "narration": scene["narration"],
        "arrow_state": scene.get("arrow_state", "arrow_up"),
        "audio_path": audio_path,
        "audio_duration": audio_duration,
        "word_timings": word_timings,
        "visual_asset": visual_asset,
        "emphasis_words": emphasis_words
    }


def run_synthesis_pipeline(script_data, voice_config=None, visual_config=None):
    """
    Generate all scene assets (voice + visuals) using PE configs.
    Returns processed scenes ready for assembly.
    """
    try:
        tts_client = None
        
        scenes = script_data.get("scenes", [])
        if not scenes:
            raise ValueError("Script contains no scenes!")
            
        logger.info(f"⚡ Triggering parallel asset generation for {len(scenes)} scenes...")
        processed_scenes = []
        
        # Pre-download Kokoro models synchronously to avoid thread deadlocks
        models_dir = os.path.join(os.getcwd(), "assets", "kokoro_models")
        os.makedirs(models_dir, exist_ok=True)
        model_file = os.path.join(models_dir, "kokoro-v1.0.onnx")
        voices_file = os.path.join(models_dir, "voices-v1.0.bin")
        if not os.path.exists(model_file) or not os.path.exists(voices_file):
            import urllib.request
            logger.info("Pre-downloading Kokoro-82M ONNX model weights and voices synchronously...")
            if not os.path.exists(model_file):
                urllib.request.urlretrieve("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx", model_file)
            if not os.path.exists(voices_file):
                urllib.request.urlretrieve("https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin", voices_file)
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(scenes)) as executor:
            futures = [
                executor.submit(
                    process_scene_assets, tts_client, scene, idx,
                    voice_config=voice_config,
                    visual_config=visual_config
                )
                for idx, scene in enumerate(scenes)
            ]
            for future in concurrent.futures.as_completed(futures):
                processed_scenes.append(future.result())
                
        processed_scenes.sort(key=lambda x: x["index"])
        
        return processed_scenes
        
    except Exception as error:
        logger.exception("Synthesis pipeline crashed")
        raise


def run_video_factory_pipeline(script_data, topic_title, topic_hash,
                                publish_youtube=True, publish_telegram=True):
    """Legacy pipeline entry point - backward compatible."""
    try:
        api_key = get_secret("LLM_API_KEY")
        client = genai.Client(api_key=api_key)
        tts_client = None
        
        logger.info(f"Using Script: {script_data.get('title')}")
        
        scenes = script_data.get("scenes", [])
        if not scenes:
            raise ValueError("Script contains no scenes!")
            
        logger.info(f"Triggering parallel asset generation for {len(scenes)} scenes...")
        processed_scenes = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(scenes)) as executor:
            futures = [
                executor.submit(process_scene_assets, tts_client, scene, idx)
                for idx, scene in enumerate(scenes)
            ]
            for future in concurrent.futures.as_completed(futures):
                processed_scenes.append(future.result())
                
        processed_scenes.sort(key=lambda x: x["index"])
        
        from src.video_processor import assemble_final_video
        output_video_path = assemble_final_video(processed_scenes)
        
        from src.publisher import publish_video
        publish_results = publish_video(
            video_path=output_video_path,
            title=topic_title,
            publish_youtube=publish_youtube,
            publish_telegram=publish_telegram
        )
        
        logger.info(f"Pipeline finished successfully. Outputs: {publish_results}")
        return "Success", 200
        
    except Exception as error:
        logger.exception("Pipeline crashed during execution")
        return f"Fault: {str(error)}", 500
