"""
src/lip_sync.py
High-Resolution FaceClone AI & Lip-Sync Video Synthesizer Client
Replaces legacy local Wav2Lip processing with cloud rendering.
"""

import os
import time
import base64
import requests
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Configuration
FACECLONE_API_URL = os.getenv("FACECLONE_API_URL", "https://ais-dev-ifc4dti3hjchh7dfwfd7s2-490038387281.asia-southeast1.run.app")
FACECLONE_API_KEY = os.getenv("FACECLONE_API_KEY", "fc_live_9a7d8c6b2e1f40889345217abcdef")

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
    Submits a video rendering job to the FaceClone AI API.
    """
    logger.info(f"🎙️ [FaceClone] Preparing to send audio to FaceClone API ({model} + {enhancer})...")
    
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()
    
    encoded_audio = base64.b64encode(audio_bytes).decode('utf-8')
    
    payload = {
        "avatar_id": avatar_id,
        "script": script_text,
        "audio_base64": encoded_audio,
        "model": model,
        "enhancer": enhancer,
        "resolution": resolution
    }
    
    headers = {
        "Authorization": f"Bearer {FACECLONE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    logger.info(f"🚀 [FaceClone] Dispatching render job to {FACECLONE_API_URL}...")
    
    # 1. Start Job
    endpoint = f"{FACECLONE_API_URL}/v1/render"
    try:
        response = requests.post(endpoint, json=payload, headers=headers)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"❌ [FaceClone] API connection failed: {e}")
        raise RuntimeError(f"FaceClone API failed: {e}")
        
    data = response.json()
    job_id = data.get("job_id")
    
    if not job_id:
        raise RuntimeError(f"FaceClone API returned invalid response (missing job_id): {data}")
        
    logger.info(f"📋 [FaceClone] Job Queued! Job ID: {job_id}")
    
    # 2. Poll for completion
    poll_endpoint = f"{FACECLONE_API_URL}/v1/status/{job_id}"
    while True:
        poll_res = requests.get(poll_endpoint, headers=headers).json()
        status = poll_res.get("status")
        
        logger.info(f"⏳ [FaceClone] Status: {status}")
        
        if status == "completed":
            download_url = poll_res.get("download_url")
            logger.info("✅ [FaceClone] Synthesis Complete! Fetching video stream...")
            
            video_bytes = requests.get(download_url).content
            with open(output_path, "wb") as f:
                f.write(video_bytes)
            
            logger.info(f"💾 [FaceClone] Video saved to: {output_path}")
            return output_path
            
        elif status == "failed":
            error_msg = poll_res.get("error", "Unknown error")
            raise RuntimeError(f"FaceClone rendering failed: {error_msg}")
            
        time.sleep(10)

if __name__ == "__main__":
    pass
