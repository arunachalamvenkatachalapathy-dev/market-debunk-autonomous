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
    if not settings.ENABLE_TELEGRAM:
        log.info("Telegram notifications disabled — skipping")
        return False

    token = (settings.TELEGRAM_BOT_TOKEN or "").strip()
    chat_id = (settings.TELEGRAM_CHAT_ID or "").strip()

    if not token or not chat_id:
        log.warning("Telegram credentials missing — notification skipped")
        return False

    try:
        import requests

        base_url = f"https://api.telegram.org/bot{token}"

        if custom_message:
            message = custom_message
        else:
            links = []
            if youtube_url:
                links.append(f"🎬 Watch on YouTube Shorts:\n{youtube_url}")
            if instagram_url:
                links.append(f"📸 Watch on Instagram Reel:\n{instagram_url}")
            if facebook_url:
                links.append(f"📘 Watch on Facebook Reel:\n{facebook_url}")

            links_block = ("\n\n" + "\n\n".join(links)) if links else ""

            message = (
                f"🚨 Market Debunk — New Short Released!\n\n"
                f"📌 Topic: {title}\n"
                f"💡 Debunk Thesis: {thesis}"
                f"{links_block}"
            )

        resp = requests.post(
            f"{base_url}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": message[:4096],
                "disable_web_page_preview": False,
            },
            timeout=20,
        )
        resp.raise_for_status()
        log.info("✓ Telegram notification with video links sent successfully")
        return True

    except Exception as exc:
        log.error("Telegram notification failed: %s", exc)
        return False
