"""
src/publishing/telegram_notifier.py

Sends a mobile push notification to a Telegram chat when the pipeline
completes a successful render or upload.

Disabled by default — set ENABLE_TELEGRAM=true in .env to activate.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="telegram_notify")


def send_completion_notification(
    title: str,
    thesis: str,
    youtube_url: Optional[str] = None,
    instagram_url: Optional[str] = None,
    facebook_url: Optional[str] = None,
    video_path: Optional[Path] = None,
    run_stats: Optional[dict] = None,
    custom_message: Optional[str] = None,
) -> bool:
    """
    Send a Telegram message containing the YouTube, Instagram, and Facebook links and summary.

    Returns True on success, False if disabled or failed.
    """
    # Auto-activate if both token and chat_id are provided (unless explicitly set to false)
    token = settings.TELEGRAM_BOT_TOKEN.strip() if settings.TELEGRAM_BOT_TOKEN else ""
    chat_id = settings.TELEGRAM_CHAT_ID.strip() if settings.TELEGRAM_CHAT_ID else ""

    if not token or not chat_id:
        log.info("Telegram credentials not set (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing) — skipping")
        return False

    if not settings.ENABLE_TELEGRAM:
        log.info("Telegram notifications explicitly disabled (ENABLE_TELEGRAM=false) — skipping")
        return False

    try:
        import requests

        base_url = f"https://api.telegram.org/bot{token}"

        if custom_message:
            message = custom_message
        else:
            # Build default message
            stats_block = ""
            if run_stats:
                stats_block = (
                    f"\n\n📊 *Run Stats:*\n"
                    f"  • Total duration: {run_stats.get('total_duration', 0):.1f}s\n"
                    f"  • Voice: {run_stats.get('voice', 'Google Cloud Chirp3 Fenrir')}"
                )

            links = []
            if youtube_url:
                links.append(f"🎬 *YouTube Shorts:* {youtube_url}")
            if instagram_url:
                links.append(f"📸 *Instagram Reel:* {instagram_url}")
            if facebook_url:
                links.append(f"📘 *Facebook Reel:* {facebook_url}")

            links_block = ("\n\n" + "\n".join(links)) if links else ""

            message = (
                f"🚨 *Market Debunk — New Short Released!*\n\n"
                f"📌 *Topic:* {title}\n"
                f"💡 *Debunk Thesis:* _{thesis}_"
                f"{links_block}"
                f"{stats_block}"
            )

        # Priority 1: Send actual video file if it exists and is under 50MB (Telegram Bot API limit)
        video_file = Path(video_path) if video_path else None
        if video_file and video_file.is_file():
            file_size_mb = video_file.stat().st_size / (1024 * 1024)
            if file_size_mb <= 49.5:
                log.info("Uploading video (%.1fMB) to Telegram chat: %s...", file_size_mb, chat_id)
                try:
                    with open(video_file, "rb") as vf:
                        resp = requests.post(
                            f"{base_url}/sendVideo",
                            data={
                                "chat_id": chat_id,
                                "caption": message[:1024],  # Telegram caption max length is 1024
                                "parse_mode": "Markdown",
                                "supports_streaming": True,
                            },
                            files={"video": (video_file.name, vf, "video/mp4")},
                            timeout=60,
                        )
                    if resp.status_code == 200:
                        log.info("✓ Video successfully uploaded to Telegram")
                        return True
                    else:
                        log.warning("sendVideo returned %d: %s. Falling back to text message.", resp.status_code, resp.text)
                except Exception as vid_err:
                    log.warning("sendVideo upload failed: %s. Falling back to text message.", vid_err)

        # Priority 2: Fallback to sendMessage
        log.info("Sending text notification to Telegram chat: %s...", chat_id)
        resp = requests.post(
            f"{base_url}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message[:4096],
                "parse_mode": "Markdown",
                "disable_web_page_preview": False,
            },
            timeout=20,
        )
        resp.raise_for_status()
        log.info("✓ Telegram notification sent successfully")
        return True

    except Exception as exc:
        log.error("Telegram notification failed: %s", exc)
        return False
