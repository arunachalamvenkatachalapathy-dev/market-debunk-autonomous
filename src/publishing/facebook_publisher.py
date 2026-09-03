"""
src/publishing/facebook_publisher.py

Facebook Reels publisher using Meta Graph API for Facebook Pages.
Publishes 9:16 vertical videos directly to your Facebook Page as Reels.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import requests

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="facebook_publish")


def publish_reel(
    video_path: Path,
    title: str,
    description: str,
    hashtags: list[str],
) -> Optional[str]:
    """
    Publish a video as a Facebook Reel on the configured Facebook Page.
    Returns the Facebook Reel URL on success, or None on failure without halting pipeline.
    """
    # Dedicated FACEBOOK_ACCESS_TOKEN or reuse INSTAGRAM_ACCESS_TOKEN (which has page permissions)
    token = getattr(settings, "FACEBOOK_ACCESS_TOKEN", "").strip() or settings.INSTAGRAM_ACCESS_TOKEN.strip()
    page_id = getattr(settings, "FACEBOOK_PAGE_ID", "").strip() or getattr(settings, "FB_PAGE_ID", "").strip()

    if not page_id or not token:
        log.info("Facebook publishing skipped (FACEBOOK_PAGE_ID or access token not set)")
        return None

    if not video_path.is_file() or video_path.stat().st_size == 0:
        log.error("Video file missing or empty: %s — skipping Facebook Reel", video_path)
        return None

    # Construct clean Facebook Reel caption
    clean_tags = " ".join(t if t.startswith("#") else f"#{t}" for t in hashtags)
    caption = f"{title}\n\n{description}\n\n{clean_tags}".strip()[:2200]

    base_url = f"https://graph.facebook.com/{settings.INSTAGRAM_GRAPH_VERSION}"

    try:
        log.info("Initializing Facebook Reel upload on Page %s...", page_id)
        # Step 1: Initialize Reel session
        init_res = requests.post(
            f"{base_url}/{page_id}/video_reels",
            data={
                "upload_phase": "start",
                "access_token": token,
            },
            timeout=30,
        )
        init_json = init_res.json()
        if "error" in init_json:
            raise RuntimeError(f"Meta start reel error: {init_json['error']}")

        video_id = init_json.get("video_id")
        upload_url = init_json.get("upload_url")
        if not video_id or not upload_url:
            raise RuntimeError(f"Meta did not return video_id or upload_url: {init_json}")

        log.info("✓ Facebook Reel session initialized (Video ID: %s)", video_id)

        # Step 2: Upload Binary Bytes
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
        log.info("✓ Video binary streamed to Facebook.")

        # Step 3: Finish & Publish
        log.info("Finalizing and publishing Facebook Reel %s...", video_id)
        fin_res = requests.post(
            f"{base_url}/{page_id}/video_reels",
            data={
                "upload_phase": "finish",
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": caption,
                "access_token": token,
            },
            timeout=30,
        )
        fin_json = fin_res.json()
        if "error" in fin_json:
            raise RuntimeError(f"Meta finish reel error: {fin_json['error']}")

        reel_link = f"https://www.facebook.com/reel/{video_id}/"
        log.info("==================================================")
        log.info("🎉 FACEBOOK REEL PUBLISHED SUCCESSFULLY!")
        log.info("Reel URL: %s", reel_link)
        log.info("==================================================")
        return reel_link

    except Exception as exc:
        log.error("Facebook Reel publishing failed; pipeline continuing: %s", exc)
        return None
