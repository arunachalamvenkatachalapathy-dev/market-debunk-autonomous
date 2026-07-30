import logging
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from src.generator import get_secret

# Configure logging
logger = logging.getLogger(__name__)

def upload_to_youtube(video_path, title, description, tags, category_id="27"):
    """Upload video to YouTube channel as a Short using OAuth2 refresh tokens."""
    try:
        # Fetch tokens from Secret Manager / env
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
        
        # Ensure tags is a valid list of strings
        tags_list = tags if isinstance(tags, list) else [t.strip() for t in str(tags).split(",") if t.strip()]
        tags_list = tags_list[:15]
        
        formatted_title = f"{str(title)[:88]} #Shorts"
        formatted_desc = str(description)[:4900] if description else formatted_title
        
        # Try uploading with public privacy status first, with fallback to unlisted/private
        for privacy_status in ["public", "unlisted", "private"]:
            try:
                body = {
                    "snippet": {
                        "title": formatted_title,
                        "description": formatted_desc,
                        "tags": tags_list,
                        "categoryId": str(category_id)
                    },
                    "status": {
                        "privacyStatus": privacy_status
                    }
                }
                
                logger.info(f"Starting YouTube upload stream (privacyStatus: {privacy_status})...")
                media = MediaFileUpload(video_path, chunksize=1024*1024, resumable=True, mimetype="video/mp4")
                
                request = youtube_service.videos().insert(
                    part="snippet,status",
                    body=body,
                    media_body=media
                )
                
                response = None
                while response is None:
                    status, response = request.next_chunk()
                    if status:
                        logger.info(f"YouTube Upload progress ({privacy_status}): {int(status.progress() * 100)}%")
                        
                video_id = response.get("id")
                logger.info(f"✅ YouTube video published successfully (ID: {video_id}, Status: {privacy_status})")
                return {"success": True, "video_id": video_id, "privacy_status": privacy_status}
            except Exception as e:
                logger.warning(f"YouTube upload attempt with privacyStatus='{privacy_status}' failed: {e}")
                if privacy_status == "private":
                    raise e
                
    except Exception as error:
        logger.error(f"❌ YouTube Upload Failed: {error}")
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
