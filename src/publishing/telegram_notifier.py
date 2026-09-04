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

    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        log.warning("Telegram credentials missing — notification skipped")
        return False

    try:
        import requests

        base_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"

        if custom_message:
            message = custom_message
        else:
            # Build default message
            stats_block = ""
            if run_stats:
                stats_block = (
                    f"\n📊 Stats:\n"
                    f"  • Total duration: {run_stats.get('total_duration', 0):.1f}s\n"
                    f"  • Visual sources: {run_stats.get('visual_sources', '')}\n"
                    f"  • Voice: {run_stats.get('voice', 'Google Cloud Chirp3 Fenrir')}"
                )

            yt_line = f"\n🎬 YouTube: {youtube_url}" if youtube_url else ""
            ig_line = f"\n📸 Instagram: {instagram_url}" if instagram_url else ""
            fb_line = f"\n📘 Facebook: {facebook_url}" if facebook_url else ""

            message = (
                f"✅ *Market Debunk — New Short Ready!*\n\n"
                f"📌 *Title:* {title}\n"
                f"💡 *Thesis:* _{thesis}_"
                f"{yt_line}"
                f"{ig_line}"
                f"{fb_line}"
                f"{stats_block}"
            )

        resp = requests.post(
            f"{base_url}/sendMessage",
            json={"chat_id": settings.TELEGRAM_CHAT_ID, "text": message},
            timeout=15,
        )
        resp.raise_for_status()
        log.info("✓ Telegram notification sent")
        return True

    except Exception as exc:
        log.error("Telegram notification failed: %s", exc)
        return False
