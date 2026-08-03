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

def check_daily_quota_limit(max_daily_minutes=35.0):
    """
    Checks total GitHub Actions build minutes used today for this repository.
    If today's total build minutes >= max_daily_minutes, skips execution gracefully.
    """
    import requests
    from datetime import datetime, timezone

    repo = os.environ.get("GITHUB_REPOSITORY")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GITHUB_ACTION_TOKEN")

    if not repo or not token:
        logger.info("ℹ️ Local/non-CI run detected or missing GITHUB_TOKEN. Skipping daily quota check.")
        return True

    try:
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        url = f"https://api.github.com/repos/{repo}/actions/runs?created={today_str}&per_page=100"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json"
        }
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            runs = res.json().get("workflow_runs", [])
            total_seconds = 0
            current_run_id = str(os.environ.get("GITHUB_RUN_ID", ""))

            for r in runs:
                run_id = str(r.get("id", ""))
                # Only count earlier completed runs today (exclude current active run)
                if run_id != current_run_id and r.get("status") == "completed":
                    created_at = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                    updated_at = datetime.fromisoformat(r["updated_at"].replace("Z", "+00:00"))
                    duration_sec = (updated_at - created_at).total_seconds()
                    total_seconds += max(0, duration_sec)

            total_minutes = total_seconds / 60.0
            logger.info(f"📊 Today's GitHub Actions build time so far: {total_minutes:.1f} / {max_daily_minutes} minutes")

            if total_minutes >= max_daily_minutes:
                logger.warning(
                    f"⚠️ Daily quota limit reached ({total_minutes:.1f} mins >= {max_daily_minutes} mins). "
                    "Skipping new video generation to protect monthly GitHub Actions budget."
                )
                return False
    except Exception as err:
        logger.warning(f"⚠️ Could not check daily GitHub Actions quota: {err}. Proceeding with run.")

    return True


def run_production():
    """
    Production entry point for the GitHub Actions pipeline.
    This runs the full workflow and intentionally ENABLES publishing.
    """
    logger.info("Starting Autonomous Production Pipeline...")

    # Check 35-minute daily build time limit before starting
    if not check_daily_quota_limit(max_daily_minutes=35.0):
        logger.info("Daily quota cap reached. Exiting gracefully without error.")
        sys.exit(0)
    
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
