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


class PublishResult(str):
    """String URL carrying attached media_id metadata."""
    media_id: Optional[str] = None


def _upload_binary_resumable(upload_uri: str, video_path: Path, token: str) -> bool:
    """Stream local MP4 binary data directly to Meta's resumable upload server."""
    file_size = video_path.stat().st_size
    log.info("Streaming %d KB directly to Meta resumable upload endpoint...", file_size // 1024)

    with open(video_path, "rb") as video_file:
        video_bytes = video_file.read()

    headers = {
        "Authorization": f"OAuth {token}",
        "offset": "0",
        "file_size": str(len(video_bytes)),
        "Content-Length": str(len(video_bytes)),
        "Content-Type": "application/octet-stream",
    }

    res = requests.post(upload_uri, headers=headers, data=video_bytes, timeout=300)

    if res.status_code not in (200, 201):
        log.error("Binary upload failed: HTTP %d: %s", res.status_code, res.text[:300])
        res.raise_for_status()

    log.info("✓ Binary video bytes received by Meta.")
    return True


def _get_public_video_url_via_release(video_path: Path) -> Optional[str]:
    """Upload video to the public repository's latest-assets release to get a direct HTTPS URL for Meta."""
    import os
    import requests

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    repo = os.environ.get("GITHUB_REPOSITORY") or "arunachalamvenkatachalapathy-dev/market-debunk-autonomous"
    tag = "latest-assets"
    target_filename = video_path.name

    # Method 1: Direct GitHub REST API
    if token:
        try:
            log.info("Uploading video to GitHub release '%s' via REST API...", tag)
            gh_headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
            rel_res = requests.get(f"https://api.github.com/repos/{repo}/releases/tags/{tag}", headers=gh_headers, timeout=15)
            if rel_res.status_code == 200:
                rel_json = rel_res.json()
                upload_url_base = rel_json.get("upload_url", "").split("{")[0]
                # Delete existing asset with same name if present
                for asset in rel_json.get("assets", []):
                    if asset.get("name") == target_filename:
                        requests.delete(f"https://api.github.com/repos/{repo}/releases/assets/{asset.get('id')}", headers=gh_headers, timeout=15)
                        break
                with open(video_path, "rb") as f:
                    up_res = requests.post(
                        f"{upload_url_base}?name={target_filename}",
                        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/octet-stream"},
                        data=f,
                        timeout=300,
                    )
                if up_res.status_code in (200, 201):
                    public_url = f"https://github.com/{repo}/releases/download/{tag}/{target_filename}"
                    log.info("✓ Public video URL ready for Meta via GitHub API: %s", public_url)
                    return public_url
                else:
                    log.warning("REST API release upload returned %d: %s", up_res.status_code, up_res.text[:200])
        except Exception as exc:
            log.warning("REST API release upload failed: %s", exc)

    # Method 2: Fallback to gh CLI
    import shutil
    import subprocess
    if shutil.which("gh"):
        try:
            log.info("Publishing temporary public asset via gh CLI release '%s'...", tag)
            env = os.environ.copy()
            if token:
                env["GH_TOKEN"] = token
            cmd = ["gh", "release", "upload", tag, str(video_path), "--clobber", "-R", repo]
            run_res = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
            if run_res.returncode == 0:
                public_url = f"https://github.com/{repo}/releases/download/{tag}/{target_filename}"
                log.info("✓ Public video URL available for Meta: %s", public_url)
                return public_url
            else:
                log.warning("gh release upload failed (%d): %s", run_res.returncode, run_res.stderr[:200])
        except Exception as exc:
            log.warning("Could not upload video to GitHub release: %s", exc)
    return None


def _resolve_instagram_user_id(token: str, configured_user_id: str, graph_version: str = "v23.0") -> Optional[str]:
    """Auto-discover linked Instagram Business Account ID from Meta Graph API if not explicitly set."""
    if configured_user_id:
        return configured_user_id
    try:
        # 1. Query /me/accounts for linked instagram_business_account
        res = requests.get(f"https://graph.facebook.com/{graph_version}/me/accounts?fields=instagram_business_account,name&access_token={token}", timeout=15)
        if res.status_code == 200:
            for page in res.json().get("data", []):
                ig = page.get("instagram_business_account", {})
                if ig and ig.get("id"):
                    log.info("Auto-discovered Instagram User ID %s from Page '%s'", ig["id"], page.get("name"))
                    return str(ig["id"])
        # 2. Query /me?fields=instagram_business_account
        res2 = requests.get(f"https://graph.facebook.com/{graph_version}/me?fields=instagram_business_account&access_token={token}", timeout=15)
        if res2.status_code == 200:
            ig = res2.json().get("instagram_business_account", {})
            if ig and ig.get("id"):
                log.info("Auto-discovered Instagram User ID %s from /me endpoint", ig["id"])
                return str(ig["id"])
    except Exception as exc:
        log.warning("Could not auto-discover Instagram User ID: %s", exc)
    return None


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

    import os
    token = (settings.INSTAGRAM_ACCESS_TOKEN or os.environ.get("META_ACCESS_TOKEN") or os.environ.get("INSTAGRAM_ACCESS_TOKEN") or "").strip()
    configured_user_id = (settings.INSTAGRAM_USER_ID or os.environ.get("INSTAGRAM_USER_ID") or "").strip()
    user_id = _resolve_instagram_user_id(token, configured_user_id, settings.INSTAGRAM_GRAPH_VERSION) if token else ""

    if not token or not user_id:
        log.warning("Instagram credentials missing (INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_USER_ID) — skipping")
        return None

    if not video_path.is_file() or video_path.stat().st_size == 0:
        log.error("Video file does not exist or is empty: %s — skipping Instagram upload", video_path)
        return None

    # Construct high-converting caption with comment trigger & engagement CTA
    clean_tags = " ".join(t if t.startswith("#") else f"#{t}" for t in hashtags)
    cta = "💬 Comment 'GUIDE' below to get the full risk playbook sent directly to your DMs!\n📌 Save this Reel before your next trade."
    caption = f"{title}\n\n{description}\n\n{cta}\n\n{clean_tags}".strip()[:2200]

    base_url = f"https://graph.facebook.com/{settings.INSTAGRAM_GRAPH_VERSION}"

    try:
        # Step 1: Initialize Container
        # Priority 1: Direct Resumable Binary Upload
        # Priority 2: Configured INSTAGRAM_VIDEO_URL
        # Priority 3: Automatic fallback to public GitHub Release video URL
        video_url = settings.INSTAGRAM_VIDEO_URL if (settings.INSTAGRAM_VIDEO_URL and settings.INSTAGRAM_VIDEO_URL.startswith("https://")) else None
        creation_id = None

        if not video_url:
            try:
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
                    raise RuntimeError(f"Meta Graph API container error: {init_json['error']}")
                creation_id = init_json.get("id")
                upload_uri = init_json.get("uri")

                if creation_id and upload_uri:
                    log.info("✓ Meta container created (ID: %s)", creation_id)
                    _upload_binary_resumable(upload_uri, video_path, token)
            except Exception as res_err:
                log.warning("Direct resumable upload failed (%s). Attempting hosted URL fallback via GitHub Release...", res_err)
                video_url = _get_public_video_url_via_release(video_path)
                creation_id = None

        if video_url and not creation_id:
            log.info("Creating Meta container using public video URL: %s", video_url)
            create_payload = {
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": token,
            }
            init_res = requests.post(f"{base_url}/{user_id}/media", data=create_payload, timeout=30)
            init_json = init_res.json()
            if "error" in init_json:
                raise RuntimeError(f"Meta Graph API container error with video_url: {init_json['error']}")
            creation_id = init_json.get("id")
            if not creation_id:
                raise RuntimeError(f"Meta did not return a media container ID. Response: {init_json}")
            log.info("✓ Meta container created via video_url (ID: %s)", creation_id)

        if not creation_id:
            raise RuntimeError("Failed to create Meta media container via both resumable and URL methods.")

        # Step 3: Poll Container Processing Status
        log.info("Polling Meta media processing status for container %s...", creation_id)
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

        final_link = PublishResult(reel_url or f"https://www.instagram.com/reel/{media_id}/")
        final_link.media_id = str(media_id)
        log.info("==================================================")
        log.info("🎉 INSTAGRAM REEL PUBLISHED SUCCESSFULLY!")
        log.info("Reel URL: %s (Media ID: %s)", final_link, media_id)
        log.info("==================================================")
        return final_link

    except Exception as exc:
        log.error("Instagram publishing failed; pipeline continuing uninterrupted: %s", exc)
        return None
