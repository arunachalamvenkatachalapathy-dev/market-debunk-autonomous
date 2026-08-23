"""
src/lip_sync.py
High-Resolution FaceClone AI & Lip-Sync Video Synthesizer Client
Replaces legacy local Wav2Lip processing with Fal.ai SadTalker cloud rendering.
"""

import os
import time
import base64
import requests
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Configuration
FAL_KEY = os.getenv("FAL_KEY")

def generate_lip_sync_video(
    script_text: str,
    audio_path: str = "scene_kokoro.wav",
    avatar_id: str = "avatar-arunachalam",
    output_path: str = "custom_avatar.mp4",
    resolution: str = "1080p",
    model: str = "wav2lip-hd",
    enhancer: str = "gfpgan-v1.4"
) -> str:
    """
    Submits a video rendering job to Fal.ai (SadTalker).
    """
    if not FAL_KEY:
        raise RuntimeError("FAL_KEY environment variable is not set. Please add it to your GitHub Secrets.")

    logger.info(f"🎙️ [Fal.ai] Preparing to send audio to Fal.ai SadTalker...")
    
    # Read audio and encode to base64 data URI
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    encoded_audio = base64.b64encode(audio_bytes).decode('utf-8')
    audio_data_uri = f"data:audio/wav;base64,{encoded_audio}"
    
    # Read source avatar image
    avatar_path = os.path.join(os.getcwd(), "assets", "host_original.png")
    if not os.path.exists(avatar_path):
        raise FileNotFoundError(f"Avatar image not found at {avatar_path}")
        
    with open(avatar_path, "rb") as f:
        image_bytes = f.read()
    encoded_image = base64.b64encode(image_bytes).decode('utf-8')
    image_data_uri = f"data:image/png;base64,{encoded_image}"
    
    payload = {
        "source_image_url": image_data_uri,
        "driven_audio_url": audio_data_uri,
        "enhancer": "gfpgan" if "gfpgan" in enhancer.lower() else "RestoreFormer",
        "preprocess": "crop", # 'crop', 'resize', 'full', 'extcrop', 'extfull'
        "still": True # True to reduce head motion
    }
    
    headers = {
        "Authorization": f"Key {FAL_KEY}",
        "Content-Type": "application/json"
    }
    
    logger.info(f"🚀 [Fal.ai] Dispatching render job to Fal.ai queue...")
    
    # 1. Start Job
    endpoint = "https://queue.fal.run/fal-ai/sadtalker"
    try:
        response = requests.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"❌ [Fal.ai] API connection failed: {e}")
        if hasattr(e, 'response') and e.response is not None:
             logger.error(f"Response: {e.response.text}")
        raise RuntimeError(f"Fal.ai API failed: {e}")
        
    data = response.json()
    request_id = data.get("request_id")
    
    if not request_id:
        raise RuntimeError(f"Fal.ai API returned invalid response (missing request_id): {data}")
        
    logger.info(f"📋 [Fal.ai] Job Queued! Request ID: {request_id}")
    
    # 2. Poll for completion
    poll_endpoint = f"https://queue.fal.run/fal-ai/sadtalker/requests/{request_id}"
    while True:
        poll_res = requests.get(poll_endpoint, headers=headers).json()
        status = poll_res.get("status")
        
        logger.info(f"⏳ [Fal.ai] Status: {status}")
        
        if status == "COMPLETED":
            video_url = poll_res.get("video", {}).get("url")
            if not video_url:
                raise RuntimeError("Fal.ai completed but returned no video URL.")
                
            logger.info("✅ [Fal.ai] Synthesis Complete! Fetching video stream...")
            
            video_bytes = requests.get(video_url).content
            with open(output_path, "wb") as f:
                f.write(video_bytes)
            
            logger.info(f"💾 [Fal.ai] Video saved to: {output_path}")
            return output_path
            
        elif status == "FAILED":
            error_msg = poll_res.get("error", "Unknown error")
            raise RuntimeError(f"Fal.ai rendering failed: {error_msg}")
            
        time.sleep(5)

if __name__ == "__main__":
    pass
