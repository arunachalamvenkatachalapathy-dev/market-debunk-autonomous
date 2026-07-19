import os
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load local environment variables (if running locally)
if os.path.exists(".env"):
    load_dotenv()
    logger.info("Loaded config from .env")

from src.agents.manager import ManagerAgent
from main import cleanup_tmp

def run_production():
    """
    Production entry point for the GitHub Actions pipeline.
    This runs the full workflow and intentionally ENABLES publishing.
    """
    logger.info("Starting Autonomous Production Pipeline...")
    
    # Clean any leftover files just in case
    cleanup_tmp()
    
    manager = ManagerAgent()
    
    # We turn ON publishing for production deployment.
    # The workflow requires LLM_API_KEY, YOUTUBE_CLIENT_SECRET, TELEGRAM_BOT_TOKEN etc. to be set.
    # Ensure override_topic is None so it fetches fresh RSS topics!
    success = manager.execute_workflow(
        publish_youtube=True,
        publish_telegram=True,
        override_topic=None
    )
    
    if success:
        logger.info("Production Pipeline completed successfully!")
        sys.exit(0)
    else:
        logger.error("Production Pipeline FAILED during workflow execution.")
        sys.exit(1)

if __name__ == "__main__":
    run_production()
