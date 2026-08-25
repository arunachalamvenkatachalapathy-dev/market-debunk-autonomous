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


def generate_gemini_voice(text, scene_index, arrow_state="arrow_up"):
    """
    Synthesize audio using Gemini 3.5 Live Translate API (Audio output mode).
    This acts as a high-fidelity cloud TTS engine.
    """
    import asyncio
    import os
    import subprocess
    import re
    from google import genai
    from google.genai import types

    audio_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}.mp3")
    pcm_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}.pcm")

    clean_text = re.sub(r'<[^>]+>', '', text).strip()
    
    logger.info(f"🎙️ Synthesizing voice for Scene {scene_index} using Gemini Live Audio API...")

    gemini_key = os.environ.get("GEMINI_TTS_API_KEY") or get_secret("GEMINI_TTS_API_KEY")
    if not gemini_key:
        raise ValueError("GEMINI_TTS_API_KEY not found in environment or secrets.")

    async def _run_gemini_websocket():
        client = genai.Client(http_options={"api_version": "v1beta"}, api_key=gemini_key)
        MODEL = "models/gemini-3.5-live-translate-preview"
        CONFIG = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            translation_config=types.TranslationConfig(target_language_code="en"),
        )
        
        pcm_data = bytearray()
        try:
            async with client.aio.live.connect(model=MODEL, config=CONFIG) as session:
                await session.send(input=clean_text, end_of_turn=True)
                async for response in session.receive():
                    if response.data:
                        pcm_data.extend(response.data)
        except Exception as e:
            logger.error(f"Gemini Live API error: {e}")
            raise
            
        with open(pcm_path, "wb") as f:
            f.write(pcm_data)

    asyncio.run(_run_gemini_websocket())

    # Convert PCM to MP3 using FFmpeg (Gemini Live Audio is 24000Hz s16le PCM)
    conv_cmd = ["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", pcm_path, "-codec:a", "libmp3lame", "-qscale:a", "2", audio_path]
    subprocess.run(conv_cmd, capture_output=True, check=True)

    # Clean up raw PCM
    if os.path.exists(pcm_path):
        os.remove(pcm_path)

    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    dur_res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True, timeout=15)
    audio_duration = float(dur_res.stdout.strip())

    words = clean_text.split()
    step = (audio_duration * 0.85) / max(1, len(words))
    word_timings = [{"word": w, "time_seconds": round(0.1 + i * step, 3)} for i, w in enumerate(words)]

    logger.info(f"✅ Gemini Live Audio track generated for Scene {scene_index} ({audio_duration:.2f}s)")
    return audio_path, word_timings, audio_duration


def generate_fish_audio_voice(text, scene_index, arrow_state="arrow_up"):
    """
    Synthesize audio using Fish Audio API as a fallback.
    """
    import os
    import subprocess
    import requests
    import re
    
    logger.info(f"🎙️ Synthesizing voice for Scene {scene_index} using FISH AUDIO Fallback...")
    
    fish_api_key = get_secret("FISH_AUDIO_API_KEY")
    if not fish_api_key:
        raise ValueError("FISH_AUDIO_API_KEY not found.")
        
    audio_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}.mp3")
    clean_text = re.sub(r'<[^>]+>', '', text).strip()
    
    url = "https://api.fish.audio/v1/tts"
    headers = {
        "Authorization": f"Bearer {fish_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "text": clean_text,
        "format": "mp3",
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    
    with open(audio_path, "wb") as f:
        f.write(response.content)
        
    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    dur_res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True, timeout=15)
    audio_duration = float(dur_res.stdout.strip())

    words = clean_text.split()
    step = (audio_duration * 0.85) / max(1, len(words))
    word_timings = [{"word": w, "time_seconds": round(0.1 + i * step, 3)} for i, w in enumerate(words)]
    
    logger.info(f"✅ Fish Audio track generated for Scene {scene_index} ({audio_duration:.2f}s)")
    return audio_path, word_timings, audio_duration


def generate_scene_voice(tts_client, text, scene_index, voice_config_scene=None, arrow_state="arrow_up"):
    """Generate audio using Gemini Live API with Fish Audio fallback."""
    try:
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as exec:
            future = exec.submit(generate_gemini_voice, text, scene_index, arrow_state)
            return future.result(timeout=180.0)
    except Exception as err:
        logger.warning(f"⚠️ Gemini Live Audio TTS failed: {err}. Falling back to Fish Audio...")
        try:
            return generate_fish_audio_voice(text, scene_index, arrow_state)
        except Exception as e2:
            logger.error(f"❌ Fish Audio TTS fallback also failed: {e2}")
            raise RuntimeError(f"Voice generation completely failed. Gemini err: {err}, Fish err: {e2}")

def generate_scene_image(visual_prompt, scene_index, visual_config_scene=None):
    """
    Dynamically generates a high-quality vertical AI image using NVIDIA NIM or Gemini Imagen 3.
    """
    import hashlib
    import io
    import time
    from PIL import Image
    from google import genai
    from google.genai import types
    
    bg_dir = os.path.join(os.getcwd(), "assets", "backgrounds")
    os.makedirs(bg_dir, exist_ok=True)
    
    search_query = visual_prompt
    if "Professional sleek minimalist corporate" not in search_query:
        search_query = (
            f"Professional sleek minimalist corporate 3D illustration, "
            f"deep navy blue and vibrant gold color palette, "
            f"highly recognizable editorial infographic aesthetic, no text, no letters. "
            f"{visual_prompt}"
        )
    
    prompt_hash = hashlib.md5(f"{scene_index}_{search_query}".encode('utf-8')).hexdigest()[:8]
    target_path = os.path.join(bg_dir, f"bg_{scene_index}_{prompt_hash}.jpg")
    
    # ── PRIMARY: NVIDIA NIM ──
    try:
        nvidia_api_key = get_secret("NVIDIA_API_KEY")
    except Exception:
        nvidia_api_key = None
        
    if nvidia_api_key:
        logger.info(f"🎨 Generating image for Scene {scene_index + 1} via NVIDIA NIM...")
        try:
            import requests
            import base64
            invoke_url = "https://ai.api.nvidia.com/v1/genai/stabilityai/stable-diffusion-3-medium"
            headers = {
                "Authorization": f"Bearer {nvidia_api_key}",
                "Accept": "application/json",
            }
            payload = {
                "text_prompts": [{"text": search_query}],
                "cfg_scale": 5,
                "seed": 0,
                "steps": 50
            }
            response = requests.post(invoke_url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            response_body = response.json()
            if "artifacts" in response_body and len(response_body["artifacts"]) > 0:
                image_data = base64.b64decode(response_body["artifacts"][0]["base64"])
                with open(target_path, "wb") as f:
                    f.write(image_data)
                logger.info(f"✅ [NVIDIA NIM] Image for Scene {scene_index + 1} saved → {target_path}")
                return {"type": "image", "path": target_path}
        except Exception as e:
            logger.warning(f"⚠️ NVIDIA API failed for Scene {scene_index + 1}: {e}")

    # ── SECONDARY: FAL AI ──
    logger.warning(f"🔄 NVIDIA failed or not configured. Trying FAL AI fallback for Scene {scene_index + 1}...")
    fal_key = None
    try:
        fal_key = get_secret("FAL_KEY")
    except ValueError:
        pass
        
    if fal_key:
        try:
            import requests
            url = "https://fal.run/fal-ai/fast-sdxl"
            headers = {
                "Authorization": f"Key {fal_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "prompt": search_query,
                "image_size": "portrait_16_9"
            }
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            response_body = response.json()
            if "images" in response_body and len(response_body["images"]) > 0:
                image_url = response_body["images"][0]["url"]
                img_data = requests.get(image_url).content
                with open(target_path, "wb") as f:
                    f.write(img_data)
                logger.info(f"✅ [FAL AI] Image for Scene {scene_index + 1} saved → {target_path}")
                return {"type": "image", "path": target_path}
        except Exception as e:
            logger.warning(f"⚠️ FAL AI failed for Scene {scene_index + 1}: {e}")

    # ── TERTIARY: HUGGING FACE SERVERLESS ──
    logger.warning(f"🔄 FAL AI failed or not configured. Trying Hugging Face Serverless fallback for Scene {scene_index + 1}...")
    hf_api_key = None
    try:
        hf_api_key = get_secret("HF_API_KEY")
    except ValueError:
        pass
            
    if not hf_api_key:
        raise RuntimeError("HF_API_KEY missing, image generation completely failed.")

    import requests
    import time
    
    API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
    headers = {"Authorization": f"Bearer {hf_api_key}"}
    
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            payload = {"inputs": search_query}
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            if response.status_code == 200:
                with open(target_path, "wb") as f:
                    f.write(response.content)
                logger.info(f"✅ [Hugging Face] Image for Scene {scene_index + 1} saved → {target_path}")
                return {"type": "image", "path": target_path}
            else:
                logger.warning(f"⚠️ Hugging Face attempt {attempt}/{max_attempts} failed: {response.text}")
        except Exception as e:
            logger.warning(f"⚠️ Hugging Face attempt {attempt}/{max_attempts} failed for Scene {scene_index + 1}: {e}")
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
    
    import concurrent.futures
    
    visual_prompt = scene.get("visual_prompt", "")
    if visual_config_scene and visual_config_scene.get("enhanced_prompt"):
        visual_prompt = visual_config_scene["enhanced_prompt"]
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        voice_future = executor.submit(
            generate_scene_voice,
            tts_client, scene["narration"], index,
            voice_config_scene=voice_config_scene,
            arrow_state=scene.get("arrow_state", "arrow_up")
        )
        visual_future = executor.submit(
            generate_scene_image,
            visual_prompt, index,
            visual_config_scene=visual_config_scene
        )
        
        audio_path, word_timings, audio_duration = voice_future.result()
        visual_asset = visual_future.result()
    
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
