import os
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

AUDIO_DIR = os.path.join(os.getcwd(), "assets", "audio")
BGM_DIR = os.path.join(AUDIO_DIR, "bgm")
SFX_DIR = os.path.join(AUDIO_DIR, "sfx")

os.makedirs(BGM_DIR, exist_ok=True)
os.makedirs(SFX_DIR, exist_ok=True)

# 1. The Weeknd - Timeless (Instrumental)
# 2. Death of Bluebird (Instrumental) 
# 3. Indila - Love Story (Instrumental)
# 4. Dramamine - Flawed Mangoes

TRACKS = {
    "bgm_timeless": "ytsearch1:the weeknd timeless instrumental",
    "bgm_bluebird": "ytsearch1:death of bluebird instrumental",
    "bgm_lovestory": "ytsearch1:indila love story instrumental",
    "bgm_dramamine": "ytsearch1:flawed mangoes dramamine",
}

SFX = {
    "sfx_riser": "ytsearch1:cinematic tension riser sound effect no copyright",
    "sfx_click": "ytsearch1:crisp mouse click sound effect high quality",
    "sfx_whoosh": "ytsearch1:cinematic whoosh transition sound effect premium",
    "sfx_gears": "ytsearch1:mechanical gears turning clicking sound effect",
}

def download_audio(name, query, out_dir):
    out_path = os.path.join(out_dir, f"{name}.mp3")
    if os.path.exists(out_path):
        logger.info(f"Already exists: {out_path}")
        return True
    
    logger.info(f"Downloading: {name} ...")
    cmd = [
        "python", "-m", "yt_dlp",
        "-x", "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", out_path,
        query
    ]
    try:
        subprocess.run(cmd, check=True)
        logger.info(f"Successfully downloaded {name}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to download {name}: {e}. Trying fallback...")
        
        # Check if we already have this file but in webm format
        fallback_webm = os.path.join(out_dir, f"{name}.webm")
        if os.path.exists(fallback_webm):
            logger.info(f"Using existing .webm fallback for {name}")
            dst = out_path.replace('.mp3', '.webm')
            if fallback_webm != dst:
                import shutil
                shutil.copy(fallback_webm, dst)
            return True
            
        # Generic fallback
        import glob
        existing_mp3s = glob.glob(os.path.join(out_dir, "*.mp3"))
        existing_webms = glob.glob(os.path.join(out_dir, "*.webm"))
        
        if existing_mp3s:
            dst = out_path
            if existing_mp3s[0] != dst:
                import shutil
                shutil.copy(existing_mp3s[0], dst)
            logger.info(f"Used generic .mp3 fallback for {name}")
            return True
        elif existing_webms:
            dst = out_path.replace('.mp3', '.webm')
            if existing_webms[0] != dst:
                import shutil
                shutil.copy(existing_webms[0], dst)
            logger.info(f"Used generic .webm fallback for {name}")
            return True
            
        logger.warning(f"No fallback found for {name}. Proceeding without it.")
        return False

def main():
    logger.info("Downloading premium BGM tracks...")
    for name, query in TRACKS.items():
        download_audio(name, query, BGM_DIR)
        
    logger.info("Downloading premium SFX...")
    for name, query in SFX.items():
        download_audio(name, query, SFX_DIR)

if __name__ == "__main__":
    main()
