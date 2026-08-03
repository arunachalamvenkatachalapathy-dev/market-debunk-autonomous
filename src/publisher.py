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

def upload_to_twitter(video_path, caption, youtube_url=None):
    """
    Extract a 10-second clip from video_path, upload media to Twitter/X API v1.1,
    and post a Tweet via Twitter API v2 redirecting users to the full YouTube video.
    """
    import os
    import time
    import subprocess
    from requests_oauthlib import OAuth1

    try:
        api_key = get_secret("TWITTER_API_KEY")
        api_secret = get_secret("TWITTER_API_SECRET")
        access_token = get_secret("TWITTER_ACCESS_TOKEN")
        access_token_secret = get_secret("TWITTER_ACCESS_TOKEN_SECRET")

        if not (api_key and api_secret and access_token and access_token_secret):
            logger.warning("⚠️ Twitter/X API credentials missing (TWITTER_API_KEY / ACCESS_TOKEN). Skipping Twitter post.")
            return {"success": False, "status": "skipped", "reason": "missing_credentials"}

        auth = OAuth1(api_key, api_secret, access_token, access_token_secret)

        # 1. Extract 10-second teaser clip using FFmpeg
        teaser_path = os.path.join(os.path.dirname(video_path), "teaser_10s.mp4")
        clip_cmd = ["ffmpeg", "-y", "-i", video_path, "-t", "10", "-c", "copy", teaser_path]
        subprocess.run(clip_cmd, capture_output=True, check=True)

        file_size = os.path.getsize(teaser_path)

        # 2. Chunked Media Upload to Twitter v1.1 API
        upload_url = "https://upload.twitter.com/1.1/media/upload.json"
        logger.info(f"Uploading 10s clip ({file_size} bytes) to Twitter/X...")

        # INIT
        init_res = requests.post(upload_url, auth=auth, data={
            "command": "INIT",
            "total_bytes": file_size,
            "media_type": "video/mp4",
            "media_category": "tweet_video"
        })
        init_res.raise_for_status()
        media_id = init_res.json()["media_id_string"]

        # APPEND
        with open(teaser_path, "rb") as f:
            segment_id = 0
            while True:
                chunk = f.read(4 * 1024 * 1024)
                if not chunk:
                    break
                app_res = requests.post(upload_url, auth=auth, data={
                    "command": "APPEND",
                    "media_id": media_id,
                    "segment_index": segment_id
                }, files={"media": chunk})
                app_res.raise_for_status()
                segment_id += 1

        # FINALIZE
        fin_res = requests.post(upload_url, auth=auth, data={
            "command": "FINALIZE",
            "media_id": media_id
        })
        fin_res.raise_for_status()

        # Check processing status for video if required
        processing_info = fin_res.json().get("processing_info")
        if processing_info:
            state = processing_info.get("state")
            while state in ["pending", "in_progress"]:
                check_after = processing_info.get("check_after_secs", 2)
                time.sleep(check_after)
                status_res = requests.get(upload_url, auth=auth, params={
                    "command": "STATUS",
                    "media_id": media_id
                })
                status_res.raise_for_status()
                processing_info = status_res.json().get("processing_info", {})
                state = processing_info.get("state")

        # 3. Post Tweet with 10s teaser clip & YouTube URL via Twitter API v2
        tweet_url = "https://api.twitter.com/2/tweets"
        full_text = caption
        if youtube_url:
            full_text = f"{caption}\n\n👇 Watch full video on YouTube:\n{youtube_url}"

        tweet_body = {
            "text": full_text[:280],
            "media": {
                "media_ids": [media_id]
            }
        }

        logger.info("Publishing Tweet with 10s teaser video clip...")
        tweet_res = requests.post(tweet_url, auth=auth, json=tweet_body)
        tweet_res.raise_for_status()
        tweet_data = tweet_res.json()
        tweet_id = tweet_data.get("data", {}).get("id")

        logger.info(f"✅ Posted 10s teaser clip to Twitter/X (Tweet ID: {tweet_id})")
        return {"success": True, "tweet_id": tweet_id}

    except Exception as error:
        logger.error(f"❌ Twitter/X Upload Failed: {error}")
        return {"success": False, "error": str(error)}


def publish_video(video_path, title, youtube_description, youtube_tags, telegram_caption, category_id="27", publish_youtube=True, publish_telegram=True, publish_twitter=True):
    """Orchestrate video distribution to selected destinations (YouTube, Telegram, Twitter/X)."""
    results = {}
    yt_url = None
    
    if publish_youtube:
        logger.info("Distribution target: YouTube Shorts")
        yt_res = upload_to_youtube(video_path, title, youtube_description, youtube_tags, category_id)
        results["youtube"] = yt_res
        if yt_res.get("success") and yt_res.get("video_id"):
            yt_url = f"https://youtube.com/shorts/{yt_res['video_id']}"
    else:
        results["youtube"] = {"success": False, "status": "skipped"}
        
    if publish_telegram:
        logger.info("Distribution target: Telegram Channel")
        results["telegram"] = upload_to_telegram(video_path, telegram_caption)
    else:
        results["telegram"] = {"success": False, "status": "skipped"}

    if publish_twitter:
        logger.info("Distribution target: Twitter / X")
        twitter_caption = f"🚨 {title}\n\nWatch 10s preview below! 👇"
        results["twitter"] = upload_to_twitter(video_path, twitter_caption, youtube_url=yt_url)
    else:
        results["twitter"] = {"success": False, "status": "skipped"}
        
    return results
