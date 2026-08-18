"""
src/lip_sync.py
High-Resolution FaceClone AI & Lip-Sync Video Synthesizer Client
Replaces legacy local Wav2Lip processing with cloud rendering.
"""

import os
import time
import base64
import requests
from pathlib import Path

# Configuration (configured via GitHub Secrets or environment variables)
FACECLONE_API_URL = os.getenv(
    "FACECLONE_API_URL",
    "https://ais-dev-ifc4dti3hjchh7dfwfd7s2-490038387281.asia-southeast1.run.app"
)
FACECLONE_API_KEY = os.getenv(
    "FACECLONE_API_KEY",
    "fc_live_9a7d8c6b2e1f40889345217abcdef"
)

def generate_lip_sync_video(
    script_text: str,
    audio_path: str = "scene_kokoro.wav",
    avatar_id: str = "avatar-arunachalam",
    output_path: str = "custom_avatar.mp4",
    resolution: str = "4k",
    model: str = "liveportrait-v2",
    enhancer: str = "codeformer-4k"
) -> str:
    """
    Submits a video rendering job to the FaceClone AI API, polls until completion,
    and saves the resulting synchronized 4K MP4 video artifact.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {FACECLONE_API_KEY}"
    }

    # Encode optional local audio if provided
    audio_b64 = None
    if audio_path and Path(audio_path).exists():
        with open(audio_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    payload = {
        "script": script_text,
        "avatarId": avatar_id,
        "model": model,
        "enhancer": enhancer,
        "resolution": resolution,
        "fps": 30,
        "metadata": {
            "source": "market-debunk-autonomous",
            "audio_file": audio_path
        }
    }

    if audio_b64:
        payload["audio_base64"] = audio_b64

    print(f"🚀 [FaceClone AI] Dispatching render job (Avatar: {avatar_id}, Res: {resolution})...")
    
    # 1. Dispatch Job
    response = requests.post(f"{FACECLONE_API_URL}/api/v1/generate", json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()
    job_id = data["job_id"]
    print(f"📋 [FaceClone AI] Job Queued: {job_id}")

    # 2. Poll for Progress
    poll_endpoint = f"{FACECLONE_API_URL}/api/v1/jobs/{job_id}"
    while True:
        poll_res = requests.get(poll_endpoint, headers=headers).json()
        status = poll_res.get("status")
        progress = poll_res.get("progress", 0)
        stage = poll_res.get("current_stage", "Rendering")

        print(f"⏳ [FaceClone AI] [{progress}%] {stage}")

        if status == "completed":
            download_url = poll_res.get("download_url") or poll_res.get("video_url")
            print(f"✅ [FaceClone AI] Synthesis Complete! Fetching video stream...")
            
            # 3. Download the finished MP4
            if not download_url.startswith("http"):
                download_url = f"{FACECLONE_API_URL}{download_url}"
                
            video_bytes = requests.get(download_url, headers=headers).content
            with open(output_path, "wb") as f:
                f.write(video_bytes)
            
            print(f"💾 [FaceClone AI] Video saved to: {output_path} ({len(video_bytes) // 1024} KB)")
            return output_path

        elif status in ("failed", "cancelled"):
            error_msg = poll_res.get("error", "Unknown error during rendering")
            raise RuntimeError(f"FaceClone rendering failed: {error_msg}")

        time.sleep(2.5)

if __name__ == "__main__":
    # Test run
    test_script = (
        "Market Debunk autonomous broadcast is live. "
        "Analyzing today's liquidity flows and macroeconomic trends."
    )
    generate_lip_sync_video(script_text=test_script)
