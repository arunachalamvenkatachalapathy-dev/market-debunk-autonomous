import logging
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from src.generator import get_secret

# Configure logging
logger = logging.getLogger(__name__)

def upload_to_youtube(video_path, title, description, tags, category_id="27"):
    """Upload video to YouTube channels as a Short using OAuth2 refresh tokens."""
    try:
        # Fetch tokens from Secret Manager
        refresh_token = get_secret("YT_REFRESH_TOKEN")
        client_id = get_secret("YT_CLIENT_ID")
        client_secret = get_secret("YT_CLIENT_SECRET")
        
        # Build OAuth2 Credentials
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret
        )
        
        youtube_service = build("youtube", "v3", credentials=creds)
        
        # Construct metadata
        body = {
            "snippet": {
                "title": f"{title[:50]} #Shorts",
                "description": description[:5000],
                "tags": tags[:15],
                "categoryId": category_id
            },
            "status": {
                "privacyStatus": "public"  # Short-form video should be public
            }
        }
        
        logger.info("Starting YouTube upload stream...")
        media = MediaFileUpload(video_path, chunksize=1024*1024, resumable=True, mimeType="video/mp4")
        
        request = youtube_service.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"YouTube Upload progress: {int(status.progress() * 100)}%")
                
        video_id = response.get("id")
        logger.info(f"YouTube video published successfully. Video ID: {video_id}")
        return {"success": True, "video_id": video_id}
        
    except Exception as error:
        logger.error(f"YouTube Upload Failed: {error}")
        return {"success": False, "error": str(error)}

def upload_to_telegram(video_path, caption):
    """Upload video directly to a Telegram Channel or Group via Bot API."""
    try:
        token = get_secret("TELEGRAM_BOT_TOKEN")
        chat_id = get_secret("TELEGRAM_CHAT_ID")
        
        url = f"https://api.telegram.org/bot{token}/sendVideo"
        logger.info(f"Uploading media file to Telegram chat: {chat_id}...")
        
        with open(video_path, "rb") as video_file:
            payload = {
                "chat_id": chat_id,
                "caption": caption
            }
            files = {
                "video": video_file
            }
            
            # Allow up to 120 seconds for the request to complete
            response = requests.post(url, data=payload, files=files, timeout=120)
            response.raise_for_status()
            
        logger.info("Telegram broadcast upload complete.")
        return {"success": True}
        
    except Exception as error:
        logger.error(f"Telegram Upload Failed: {error}")
        return {"success": False, "error": str(error)}

def publish_video(video_path, title, youtube_description, youtube_tags, telegram_caption, category_id="27", publish_youtube=True, publish_telegram=True):
    """Orchestrate video distribution to selected destinations."""
    results = {}
    
    if publish_youtube:
        logger.info("Distribution target: YouTube Shorts")
        results["youtube"] = upload_to_youtube(video_path, title, youtube_description, youtube_tags, category_id)
    else:
        results["youtube"] = {"success": False, "status": "skipped"}
        
    if publish_telegram:
        logger.info("Distribution target: Telegram Channel")
        results["telegram"] = upload_to_telegram(video_path, telegram_caption)
    else:
        results["telegram"] = {"success": False, "status": "skipped"}
        
    return results
