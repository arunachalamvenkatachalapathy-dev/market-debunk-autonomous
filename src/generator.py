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
from google.cloud import secretmanager
from google.cloud import firestore
from google.cloud import texttospeech
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


def generate_scene_voice(tts_client, text, scene_index, voice_config_scene=None, arrow_state="arrow_up"):
    """Generate audio and word-level timing offsets using edge-tts."""
    import subprocess
    import ast
    
    audio_path = os.path.join(OUTPUT_DIR, f"scene_{scene_index}.mp3")
    
    # Red Arrow (arrow_down) asks questions -> Natural Male Voice (GuyNeural)
    # Green Arrow (arrow_up) answers -> Natural Female Voice (NeerjaNeural)
    voice_name = "en-US-GuyNeural" if arrow_state == "arrow_down" else "en-IN-NeerjaNeural"
    
    try:
        logger.info(f"Synthesizing voice for Scene {scene_index} (Arrow: {arrow_state}) using {voice_name} at +30% speed...")
        import time
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                result = subprocess.run(
                    ["python", "-m", "edge_tts", "--voice", voice_name, "--rate", "+30%", "--text", text, "--write-media", audio_path],
                    capture_output=True, text=True, check=True
                )
                break
            except subprocess.CalledProcessError as e:
                logger.warning(f"edge-tts attempt {attempt} failed: {e.stderr}")
                if attempt == max_retries:
                    raise RuntimeError(f"Text-to-Speech synthesis failed: {e.stderr}")
                time.sleep(2)
        
        # Parse the JSON metadata for word boundaries
        word_timings = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") == "WordBoundary":
                    # edge-tts offsets are in 100-nanosecond units. Convert to seconds.
                    time_seconds = data["offset"] / 10_000_000.0
                    word_timings.append({
                        "word": data["text"],
                        "time_seconds": time_seconds
                    })
            except Exception as e:
                pass
                
        if not word_timings:
            # Fallback if metadata fails
            words = text.split()
            word_timings = [{"word": w, "time_seconds": i * 0.4} for i, w in enumerate(words)]
            
        logger.info(f"Generated voice track for Scene {scene_index}.")
        return audio_path, word_timings
        
    except RuntimeError as e:
        logger.error(str(e))
        raise

def generate_scene_image(visual_prompt, scene_index, visual_config_scene=None):
    """
    Selects one of the 10 curated hypnotic looping background MP4 videos for high retention.
    Scraps scene-by-scene AI image generation and B-roll.
    """
    import random
    import glob
    
    bg_dir = os.path.join(os.getcwd(), "assets", "backgrounds")
    os.makedirs(bg_dir, exist_ok=True)
    
    # Ensure 10 background loop videos are available
    bg_files = sorted(glob.glob(os.path.join(bg_dir, "bg_*.mp4")))
    if len(bg_files) < 10:
        logger.info("Initializing 10 hypnotic looping background videos...")
        try:
            from scripts.download_stock_loops import download_all_stock_loops
            download_all_stock_loops()
            bg_files = sorted(glob.glob(os.path.join(bg_dir, "bg_*.mp4")))
        except Exception as e:
            logger.warning(f"Stock loop downloader warning: {e}")
            bg_files = sorted(glob.glob(os.path.join(bg_dir, "bg_*.mp4")))

    if bg_files:
        # Pick background based on scene_index or random choice from set of 10
        selected_bg = bg_files[scene_index % len(bg_files)]
        logger.info(f"🎬 HYPNOTIC BACKGROUND: Selected {os.path.basename(selected_bg)} for Scene {scene_index}")
        return {"type": "video", "path": selected_bg}
    else:
        logger.warning(f"⚠️ Falling back to default background asset for Scene {scene_index}")
        fallback_path = os.path.join(os.getcwd(), "assets", "fallback.png")
        return {"type": "image", "path": fallback_path}


def process_scene_assets(tts_client, scene, index, voice_config=None, visual_config=None):
    """
    Fetch voice, word marks, and visual assets for a single scene.
    Accepts PE-generated configs for both voice and visuals.
    """
    logger.info(f"=== Processing Scene {index} ===")
    
    # Get PE configs for this scene
    voice_config_scene = None
    visual_config_scene = None
    
    if voice_config:
        voice_scenes = voice_config.get("scenes", [])
        for vs in voice_scenes:
            if vs.get("scene_number") == index + 1:  # 1-indexed
                voice_config_scene = vs
                break
    
    if visual_config:
        visual_scenes = visual_config.get("scenes", [])
        for vs in visual_scenes:
            if vs.get("scene_number") == index + 1:  # 1-indexed
                visual_config_scene = vs
                break
    
    # 1. Generate Voice with PE config
    audio_path, word_timings = generate_scene_voice(
        tts_client, scene["narration"], index,
        voice_config_scene=voice_config_scene,
        arrow_state=scene.get("arrow_state", "arrow_up")
    )
    
    # 2. Generate Image with PE config
    visual_prompt = scene.get("visual_prompt", "")
    if visual_config_scene and visual_config_scene.get("enhanced_prompt"):
        visual_prompt = visual_config_scene["enhanced_prompt"]
    
    visual_asset = generate_scene_image(
        visual_prompt, index,
        visual_config_scene=visual_config_scene
    )
    
    # Get emphasis words from PE voice config
    emphasis_words = []
    if voice_config_scene:
        emphasis_words = voice_config_scene.get("emphasis_words", [])
    
    return {
        "index": index,
        "narration": scene["narration"],
        "arrow_state": scene.get("arrow_state", "arrow_up"),
        "audio_path": audio_path,
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
                
        # Sort scenes by index to preserve chronological order
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
