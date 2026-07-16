import logging
import os
import glob
from main import load_env_file
from src.agents.manager import ManagerAgent
from src.config import OUTPUT_DIR

# Set up basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def run_test():
    logging.info("Loading environment variables...")
    load_env_file()
    
    logging.info("Initializing Manager Agent...")
    try:
        manager = ManagerAgent()
        logging.info("Starting Multi-Agent Workflow Execution...")
        success = manager.execute_workflow(publish_youtube=False, publish_telegram=False)
        
        if success:
            final_vid = os.path.join(OUTPUT_DIR, "distribution_ready.mp4")
            logging.info(f"Test completed SUCCESSFULLY! Video is ready at {final_vid}")
            
            # Auto-cleanup of intermediate files
            patterns = [
                os.path.join(OUTPUT_DIR, "scene_*"),
                os.path.join(OUTPUT_DIR, "combined_*"),
                os.path.join(OUTPUT_DIR, "video_*"),
                os.path.join(OUTPUT_DIR, "subs.ass"),
                os.path.join(OUTPUT_DIR, "video_list.txt"),
                os.path.join(OUTPUT_DIR, "audio_list.txt")
            ]
            for pattern in patterns:
                for f in glob.glob(pattern):
                    try:
                        os.remove(f)
                    except Exception:
                        pass
            logging.info("Cleaned up intermediate files.")
        else:
            logging.error("Test FAILED during workflow execution.")
            
    except Exception as e:
        logging.error(f"Test crashed: {e}", exc_info=True)

if __name__ == "__main__":
    run_test()
