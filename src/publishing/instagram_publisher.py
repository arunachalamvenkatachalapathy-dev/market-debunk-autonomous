"""Optional Instagram Reels publisher using the Instagram Graph API.

Instagram requires a Business/Creator account and a publicly reachable HTTPS
video URL. The generated local MP4 is not itself a valid ``video_url``; a
hosting step must provide ``INSTAGRAM_VIDEO_URL`` before publishing is enabled.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import requests

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="instagram_publish")


def publish_reel(video_path: Path, title: str, description: str, hashtags: list[str]) -> Optional[str]:
    """Publish a Reel, or return None without failing the pipeline."""
    if not settings.ENABLE_INSTAGRAM:
        log.info("Instagram publishing disabled — skipping")
        return None

    token = settings.INSTAGRAM_ACCESS_TOKEN
    user_id = settings.INSTAGRAM_USER_ID
    video_url = settings.INSTAGRAM_VIDEO_URL
    if not token or not user_id:
        log.warning("Instagram credentials missing — publishing skipped")
        return None
    if not video_url:
        log.warning("INSTAGRAM_VIDEO_URL missing — Instagram skipped; Meta cannot fetch a local MP4")
        return None
    if not video_url.startswith("https://"):
        log.warning("INSTAGRAM_VIDEO_URL must be a public HTTPS URL — Instagram skipped")
        return None

    caption = f"{title}\n\n{description}\n\n" + " ".join(
        tag if tag.startswith("#") else f"#{tag}" for tag in hashtags
    )
    base_url = f"https://graph.facebook.com/{settings.INSTAGRAM_GRAPH_VERSION}"
    try:
        create = requests.post(
            f"{base_url}/{user_id}/media",
            data={"media_type": "REELS", "video_url": video_url, "caption": caption[:2200], "access_token": token},
            timeout=30,
        )
        create.raise_for_status()
        creation_id = create.json().get("id")
        if not creation_id:
            raise RuntimeError("Instagram did not return a media container ID")

        for _ in range(12):
            status = requests.get(
                f"{base_url}/{creation_id}",
                params={"fields": "status_code", "access_token": token},
                timeout=20,
            )
            status.raise_for_status()
            status_code = status.json().get("status_code")
            if status_code == "FINISHED":
                break
            if status_code in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Instagram media processing status: {status_code}")
            time.sleep(5)
        else:
            raise RuntimeError("Instagram media container did not finish processing in time")

        publish = requests.post(
            f"{base_url}/{user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": token},
            timeout=30,
        )
        publish.raise_for_status()
        media_id = publish.json().get("id")
        log.info("✓ Instagram Reel published: %s", media_id)
        return media_id
    except Exception as exc:
        log.error("Instagram publishing failed; continuing pipeline: %s", exc)
        return None
