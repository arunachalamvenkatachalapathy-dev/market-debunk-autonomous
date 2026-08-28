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
from src.limiter import rate_limiter

OUTPUT_DIR

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

    keys_str = os.environ.get("LLM_API_KEYS") or get_secret("LLM_API_KEYS") or ""
    keys_list = [k.strip() for k in keys_str.split(",") if k.strip()]
    import random
    gemini_key = random.choice(keys_list) if keys_list else None
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
                    server_content = getattr(response, 'server_content', None)
                    if server_content is not None and getattr(server_content, 'turn_complete', False):
                        break
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


def generate_kokoro_voice(text, scene_index):
    """
    Synthesize audio using Kokoro (via FAL AI) as a tertiary fallback.
    """
    import os
    import subprocess
    import requests
    import re
    
    logger.info(f"🎙️ Synthesizing voice for Scene {scene_index} using KOKORO (FAL AI) Fallback...")
    
    fal_key = get_secret("FAL_KEY")
    if not fal_key:
        raise ValueError("FAL_KEY not found for Kokoro TTS.")
        
    audio_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}.mp3")
    clean_text = re.sub(r'<[^>]+>', '', text).strip()
    
    url = "https://fal.run/fal-ai/kokoro"
    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "prompt": clean_text,
        "voice": "am_adam" # standard male energetic voice
    }
    
    response = requests.post(url, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    response_body = response.json()
    
    if "audio" in response_body and "url" in response_body["audio"]:
        audio_url = response_body["audio"]["url"]
        audio_data = requests.get(audio_url).content
        
        wav_path = audio_path.replace(".mp3", ".wav")
        with open(wav_path, "wb") as f:
            f.write(audio_data)
            
        # Convert WAV to MP3 to ensure FFmpeg concat doesn't crash later
        conv_cmd = ["ffmpeg", "-y", "-i", wav_path, "-codec:a", "libmp3lame", "-qscale:a", "2", audio_path]
        subprocess.run(conv_cmd, capture_output=True, check=True)
        
        if os.path.exists(wav_path):
            os.remove(wav_path)
    else:
        raise RuntimeError("Kokoro FAL AI response missing audio URL.")
        
    probe_cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    dur_res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True, timeout=15)
    audio_duration = float(dur_res.stdout.strip())

    words = clean_text.split()
    step = (audio_duration * 0.85) / max(1, len(words))
    word_timings = [{"word": w, "time_seconds": round(0.1 + i * step, 3)} for i, w in enumerate(words)]
    
    logger.info(f"✅ Kokoro track generated for Scene {scene_index} ({audio_duration:.2f}s)")
    return audio_path, word_timings, audio_duration


def generate_scene_voice(tts_client, text, scene_index, voice_config_scene=None, arrow_state="arrow_up"):
    import os, subprocess, re, requests, sys
    import logging
    logger = logging.getLogger(__name__)
    
    audio_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}.mp3")
    clean_text = re.sub(r'<[^>]+>', '', text).strip()
    
    # Try Fish Audio first
    fish_api_key = os.environ.get("FISH_AUDIO_API_KEY")
    if fish_api_key:
        logger.info(f"?? Synthesizing voice for Scene {scene_index} using Fish Audio...")
        try:
            url = "https://api.fish.audio/v1/tts"
            headers = {
                "Authorization": f"Bearer {fish_api_key}",
                "Content-Type": "application/json"
            }
            # Using a known reference_id for a good voice if available, else omit
            payload = {
                "text": clean_text,
                "format": "mp3",
                "reference_id": "8064972e6b20469b8bf1e3c8800045f2" # Default to this reference from docs
            }
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 200:
                with open(audio_path, "wb") as f:
                    f.write(resp.content)
            else:
                raise Exception(f"Fish Audio failed: {resp.status_code} {resp.text}")
        except Exception as e:
            logger.warning(f"Fish Audio failed ({e}). Falling back to Edge-TTS...")
            fish_api_key = None # trigger fallback
            
    # Edge-TTS Fallback
    if not fish_api_key or not os.path.exists(audio_path):
        logger.info(f"??? Synthesizing voice for Scene {scene_index} using EDGE-TTS fallback (Andrew)...")
        voice = "en-US-AndrewMultilingualNeural"
        subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voice, "--text", clean_text, "--write-media", audio_path], check=True)

    probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path]
    dur_res = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
    audio_duration = float(dur_res.stdout.strip())
    words = clean_text.split()
    step = (audio_duration * 0.85) / max(1, len(words))
    word_timings = [{"word": w, "time_seconds": round(0.1 + i * step, 3)} for i, w in enumerate(words)]
    return audio_path, word_timings, audio_duration



def fetch_pexels_video(query, scene_index, min_duration=3):
    import os
    import requests
    import logging
    import random
    import urllib.parse
    logger = logging.getLogger(__name__)
    
    OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
    target_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}.mp4")
    
    api_key = os.environ.get("PEXELS_API_KEY")
    if not api_key:
        logger.warning("No PEXELS_API_KEY found, falling back to Pollinations image")
        return generate_scene_image(query, scene_index)
        
    # Take first 2-3 words of prompt for better search results
    import re as regex
    clean_query = " ".join(regex.sub(r'[^a-zA-Z0-9 ]', '', query).split()[:3])
    url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(clean_query)}&orientation=portrait&size=medium&per_page=15"
    
    try:
        headers = {"Authorization": api_key}
        res = requests.get(url, headers=headers, timeout=10)
        res.raise_for_status()
        data = res.json()
        
        videos = [v for v in data.get("videos", []) if v.get("duration", 0) >= min_duration]
        if not videos:
            logger.warning(f"No valid Pexels videos found for '{clean_query}'. Falling back to Pollinations image.")
            return generate_scene_image(query, scene_index)
            
        selected_video = random.choice(videos)
        video_files = selected_video.get("video_files", [])
        
        # Prefer HD vertical
        hd_files = [f for f in video_files if f.get("quality") == "hd" and f.get("width", 0) < f.get("height", 0)]
        if hd_files:
            video_url = hd_files[0].get("link")
        else:
            video_url = video_files[0].get("link")
            
        # Download video
        logger.info(f"Downloading Pexels video for scene {scene_index}...")
        vid_res = requests.get(video_url, stream=True, timeout=30)
        vid_res.raise_for_status()
        with open(target_path, 'wb') as f:
            for chunk in vid_res.iter_content(chunk_size=8192):
                f.write(chunk)
        return target_path
    except Exception as e:
        logger.error(f"Pexels fetch failed: {e}. Falling back to Pollinations.")
        return generate_scene_image(query, scene_index)

def generate_scene_image(visual_prompt, scene_index, visual_config_scene=None):

    import urllib.parse
    import requests
    import os
    import time
    import logging
    logger = logging.getLogger(__name__)
    
    prompt = visual_prompt
    if visual_config_scene and 'style' in visual_config_scene:
        prompt += f", {visual_config_scene['style']}"
        
    encoded_prompt = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1080&height=1920&nologo=true"
    
    OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
    target_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}.jpg")
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.info(f"??? Requesting image for Scene {scene_index} (Attempt {attempt+1})")
            rate_limiter.wait()
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            with open(target_path, "wb") as f:
                f.write(resp.content)
            logger.info(f"??? Image saved for Scene {scene_index}")
            return {"type": "image", "path": target_path}
        except Exception as e:
            logger.warning(f"Pollinations AI failed: {e}. Retrying in 5s...")
            time.sleep(5)
            
    # Fallback if all retries fail
    logger.error("All retries failed for Pollinations. Using dummy image.")
    return {"type": "image", "path": r'C:/Users/NALINI ARUN/.gemini/antigravity/brain/b92be3c9-3963-4f83-9a08-0244316c2cf0/.user_uploaded/media__1785725221688.png'}

def process_scene_assets(tts_client, scene, idx, voice_config=None, visual_config=None):
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f'Processing assets for scene {idx}')
    
    text = scene.get('narration', scene.get('text', ''))
    visual_prompt = scene.get('visual_prompt', '')
    
    vc = voice_config[idx] if voice_config and idx < len(voice_config) else None
    audio_path, word_timings, audio_duration = generate_scene_voice(tts_client, text, idx, voice_config_scene=vc)
    
    vic = visual_config[idx] if visual_config and idx < len(visual_config) else None
    
    # MPT Methodology: Try Pexels Video first
    image_path = fetch_pexels_video(visual_prompt, idx)

    
    scene['audio_path'] = audio_path
    scene['word_timings'] = word_timings
    scene['audio_duration'] = audio_duration
    scene['visual_asset'] = image_path
    scene['index'] = idx
    return scene


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
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
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
