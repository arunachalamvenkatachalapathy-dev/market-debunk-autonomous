"""
src/publishing/instagram_publisher.py

Instagram Reels publisher using the Meta Instagram Graph API.

Supports:
1. Direct Resumable Binary Upload: Streams local distribution_ready.mp4 directly to Meta.
   NO external hosting or public CDN URL required!
2. Hosted URL Fallback: Uses INSTAGRAM_VIDEO_URL if specified.
3. Permalinks & Status Polling: Fetches the live https://www.instagram.com/reel/... URL.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import requests

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="instagram_publish")


def _upload_binary_resumable(upload_uri: str, video_path: Path, token: str) -> bool:
    """Stream local MP4 binary data directly to Meta's resumable upload server."""
    file_size = video_path.stat().st_size
    log.info("Streaming %d KB directly to Meta resumable upload endpoint...", file_size // 1024)

    headers = {
        "Authorization": f"OAuth {token}",
        "file_offset": "0",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(file_size),
    }

    with open(video_path, "rb") as video_file:
        res = requests.post(upload_uri, headers=headers, data=video_file, timeout=300)

    if res.status_code not in (200, 201):
        log.error("Binary upload failed: HTTP %d: %s", res.status_code, res.text[:300])
        res.raise_for_status()

    log.info("✓ Binary video bytes received by Meta.")
    return True


def publish_reel(
    video_path: Path,
    title: str,
    description: str,
    hashtags: list[str],
) -> Optional[str]:
    """
    Publish a video as an Instagram Reel.

    Returns the published Reel's permalink or ID on success, or None on failure
    without raising an exception (allowing the rest of the pipeline to continue).
    """
    if not settings.ENABLE_INSTAGRAM:
        log.info("Instagram publishing disabled (ENABLE_INSTAGRAM != true) — skipping")
        return None

    token = settings.INSTAGRAM_ACCESS_TOKEN.strip()
    user_id = settings.INSTAGRAM_USER_ID.strip()

    if not token or not user_id:
        log.warning("Instagram credentials missing (INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_USER_ID) — skipping")
        return None

    if not video_path.is_file() or video_path.stat().st_size == 0:
        log.error("Video file does not exist or is empty: %s — skipping Instagram upload", video_path)
        return None

    # Construct clean caption
    clean_tags = " ".join(t if t.startswith("#") else f"#{t}" for t in hashtags)
    caption = f"{title}\n\n{description}\n\n{clean_tags}".strip()[:2200]

    base_url = f"https://graph.facebook.com/{settings.INSTAGRAM_GRAPH_VERSION}"

    try:
        # Step 1: Initialize Container
        # Prefer direct resumable upload of local file, unless a valid HTTPS video URL is explicitly configured.
        if settings.INSTAGRAM_VIDEO_URL and settings.INSTAGRAM_VIDEO_URL.startswith("https://"):
            log.info("Using configured INSTAGRAM_VIDEO_URL for container creation...")
            create_payload = {
                "media_type": "REELS",
                "video_url": settings.INSTAGRAM_VIDEO_URL,
                "caption": caption,
                "access_token": token,
            }
        else:
            log.info("Initiating direct Meta resumable upload session for '%s'...", video_path.name)
            create_payload = {
                "media_type": "REELS",
                "upload_type": "resumable",
                "caption": caption,
                "access_token": token,
            }

        init_res = requests.post(f"{base_url}/{user_id}/media", data=create_payload, timeout=30)
        init_json = init_res.json()

        if "error" in init_json:
            err_msg = init_json["error"].get("message", str(init_json["error"]))
            raise RuntimeError(f"Meta Graph API container error: {err_msg}")

        creation_id = init_json.get("id")
        upload_uri = init_json.get("uri")

        if not creation_id:
            raise RuntimeError(f"Meta did not return a media container ID. Response: {init_json}")

        log.info("✓ Meta container created (ID: %s)", creation_id)

        # Step 2: Upload Binary Bytes if Resumable
        if upload_uri:
            _upload_binary_resumable(upload_uri, video_path, token)

        # Step 3: Poll Container Processing Status
        log.info("Polling Meta media processing status...")
        max_attempts = 30  # 30 * 5s = 150 seconds max
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
                log.info("✓ Media processing FINISHED (ready to publish).")
                break
            elif status_code == "IN_PROGRESS":
                log.info("  Processing in progress... (%d/%d)", attempt, max_attempts)
            elif status_code in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Meta media processing failed with status: {status_code}. Info: {status_json}")
        else:
            raise RuntimeError("Meta media container processing timed out after 150 seconds.")

        # Step 4: Publish Reel
        log.info("Publishing container %s as live Instagram Reel...", creation_id)
        pub_res = requests.post(
            f"{base_url}/{user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": token},
            timeout=30,
        )
        pub_json = pub_res.json()

        if "error" in pub_json:
            err_msg = pub_json["error"].get("message", str(pub_json["error"]))
            raise RuntimeError(f"Meta media_publish error: {err_msg}")

        media_id = pub_json.get("id")
        if not media_id:
            raise RuntimeError(f"Meta did not return published media ID: {pub_json}")

        # Step 5: Query Reel Permalink
        reel_url = None
        try:
            meta_res = requests.get(
                f"{base_url}/{media_id}",
                params={"fields": "permalink,shortcode", "access_token": token},
                timeout=15,
            )
            meta_json = meta_res.json()
            reel_url = meta_json.get("permalink")
        except Exception:
            pass

        final_link = reel_url or f"https://www.instagram.com/reel/{media_id}/"
        log.info("==================================================")
        log.info("🎉 INSTAGRAM REEL PUBLISHED SUCCESSFULLY!")
        log.info("Reel URL: %s", final_link)
        log.info("==================================================")
        return final_link

    except Exception as exc:
        log.error("Instagram publishing failed; pipeline continuing uninterrupted: %s", exc)
        return None
