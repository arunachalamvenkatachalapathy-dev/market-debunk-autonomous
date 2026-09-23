"""
src/publishing/publish_custom_ad.py

Dedicated one-click publisher for custom marketing Reels/Shorts (e.g. Beggy).
Uploads directly to YouTube Shorts, Instagram Reels, and Facebook Reels
using the exact provided title, description, and captions.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="custom_publish")

VIDEO_PATH = Path("assets/custom_video.mp4")

YT_TITLE = "Ordered biryani at 1am\u2026 the app ghosted ME \ud83d\udc80 #shorts"
YT_DESCRIPTION = """\u20b9458 for one biryani at 1am? Nope. I ordered on Beggy - the food app where nothing ever arrives and your money stays in your account. Then I ghosted my friend with a fake order \ud83d\ude02

Try it (free, no login): beggy.vercel.app

#shorts #beggy #latenightcravings #biryani #savemoney #indianmemes #studentlife"""

IG_CAPTION = """ordered biryani at 1am. paid \u20b90. the rider is still coming. \ud83d\udef5

beggy - fake food, real money. ghost your friends \ud83d\udc7b
link in bio \u2192 beggy.vercel.app

#beggy #latenightcravings #biryani #savemoney #indianmemes #reelsindia #studentlife #foodmemes"""

FB_CAPTION = """1am. Biryani craving. \u20b9458 bill. \ud83d\ude10
So I ordered on Beggy instead - the rider never comes, and the \u20b9458 stays in my account.
Then I sent a fake order to my friend. He's still waiting \ud83d\ude02

Ghost your friends \ud83d\udc49 beggy.vercel.app

#beggy #latenightcravings #biryani #savemoney"""


def upload_youtube_short(video_path: Path, title: str, description: str) -> Optional[str]:
    """Upload directly to YouTube Shorts with exact title and description."""
    if not all([settings.YT_CLIENT_ID, settings.YT_CLIENT_SECRET, settings.YT_REFRESH_TOKEN]):
        log.warning("YouTube OAuth credentials missing \u2014 YouTube upload skipped")
        return None

    log.info("Uploading to YouTube: '%s'...", title)
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload

        creds = Credentials(
            token=None,
            refresh_token=settings.YT_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.YT_CLIENT_ID,
            client_secret=settings.YT_CLIENT_SECRET,
        )
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

        tags = ["shorts", "beggy", "latenightcravings", "biryani", "savemoney", "indianmemes", "studentlife"]
        request_body = {
            "snippet": {
                "title": title[:100],
                "description": description[:5000],
                "tags": tags,
                "categoryId": "22",  # People & Blogs
                "defaultLanguage": "en",
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(
            str(video_path),
            mimetype="video/mp4",
            resumable=True,
            chunksize=5 * 1024 * 1024,
        )

        upload_request = youtube.videos().insert(
            part=",".join(request_body.keys()),
            body=request_body,
            media_body=media,
        )

        response = None
        while response is None:
            status, response = upload_request.next_chunk()
            if status:
                log.info("YouTube upload progress: %.0f%%", status.progress() * 100)

        video_id = response.get("id", "")
        yt_url = f"https://www.youtube.com/shorts/{video_id}"
        log.info("==================================================")
        log.info("\u2705 YOUTUBE SHORT PUBLISHED SUCCESSFULLY!")
        log.info("Short URL: %s", yt_url)
        log.info("==================================================")
        return yt_url

    except Exception as exc:
        log.error("YouTube upload failed: %s", exc)
        return None


def upload_instagram_reel(video_path: Path, caption: str) -> Optional[str]:
    """Upload directly to Instagram Reels with exact caption."""
    token = (settings.INSTAGRAM_ACCESS_TOKEN or os.environ.get("META_ACCESS_TOKEN") or os.environ.get("INSTAGRAM_ACCESS_TOKEN") or "").strip()
    configured_user_id = (settings.INSTAGRAM_USER_ID or os.environ.get("INSTAGRAM_USER_ID") or "").strip()

    from src.publishing.instagram_publisher import _resolve_instagram_user_id, _upload_binary_resumable

    user_id = _resolve_instagram_user_id(token, configured_user_id, settings.INSTAGRAM_GRAPH_VERSION) if token else ""
    if not token or not user_id:
        log.warning("Instagram credentials missing \u2014 Instagram upload skipped")
        return None

    base_url = f"https://graph.facebook.com/{settings.INSTAGRAM_GRAPH_VERSION}"
    try:
        log.info("Initiating direct Meta resumable upload session for Instagram Reel...")
        create_payload = {
            "media_type": "REELS",
            "upload_type": "resumable",
            "caption": caption[:2200],
            "access_token": token,
        }
        init_res = requests.post(f"{base_url}/{user_id}/media", data=create_payload, timeout=30)
        init_json = init_res.json()
        if "error" in init_json:
            raise RuntimeError(f"Meta Graph API container error: {init_json['error']}")

        creation_id = init_json.get("id")
        upload_uri = init_json.get("uri")
        if not creation_id or not upload_uri:
            raise RuntimeError(f"Failed to obtain container ID or upload URI: {init_json}")

        log.info("\u2713 Meta container created (ID: %s)", creation_id)
        if not _upload_binary_resumable(upload_uri, video_path, token):
            raise RuntimeError("Direct binary upload to Meta failed")

        log.info("Polling Meta media processing status for container %s...", creation_id)
        max_attempts = 35
        for attempt in range(1, max_attempts + 1):
            time.sleep(5)
            status_res = requests.get(
                f"{base_url}/{creation_id}",
                params={"fields": "status_code,status", "access_token": token},
                timeout=20,
            )
            status_json = status_res.json()
            status_code = status_json.get("status_code")
            if status_code == "FINISHED":
                log.info("\u2713 Media processing FINISHED (ready to publish).")
                break
            elif status_code == "IN_PROGRESS":
                log.info("  Processing in progress... (%d/%d)", attempt, max_attempts)
            elif status_code in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Meta media processing failed: {status_code} ({status_json})")
        else:
            raise RuntimeError("Meta media container processing timed out.")

        log.info("Publishing container %s as live Instagram Reel...", creation_id)
        pub_res = requests.post(
            f"{base_url}/{user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": token},
            timeout=30,
        )
        pub_json = pub_res.json()
        if "error" in pub_json:
            raise RuntimeError(f"Meta media_publish error: {pub_json['error']}")

        media_id = pub_json.get("id")
        ig_url = f"https://www.instagram.com/reel/{media_id}/"
        try:
            meta_res = requests.get(
                f"{base_url}/{media_id}",
                params={"fields": "permalink", "access_token": token},
                timeout=15,
            )
            permalink = meta_res.json().get("permalink")
            if permalink:
                ig_url = permalink
        except Exception:
            pass

        log.info("==================================================")
        log.info("\ud83c\udf89 INSTAGRAM REEL PUBLISHED SUCCESSFULLY!")
        log.info("Reel URL: %s", ig_url)
        log.info("==================================================")
        return ig_url

    except Exception as exc:
        log.error("Instagram Reel publish failed: %s", exc)
        return None


def upload_facebook_reel(video_path: Path, caption: str) -> Optional[str]:
    """Upload directly to Facebook Page Reels with exact caption."""
    token = getattr(settings, "FACEBOOK_ACCESS_TOKEN", "").strip() or settings.INSTAGRAM_ACCESS_TOKEN.strip()
    page_id = getattr(settings, "FACEBOOK_PAGE_ID", "").strip() or getattr(settings, "FB_PAGE_ID", "").strip()

    if not page_id or not token:
        log.warning("Facebook credentials missing \u2014 Facebook upload skipped")
        return None

    base_url = f"https://graph.facebook.com/{settings.INSTAGRAM_GRAPH_VERSION}"
    try:
        acc_res = requests.get(f"{base_url}/me/accounts?access_token={token}", timeout=10).json()
        if "data" in acc_res:
            for acc in acc_res["data"]:
                if str(acc.get("id")) == str(page_id):
                    token = acc.get("access_token", token)
                    log.info("\u2713 Resolved dedicated Facebook Page token for %s", page_id)
                    break
    except Exception as tok_err:
        log.debug("Page token auto-resolution skipped: %s", tok_err)

    try:
        log.info("Initializing Facebook Reel upload on Page %s...", page_id)
        init_res = requests.post(
            f"{base_url}/{page_id}/video_reels",
            data={"upload_phase": "start", "access_token": token},
            timeout=30,
        )
        init_json = init_res.json()
        if "error" in init_json:
            raise RuntimeError(f"Meta start reel error: {init_json['error']}")

        video_id = init_json.get("video_id")
        upload_url = init_json.get("upload_url")
        if not video_id or not upload_url:
            raise RuntimeError(f"Meta did not return video_id or upload_url: {init_json}")

        log.info("\u2713 Facebook Reel session initialized (Video ID: %s)", video_id)
        file_size = video_path.stat().st_size
        headers = {
            "Authorization": f"OAuth {token}",
            "offset": "0",
            "file_size": str(file_size),
        }
        log.info("Streaming %d KB directly to Facebook Reels upload server...", file_size // 1024)
        with open(video_path, "rb") as f:
            up_res = requests.post(upload_url, headers=headers, data=f, timeout=300)
        up_res.raise_for_status()
        log.info("\u2713 Video binary streamed to Facebook.")

        log.info("Finalizing and publishing Facebook Reel %s...", video_id)
        fin_res = requests.post(
            f"{base_url}/{page_id}/video_reels",
            data={
                "upload_phase": "finish",
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": caption[:2200],
                "access_token": token,
            },
            timeout=30,
        )
        fin_json = fin_res.json()
        if "error" in fin_json:
            raise RuntimeError(f"Meta finish reel error: {fin_json['error']}")

        reel_link = f"https://www.facebook.com/reel/{video_id}/"
        log.info("==================================================")
        log.info("\ud83c\udf89 FACEBOOK REEL PUBLISHED SUCCESSFULLY!")
        log.info("Reel URL: %s", reel_link)
        log.info("==================================================")
        return reel_link

    except Exception as exc:
        log.error("Facebook Reel publish failed: %s", exc)
        return None


def main():
    if not VIDEO_PATH.is_file():
        log.error("Video file does not exist: %s", VIDEO_PATH)
        sys.exit(1)

    log.info("Starting Multi-Platform Publication for '%s'...", VIDEO_PATH)
    results = {}

    # 1. YouTube Shorts
    results["youtube"] = upload_youtube_short(VIDEO_PATH, YT_TITLE, YT_DESCRIPTION)

    # 2. Instagram Reels
    results["instagram"] = upload_instagram_reel(VIDEO_PATH, IG_CAPTION)

    # 3. Facebook Reels
    results["facebook"] = upload_facebook_reel(VIDEO_PATH, FB_CAPTION)

    log.info("\n==================================================")
    log.info("FINAL PUBLISH SUMMARY:")
    for platform, url in results.items():
        status = f"\u2705 {url}" if url else "\u274c FAILED / SKIPPED"
        log.info("  %s: %s", platform.upper(), status)
    log.info("==================================================")


if __name__ == "__main__":
    main()
