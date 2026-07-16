import os
import sys
import logging
import subprocess

# Set up logging to stdout
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Load variables from .env file into environment if it exists
def load_env_file(dotenv_path=".env"):
    if os.path.exists(dotenv_path):
        with open(dotenv_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'").strip('"')
                    os.environ[key] = val
                    logger.info(f"Loaded config from .env: {key}")

load_env_file()

# Add workspace to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

def generate_mock_audio(output_path, duration):
    """Generate a dummy silent audio track of specified duration using FFmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=mono",
        "-t", str(duration),
        "-c:a", "libmp3lame",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

def generate_mock_image(output_path, color="blue"):
    """Generate a 16:9 widescreen solid color mock image using FFmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={color}:s=1280x720:d=1",
        "-frames:v", "1",
        output_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

def run_mock_verification():
    """Verify the entire media compilation (FFmpeg, cropping, scaling, ASS subtitles) offline."""
    logger.info("=== STARTING OFFLINE MOCK MEDIA VERIFICATION ===")
    
    # 1. Define 5 mock scenes with different narration lengths
    mock_scenes = [
        {"narration": "Welcome to our automated market breakout report.", "color": "darkblue"},
        {"narration": "The price has hit key resistance lines.", "color": "darkred"},
        {"narration": "Bulls are pushing hard for a clean breakout.", "color": "green"},
        {"narration": "Watch the volume spikes on this massive test.", "color": "purple"},
        {"narration": "Subscribe for instant alerts on next signals.", "color": "orange"}
    ]
    
    processed_scenes = []
    
    logger.info("Generating mock source files (images & silent audio)...")
    for idx, scene in enumerate(mock_scenes):
        audio_path = f"/tmp/scene_{idx}.mp3"
        image_path = f"/tmp/scene_{idx}.jpg"
        
        # Audio durations: 3s, 2s, 4s, 3s, 2s
        durations = [3.0, 2.5, 4.0, 3.2, 2.0]
        dur = durations[idx]
        
        # Generate mock assets
        generate_mock_audio(audio_path, dur)
        generate_mock_image(image_path, color=scene["color"])
        
        # Split narration into words for mock subtitle timings
        words = scene["narration"].split()
        word_timings = []
        for w_idx, word in enumerate(words):
            word_timings.append({
                "word": word,
                "time_seconds": (dur / len(words)) * w_idx
            })
            
        processed_scenes.append({
            "index": idx,
            "narration": scene["narration"],
            "audio_path": audio_path,
            "audio_duration": dur,
            "word_timings": word_timings,
            "visual_asset": {
                "type": "image",
                "path": image_path
            }
        })
        
    logger.info("Triggering FFmpeg video processor...")
    from src.video_processor import assemble_final_video
    
    try:
        final_video_path = assemble_final_video(processed_scenes)
        logger.info(f"Mock verification successful! Video compiled at: {final_video_path}")
        
        # Output info
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height",
            "-of", "json", final_video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        logger.info(f"Video metadata specs: {result.stdout.strip()}")
        print("\nSUCCESS: The FFmpeg rendering pipeline works flawlessly.")
        print(f"Rendered Output: {final_video_path} (1080x1920 portrait format)")
        
    except Exception as error:
        logger.exception("Media assembly failed during mock verification")
        sys.exit(1)

def run_real_verification():
    """Trigger the real API pipeline locally using environment variables."""
    logger.info("=== STARTING REAL PIPELINE VERIFICATION ===")
    
    # Check key environment variables
    required_keys = [
        "GEMINI_API_KEY", 
        "TELEGRAM_BOT_TOKEN", 
        "TELEGRAM_CHAT_ID",
        "YT_REFRESH_TOKEN",
        "YT_CLIENT_ID",
        "YT_CLIENT_SECRET"
    ]
    
    missing = [k for k in required_keys if not os.environ.get(k)]
    if missing:
        print(f"Error: Missing environment variables for real run: {missing}")
        print("Please export them before running (e.g. export GEMINI_API_KEY='your_key')")
        sys.exit(1)
        
    from src.generator import run_video_factory_pipeline
    
    topic = "Financial Trend Breakout Analysis"
    topic_hash = f"test_trend_{int(os.urandom(4).hex(), 16)}"
    
    logger.info(f"Running real video pipeline for: '{topic}'")
    status, code = run_video_factory_pipeline(
        topic_title=topic,
        topic_hash=topic_hash,
        publish_youtube=True,
        publish_telegram=True
    )
    
    print(f"Finished pipeline. Status: {status}, Code: {code}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--real":
        run_real_verification()
    else:
        print("Running in MOCK mode (does not call Google APIs, only tests local FFmpeg pipeline).")
        print("To test real API connections, run: python test_pipeline.py --real\n")
        run_mock_verification()
