"""
Fetch 15 high-retention finance-contextual vertical stock video loops (Pexels / Curated HD Stock Video Loops)
for short-form video backgrounds (1080x1920 portrait).

B-roll categories mapped to visual_category tags:
  "vaults"      → gold vault, bank vault, cash counting
  "crowds"      → trading floor, busy market, stock exchange
  "growth"      → green candlestick charts, upward arrows, coins stacking
  "digital"     → blockchain, trading app, screen numbers
  "hands"       → calculator, documents, business meeting
  "paperwork"   → financial headlines, documents, tax forms
"""
import os
import requests
import logging
import urllib.parse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BACKGROUNDS_DIR = os.path.join(os.getcwd(), "assets", "backgrounds")
os.makedirs(BACKGROUNDS_DIR, exist_ok=True)

# ──────────────────────────────────────────────
# FINANCE-CONTEXTUAL B-ROLL QUERIES (replaces "satisfying" videos)
# Grouped by visual_category for scene-aware matching
# ──────────────────────────────────────────────

# Category: vaults (indices 0-1)
# Category: crowds (indices 2-3)
# Category: growth (indices 4-6)
# Category: digital (indices 7-9)
# Category: hands (indices 10-11)
# Category: paperwork (indices 12-14)

QUERIES = [
    # vaults (0-1)
    "gold bars vault close up vertical",
    "bank vault door opening security vertical",
    # crowds (2-3)
    "stock market trading floor aerial vertical",
    "busy city financial district crowd vertical",
    # growth (4-6)
    "financial charts candlestick green red vertical",
    "coins falling stacking slow motion vertical",
    "stock exchange screen numbers scrolling vertical",
    # digital (7-9)
    "digital cryptocurrency blockchain animation vertical",
    "smartphone trading app stock market vertical",
    "world map financial data connections vertical",
    # hands (10-11)
    "business meeting boardroom discussion vertical",
    "money cash counting machine vertical",
    # paperwork (12-14)
    "newspaper financial headlines close up vertical",
    "calculator financial documents tax vertical",
    "aerial city traffic financial district night vertical"
]

# Category-to-index mapping for scene-aware B-roll selection
CATEGORY_INDICES = {
    "vaults":     [0, 1],
    "crowds":     [2, 3],
    "growth":     [4, 5, 6],
    "digital":    [7, 8, 9],
    "hands":      [10, 11],
    "paperwork":  [12, 13, 14],
}

# Direct HD vertical finance/business stock loop URLs (15 Royalty-free open stock loops)
CURATED_DIRECT_LOOPS = [
    # vaults (0-1)
    "https://assets.mixkit.co/videos/preview/mixkit-golden-bars-in-a-safety-box-of-a-bank-6891-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-bank-vault-door-3055-large.mp4",
    # crowds (2-3)
    "https://assets.mixkit.co/videos/preview/mixkit-busy-street-in-the-financial-district-4818-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-aerial-view-of-city-traffic-at-night-11-large.mp4",
    # growth (4-6)
    "https://assets.mixkit.co/videos/preview/mixkit-digital-stock-market-chart-going-up-68486-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-pile-of-gold-coins-2775-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-stock-exchange-trading-screen-numbers-4621-large.mp4",
    # digital (7-9)
    "https://assets.mixkit.co/videos/preview/mixkit-abstract-digital-technology-background-12758-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-hands-using-a-smartphone-in-the-dark-41555-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-digital-world-map-hologram-4791-large.mp4",
    # hands (10-11)
    "https://assets.mixkit.co/videos/preview/mixkit-business-team-at-a-meeting-4832-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-counting-dollar-bills-by-hand-4169-large.mp4",
    # paperwork (12-14)
    "https://assets.mixkit.co/videos/preview/mixkit-close-up-of-newspaper-headlines-4783-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-typing-on-a-calculator-next-to-documents-4821-large.mp4",
    "https://assets.mixkit.co/videos/preview/mixkit-city-skyline-timelapse-at-sunset-4174-large.mp4",
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
            logger.info(f"Using curated HD vertical finance stock loop for {filename}...")
            
        success = download_file(video_url, filepath)
        if not success and idx < len(CURATED_DIRECT_LOOPS):
            download_file(CURATED_DIRECT_LOOPS[idx], filepath)

if __name__ == "__main__":
    download_all_stock_loops()
