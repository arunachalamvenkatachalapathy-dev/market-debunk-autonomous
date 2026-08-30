"""
src/utils/config.py
Centralised settings loader. Reads from .env file (local dev) or
environment variables (GitHub Actions secrets). Validates all required
keys at startup and raises clear errors if any are missing.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Load .env if present (local dev). GitHub Actions sets env vars directly.
_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_ENV_PATH, override=False)


def _get(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    val = os.environ.get(key, default)
    if required and not val:
        raise EnvironmentError(
            f"[Config] Required environment variable '{key}' is missing.\n"
            f"  → Set it in your .env file (local) or GitHub Secrets (CI)."
        )
    return val


class Settings:
    """All pipeline settings, validated at import time."""

    # ── YouTube Data API ─────────────────────────────────────────
    YT_API_KEY: str = _get("YT_API_KEY", required=False) or ""

    # ── Script Generation (Gemma via Google AI Studio) ────────────
    GEMINI_SCRIPT_API_KEY: str = _get("GEMINI_SCRIPT_API_KEY", required=False) or ""

    # ── Gemini Live (Voice Synthesis) ─────────────────────────────
    GEMINI_LIVE_API_KEY: str = _get("GEMINI_LIVE_API_KEY", required=False) or ""

    # ── Gemini Image (Cloud GCP — image generation ONLY) ──────────
    GEMINI_IMAGE_API_KEY: str = _get("GEMINI_IMAGE_API_KEY", required=False) or ""

    # ── Pexels (Background Footage) ───────────────────────────────
    PEXELS_API_KEY: str = _get("PEXELS_API_KEY", required=False) or ""

    # ── YouTube Publishing ─────────────────────────────────────────
    ENABLE_YT_UPLOAD: bool = _get("ENABLE_YT_UPLOAD", default="false").lower() == "true"
    YT_CLIENT_ID: str = _get("YT_CLIENT_ID", default="") or ""
    YT_CLIENT_SECRET: str = _get("YT_CLIENT_SECRET", default="") or ""
    YT_REFRESH_TOKEN: str = _get("YT_REFRESH_TOKEN", default="") or ""

    # ── Telegram Notifications ─────────────────────────────────────
    ENABLE_TELEGRAM: bool = _get("ENABLE_TELEGRAM", default="false").lower() == "true"
    TELEGRAM_BOT_TOKEN: str = _get("TELEGRAM_BOT_TOKEN", default="") or ""
    TELEGRAM_CHAT_ID: str = _get("TELEGRAM_CHAT_ID", default="") or ""

    # ── Video Settings ─────────────────────────────────────────────
    VIDEO_WIDTH: int = int(_get("VIDEO_WIDTH", default="1080"))
    VIDEO_HEIGHT: int = int(_get("VIDEO_HEIGHT", default="1920"))
    VIDEO_FPS: int = int(_get("VIDEO_FPS", default="30"))
    VIDEO_DURATION_TARGET: int = int(_get("VIDEO_DURATION_TARGET", default="60"))

    # ── Deduplication ─────────────────────────────────────────────
    DEDUP_THRESHOLD: float = float(_get("DEDUP_THRESHOLD", default="0.75"))
    DEDUP_WINDOW_DAYS: int = int(_get("DEDUP_WINDOW_DAYS", default="7"))

    # ── Paths ─────────────────────────────────────────────────────
    ROOT_DIR: Path = Path(__file__).resolve().parents[2]
    DATA_DIR: Path = ROOT_DIR / "data"
    OUTPUT_DIR: Path = ROOT_DIR / "output"
    ASSETS_DIR: Path = ROOT_DIR / "assets"
    BGM_PATH: Path = ASSETS_DIR / "bgm" / "background.mp3"

    # ── Subtitle Style ────────────────────────────────────────────
    SUBTITLE_FONT: str = "Arial"
    SUBTITLE_FONT_SIZE: int = 112
    SUBTITLE_PRIMARY_COLOR: str = "&H00FFFFFF"   # white
    SUBTITLE_OUTLINE_COLOR: str = "&H00000000"   # black
    SUBTITLE_MARGIN_V: int = 120                  # pixels from bottom

    # ── YouTube Channel Registry (day-indexed, 0=Monday) ─────────
    CHANNEL_REGISTRY: list[str] = [
        "MONEY PECHU",           # Monday
        "PR SUNDAR",             # Tuesday
        "MONEY PURSE",           # Wednesday
        "TRADE ACHIEVERS",       # Thursday
        "MARKET DRIVER",         # Friday
        "TAMIL NIFTY ANALYSIS",  # Saturday
        "ZERO1 BY ZERODHA",      # Sunday
    ]


settings = Settings()


def validate_for_run() -> list[str]:
    """
    Returns a list of warnings about missing optional keys.
    Raises EnvironmentError for hard-required keys.
    """
    warnings: list[str] = []

    if not settings.YT_API_KEY:
        warnings.append("YT_API_KEY missing — will use RSS feed fallback only")
    if not settings.GROQ_API_KEY:
        raise EnvironmentError("GROQ_API_KEY is required for script generation")
    if not settings.PEXELS_API_KEY:
        warnings.append("PEXELS_API_KEY missing — will use Pollinations image fallback")
    if not settings.GEMINI_IMAGE_API_KEY:
        warnings.append("GEMINI_IMAGE_API_KEY missing — AI image generation disabled")
    if not settings.GEMINI_LIVE_API_KEY:
        warnings.append("GEMINI_LIVE_API_KEY missing — voice will use gTTS fallback")

    # Ensure output dir exists
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    return warnings
