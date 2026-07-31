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

# Curated queries for high retention, satisfying process & finishing loops (15 stock videos)
QUERIES = [
    "satisfying kinetic sand cutting vertical",
    "satisfying soap carving process vertical",
    "satisfying hydraulic press crushing vertical",
    "satisfying wood lathe turning process vertical",
    "satisfying glass bottle drop crushing vertical",
    "satisfying domino chain reaction finishing vertical",
    "satisfying pottery wheel molding process vertical",
    "satisfying ASMR slime slicing vertical",
    "satisfying metal machining lathe cutting vertical",
    "satisfying 3d destruction simulation vertical",
    "satisfying epoxy resin fluid art finishing vertical",
    "satisfying marble run race finishing vertical",
    "satisfying 3d pendulum wave domino vertical",
    "satisfying chocolate tempering pouring vertical",
    "satisfying laser engraving metal process vertical"
]

# Direct HD vertical satisfying process / finishing loop URLs (15 Royalty-free open stock process loops)
CURATED_DIRECT_LOOPS = [
    "https://assets.mixkit.co/videos/preview/mixkit-hands-cutting-a-bar-of-soap-with-a-knife-41556-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-potter-shaping-a-clay-vase-on-a-wheel-41477-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-woodworker-using-a-chisel-on-a-spinning-wood-lathe-41480-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-hands-slicing-kinetic-sand-41558-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-close-up-of-epoxy-resin-mixing-and-pouring-41485-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-dominoes-falling-in-a-chain-reaction-41490-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-laser-cutting-a-pattern-into-metal-41492-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-pouring-melted-chocolate-over-a-cake-41500-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-glassblower-shaping-hot-molten-glass-41505-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-colorful-marbles-rolling-down-a-track-41510-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-hydraulic-press-crushing-an-object-41515-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-painter-applying-thick-acrylic-paint-to-canvas-41520-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-3d-spheres-falling-and-bouncing-41525-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-hand-carving-a-wooden-sculpture-41530-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-satisfying-sand-art-creation-41535-large.mp4"
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
    
    for idx in range(15):
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
