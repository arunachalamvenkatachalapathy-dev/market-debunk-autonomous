"""
src/publishing/add_pinned_cta.py

Adds 'Ghost your friends \ud83d\udc49 beggy.vercel.app' to:
1. YouTube Shorts description (top line) & comment section
2. Facebook Reel comment section
3. Instagram Reel comment section
"""
from __future__ import annotations

import os
from pathlib import Path
import requests

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="add_pinned_cta")

YT_VIDEO_ID = "nXo7Ld1aup4"
FB_VIDEO_ID = "1070024325656312"
IG_CONTAINER_ID = "18096665264437456"

CTA_TEXT = "Ghost your friends \ud83d\udc49 beggy.vercel.app"

NEW_YT_DESCRIPTION = """Ghost your friends \ud83d\udc49 beggy.vercel.app

\u20b9458 for one biryani at 1am? Nope. I ordered on Beggy - the food app where nothing ever arrives and your money stays in your account. Then I ghosted my friend with a fake order \ud83d\ude02

Try it (free, no login): https://beggy.vercel.app

#shorts #beggy #latenightcravings #biryani #savemoney #indianmemes #studentlife"""


def update_youtube(video_id: str, new_description: str, comment_text: str):
    """Updates YouTube video description and attempts to post top-level comment."""
    log.info("Updating YouTube video %s description...", video_id)
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=settings.YT_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.YT_CLIENT_ID,
            client_secret=settings.YT_CLIENT_SECRET,
        )
        youtube = build("youtube", "v3", credentials=creds, cache_discovery=False)

        # 1. Fetch current snippet
        vid_res = youtube.videos().list(part="snippet", id=video_id).execute()
        items = vid_res.get("items", [])
        if items:
            snippet = items[0]["snippet"]
            snippet["description"] = new_description
            youtube.videos().update(part="snippet", body={"id": video_id, "snippet": snippet}).execute()
            log.info("\u2705 YouTube description updated successfully with CTA!")
        else:
            log.warning("YouTube video %s not found for description update", video_id)

        # 2. Attempt comment
        try:
            body = {
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": comment_text
                        }
                    }
                }
            }
            res = youtube.commentThreads().insert(part="snippet", body=body).execute()
            log.info("\u2705 YouTube pinned comment posted (ID: %s)", res.get("id"))
        except Exception as c_err:
            log.info("YouTube comment posting notice (scope/disabled: %s)", c_err)

    except Exception as exc:
        log.error("YouTube update failed: %s", exc)


def comment_on_facebook(video_id: str, comment_text: str):
    """Posts a comment on the Facebook Reel."""
    token = getattr(settings, "FACEBOOK_ACCESS_TOKEN", "").strip() or settings.INSTAGRAM_ACCESS_TOKEN.strip()
    page_id = getattr(settings, "FACEBOOK_PAGE_ID", "").strip() or getattr(settings, "FB_PAGE_ID", "").strip()
    base_url = f"https://graph.facebook.com/{settings.INSTAGRAM_GRAPH_VERSION}"

    if not token or not video_id:
        return

    # Auto-resolve page token
    try:
        acc_res = requests.get(f"{base_url}/me/accounts?access_token={token}", timeout=10).json()
        if "data" in acc_res:
            for acc in acc_res["data"]:
                if str(acc.get("id")) == str(page_id):
                    token = acc.get("access_token", token)
                    break
    except Exception:
        pass

    try:
        log.info("Posting comment on Facebook Reel %s...", video_id)
        res = requests.post(
            f"{base_url}/{video_id}/comments",
            data={"message": comment_text, "access_token": token},
            timeout=15,
        )
        res_json = res.json()
        if "id" in res_json:
            log.info("\u2705 Facebook comment posted successfully (ID: %s)", res_json["id"])
        else:
            log.warning("Facebook comment response: %s", res_json)
    except Exception as exc:
        log.error("Facebook comment failed: %s", exc)


def comment_on_instagram(media_id: str, comment_text: str):
    """Posts a comment on the Instagram Reel."""
    token = (settings.INSTAGRAM_ACCESS_TOKEN or os.environ.get("META_ACCESS_TOKEN") or os.environ.get("INSTAGRAM_ACCESS_TOKEN") or "").strip()
    base_url = f"https://graph.facebook.com/{settings.INSTAGRAM_GRAPH_VERSION}"

    if not token:
        return

    try:
        log.info("Posting comment on Instagram Reel %s...", media_id)
        res = requests.post(
            f"{base_url}/{media_id}/comments",
            data={"message": comment_text, "access_token": token},
            timeout=15,
        )
        res_json = res.json()
        if "id" in res_json:
            log.info("\u2705 Instagram comment posted successfully (ID: %s)", res_json["id"])
        else:
            log.warning("Instagram comment response: %s", res_json)
    except Exception as exc:
        log.error("Instagram comment failed: %s", exc)


def main():
    log.info("Updating description & comments with CTA '%s'...", CTA_TEXT)
    update_youtube(YT_VIDEO_ID, NEW_YT_DESCRIPTION, CTA_TEXT)
    comment_on_facebook(FB_VIDEO_ID, CTA_TEXT)
    comment_on_instagram(IG_CONTAINER_ID, CTA_TEXT)
    log.info("Finished updating CTA across platforms.")


if __name__ == "__main__":
    main()
