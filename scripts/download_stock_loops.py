"""
Fetch 10 high-retention, satisfying vertical stock video loops (Pexels / Curated HD Stock Video Loops)
for short-form video backgrounds (1080x1920 portrait).
"""
import os
import requests
import logging
import urllib.parse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKGROUNDS_DIR = os.path.join(os.getcwd(), "assets", "backgrounds")
os.makedirs(BACKGROUNDS_DIR, exist_ok=True)

# Curated queries for high retention, satisfying vertical background loops
QUERIES = [
    "satisfying 3d loop",
    "abstract neon motion",
    "gta gameplay vertical",
    "kinetic sand liquid flow",
    "space tunnel motion",
    "cyberpunk grid loop",
    "gold particle vortex",
    "dark emerald fluid",
    "geometric polygon tunnel",
    "sunset pastel liquid"
]

# Direct HD vertical stock loop fallback URLs (Royalty-free open stock loops)
CURATED_DIRECT_LOOPS = [
    "https://assets.mixkit.co/videos/preview/mixkit-abstract-fast-line-lights-background-40742-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-vertical-video-of-a-laser-tunnel-in-a-dark-space-42686-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-fluid-abstract-motion-in-purple-and-blue-tones-40748-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-vertical-neon-lights-in-a-dark-tunnel-42687-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-waves-of-abstract-gold-and-black-liquid-40743-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-vertical-video-of-glowing-digital-particles-42685-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-abstract-tunnel-with-blue-and-purple-lights-40744-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-vertical-video-of-cyberpunk-style-neon-lines-42688-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-abstract-golden-particle-waves-40746-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-vertical-motion-of-colorful-light-trails-42689-large.mp4"
]

def download_file(url, target_path):
    try:
        response = requests.get(url, stream=True, timeout=30)
        if response.status_code == 200:
            with open(target_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024*1024):
                    if chunk:
                        f.write(chunk)
            logger.info(f"✅ Successfully downloaded {os.path.basename(target_path)} ({os.path.getsize(target_path)} bytes)")
            return True
    except Exception as e:
        logger.warning(f"Download failed for {url}: {e}")
    return False

def fetch_pexels_video(query, pexels_key):
    try:
        headers = {"Authorization": pexels_key}
        url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&per_page=5&orientation=portrait"
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            videos = res.json().get("videos", [])
            for v in videos:
                for vf in v.get("video_files", []):
                    if vf.get("width", 0) < vf.get("height", 0) and vf.get("link"):  # Vertical
                        return vf["link"]
    except Exception as e:
        logger.warning(f"Pexels Video Search error for '{query}': {e}")
    return None

def download_all_stock_loops():
    pexels_key = os.getenv("PEXELS_API_KEY")
    
    for idx in range(10):
        filename = f"bg_{idx+1:02d}.mp4"
        filepath = os.path.join(BACKGROUNDS_DIR, filename)
        
        if os.path.exists(filepath) and os.path.getsize(filepath) > 100000:
            logger.info(f"Background {filename} already exists ({os.path.getsize(filepath)} bytes).")
            continue
            
        video_url = None
        if pexels_key:
            logger.info(f"Searching Pexels Video API for '{QUERIES[idx]}'...")
            video_url = fetch_pexels_video(QUERIES[idx], pexels_key)
            
        if not video_url:
            video_url = CURATED_DIRECT_LOOPS[idx % len(CURATED_DIRECT_LOOPS)]
            logger.info(f"Using curated HD vertical stock loop for {filename}...")
            
        success = download_file(video_url, filepath)
        if not success and idx < len(CURATED_DIRECT_LOOPS):
            download_file(CURATED_DIRECT_LOOPS[idx], filepath)

if __name__ == "__main__":
    download_all_stock_loops()
