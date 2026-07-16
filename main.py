import os
import logging
from flask import Flask, request, jsonify
from src.config import OUTPUT_DIR

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
        print(f"Loaded config from {dotenv_path}")

def cleanup_tmp():
    """Remove all pipeline-generated temp files from OUTPUT_DIR to prevent disk exhaustion on Cloud Run."""
    import glob
    patterns = [
        os.path.join(OUTPUT_DIR, "scene_*"), 
        os.path.join(OUTPUT_DIR, "combined_*"), 
        os.path.join(OUTPUT_DIR, "video_*"), 
        os.path.join(OUTPUT_DIR, "subs.ass"), 
        os.path.join(OUTPUT_DIR, "distribution_ready.mp4"), 
        os.path.join(OUTPUT_DIR, "video_list.txt"), 
        os.path.join(OUTPUT_DIR, "audio_list.txt"), 
        os.path.join(OUTPUT_DIR, "evaluator_report.json")
    ]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except Exception:
                pass

load_env_file()

# Pipeline orchestrated via Agent Manager now

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

app = Flask(__name__)

@app.route("/", methods=["GET"])
def health_check():
    """Simple status endpoint for Cloud Run container probing."""
    return "Autonomous Short-Form Video Pipeline Service is Online. (PE-AI + Evaluator Gates v2)", 200

@app.route("/report", methods=["GET"])
def get_report():
    """Serve the latest Evaluator Report Card as JSON."""
    import json as _json
    report_path = os.path.join(OUTPUT_DIR, "evaluator_report.json")
    if os.path.exists(report_path):
        with open(report_path, "r") as f:
            return jsonify(_json.load(f)), 200
    return jsonify({"error": "No report available. Run the pipeline first."}), 404

@app.route("/run", methods=["POST"])
def run_pipeline():
    """Trigger the short-form video generation and publication pipeline."""
    # Clean OUTPUT_DIR from any prior run's leftover files
    cleanup_tmp()
    try:
        # Get optional overriding parameters from trigger payload
        payload = request.get_json(silent=True) or {}
        topic_title = payload.get("topic_title", "Technical Breakout Across Essential Resistance Lines")
        topic_hash = payload.get("topic_hash", "fin_signal_breakout_2026")
        publish_youtube = payload.get("publish_youtube", True)
        publish_telegram = payload.get("publish_telegram", True)

        logging.info(f"Incoming trigger. Using Multi-Agent Orchestration workflow.")
        
        from src.agents.manager import ManagerAgent
        manager = ManagerAgent()
        success = manager.execute_workflow(
            publish_youtube=publish_youtube,
            publish_telegram=publish_telegram,
            override_topic=topic_title
        )
        
        if success:
            return jsonify({"status": "Success"}), 200
        else:
            return jsonify({"status": "Failed"}), 500
    except Exception as error:
        import traceback
        logging.error("Exception in /run:")
        traceback.print_exc()
        return jsonify({"error": str(error)}), 500
    finally:
        # Always clean OUTPUT_DIR after each run regardless of success or failure
        cleanup_tmp()

if __name__ == "__main__":
    # Local execution configuration
    port = int(os.environ.get("PORT", 8080))
    logging.info(f"Starting local server on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
