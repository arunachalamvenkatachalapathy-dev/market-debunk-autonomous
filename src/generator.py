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
    """Generate audio using Fish Audio API (energetic, Indian-understandable voice). Falls back to Kokoro TTS."""
    import requests
    import subprocess
    import re
    
    audio_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}.mp3")
    
    # Clean any inline SSML/XML tags from narration to prevent TTS voice glitches
    clean_text = re.sub(r'<[^>]+>', '', text).strip()
    
    fish_api_key = None
    try:
        fish_api_key = get_secret("FISH_AUDIO_API_KEY")
    except ValueError:
        pass
        
    if fish_api_key:
        url = "https://api.fish.audio/v1/tts"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {fish_api_key}"
        }
        payload = {
            "text": clean_text,
            "format": "mp3",
            # Default reference_id for an energetic clear English voice
            "reference_id": "c1f73740e53a47948a27d2c31cc91781" 
        }
        
        logger.info(f"🎙️ Generating voice for Scene {scene_index} via Fish Audio API...")
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                with open(audio_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"✅ [Fish Audio] Scene {scene_index} voice saved.")
                
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
                    
                words = clean_text.split()
                step = (audio_duration * 0.9) / max(1, len(words))
                word_timings = [{"word": w, "time_seconds": round(0.1 + i * step, 3)} for i, w in enumerate(words)]
                
                return audio_path, word_timings, audio_duration
            else:
                logger.warning(f"⚠️ Fish Audio failed with status {response.status_code}: {response.text}")
        except Exception as e:
            logger.warning(f"⚠️ Fish Audio request failed: {e}")
    else:
        logger.warning("⚠️ FISH_AUDIO_API_KEY is missing. Skipping Fish Audio.")
        
    # --- FALLBACK: KOKORO TTS ---
    logger.info(f"🔄 Falling back to Kokoro TTS for Scene {scene_index}...")
    try:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as kokoro_exec:
            future = kokoro_exec.submit(generate_kokoro_voice, clean_text, scene_index, arrow_state)
            return future.result(timeout=60.0)
    except Exception as kokoro_err:
        logger.error(f"❌ Kokoro TTS fallback also failed: {kokoro_err}")
        raise RuntimeError(f"Voice generation completely failed. Fish Audio and Kokoro TTS both failed.")

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
        logger.warning(f"⚠️ NVIDIA API failed for Scene {scene_index + 1}: {e}")

    # ── FALLBACK: GEMINI IMAGEN ──
    logger.warning(f"⚠️ NVIDIA failed. Trying Gemini Imagen fallback for Scene {scene_index + 1}...")
    api_key = None
    try:
        api_key = get_secret("LLM_API_KEY")
    except ValueError:
        pass
            
    if not api_key:
        raise RuntimeError("LLM_API_KEY missing, image generation completely failed.")

    client = genai.Client(api_key=api_key)
    
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
                time.sleep(3 * attempt)
                
    raise RuntimeError(f"❌ ALL image generation engines exhausted for Scene {scene_index + 1}. Aborting.")


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
