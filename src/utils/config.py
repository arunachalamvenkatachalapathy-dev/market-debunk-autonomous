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
    GEMMA_FALLBACK_MODEL: str = _get("GEMMA_FALLBACK_MODEL", required=False) or "gemma-3-27b-it"

    # ── Gemini Live (Voice Synthesis) ─────────────────────────────
    GEMINI_LIVE_API_KEY: str = _get("GEMINI_LIVE_API_KEY", required=False) or ""

    # ── Gemini Image (Cloud GCP — image generation ONLY) ──────────
    GEMINI_IMAGE_API_KEY: str = _get("GEMINI_IMAGE_API_KEY", required=False) or ""

    # Groq Fallback
    GROQ_API_KEY: str = _get("GROQ_API_KEY", required=False) or ""
    GROQ_FALLBACK_MODEL: str = _get("GROQ_FALLBACK_MODEL", required=False) or "llama3-8b-8192"

    # Transcript provider
    RAPIDAPI_KEY: str = _get("RAPIDAPI_KEY", required=False) or ""
    SERPAPI_KEY: str = _get("SERPAPI_KEY", required=False) or ""

    # ── Pexels (Background Footage) ───────────────────────────────
    PEXELS_API_KEY: str = _get("PEXELS_API_KEY", required=False) or ""

    # ── YouTube Publishing ─────────────────────────────────────────
    ENABLE_YT_UPLOAD: bool = (_get("ENABLE_YT_UPLOAD", default="true") or "true").lower() == "true"
    ALLOW_PUBLICATION: bool = (_get("ALLOW_PUBLICATION", default="true") or "true").lower() == "true"
    YT_CLIENT_ID: str = _get("YT_CLIENT_ID", default="") or ""
    YT_CLIENT_SECRET: str = _get("YT_CLIENT_SECRET", default="") or ""
    YT_REFRESH_TOKEN: str = _get("YT_REFRESH_TOKEN", default="") or ""

    # ── Telegram Notifications ─────────────────────────────────────
    ENABLE_TELEGRAM: bool = (_get("ENABLE_TELEGRAM", default="true") or "true").lower() == "true"
    TELEGRAM_BOT_TOKEN: str = _get("TELEGRAM_BOT_TOKEN", default="") or ""
    TELEGRAM_CHAT_ID: str = _get("TELEGRAM_CHAT_ID", default="") or ""

    # ── Instagram Graph API publishing ───────────────────────────
    ENABLE_INSTAGRAM: bool = _get("ENABLE_INSTAGRAM", default="false").lower() == "true"
    INSTAGRAM_ACCESS_TOKEN: str = _get("INSTAGRAM_ACCESS_TOKEN", default="") or ""
    INSTAGRAM_USER_ID: str = _get("INSTAGRAM_USER_ID", default="") or ""
    INSTAGRAM_VIDEO_URL: str = _get("INSTAGRAM_VIDEO_URL", default="") or ""
    INSTAGRAM_GRAPH_VERSION: str = _get("INSTAGRAM_GRAPH_VERSION", default="v23.0") or "v23.0"

    # ── Video Settings ─────────────────────────────────────────────
    VIDEO_WIDTH: int = int(_get("VIDEO_WIDTH", default="1080"))
    VIDEO_HEIGHT: int = int(_get("VIDEO_HEIGHT", default="1920"))
    VIDEO_FPS: int = int(_get("VIDEO_FPS", default="30"))
    VIDEO_DURATION_TARGET: int = int(_get("VIDEO_DURATION_TARGET", default="60"))
    MIN_VIDEO_DURATION: int = int(_get("MIN_VIDEO_DURATION", default="40"))
    MAX_VIDEO_DURATION: int = int(_get("MAX_VIDEO_DURATION", default="90"))
    VISUAL_GENERATION_DELAY_SECONDS: float = float(_get("VISUAL_GENERATION_DELAY_SECONDS", default="10"))
    BGM_VOLUME_DB: float = float(_get("BGM_VOLUME_DB", default="-14"))
    BGM_MIX_RETRIES: int = int(_get("BGM_MIX_RETRIES", default="3"))
    BGM_MIX_REQUIRED: bool = (_get("BGM_MIX_REQUIRED", default="true") or "true").lower() == "true"
    BGM_MIN_BYTES: int = int(_get("BGM_MIN_BYTES", default="1000000"))

    # ── Voice Settings ─────────────────────────────────────────────
    VOICE_NAME: str = _get("VOICE_NAME", default="en-IN-Chirp3-HD-Orus") or "en-IN-Chirp3-HD-Orus"
    VOICE_SPEAKING_RATE: float = float(_get("VOICE_SPEAKING_RATE", default="1.04"))
    VOICE_PITCH: float = float(_get("VOICE_PITCH", default="-0.5"))

    # ── Deduplication ─────────────────────────────────────────────
    DEDUP_THRESHOLD: float = float(_get("DEDUP_THRESHOLD", default="0.75"))
    DEDUP_WINDOW_DAYS: int = int(_get("DEDUP_WINDOW_DAYS", default="30"))

    # ── Paths ─────────────────────────────────────────────────────
    ROOT_DIR: Path = Path(__file__).resolve().parents[2]
    DATA_DIR: Path = ROOT_DIR / "data"
    OUTPUT_DIR: Path = ROOT_DIR / "output"
    ASSETS_DIR: Path = ROOT_DIR / "assets"
    BGM_PATH: Path = ASSETS_DIR / "bgm" / "background.mp3"
    BRAND_MARK_PATH: Path = Path(_get("BRAND_MARK_PATH", default=str(ASSETS_DIR / "brand_protection.png")))
    BRAND_MARK_WIDTH: int = int(_get("BRAND_MARK_WIDTH", default="150"))
    BRAND_MARK_PADDING: int = int(_get("BRAND_MARK_PADDING", default="30"))

    # ── Subtitle Style ────────────────────────────────────────────
    SUBTITLE_FONT: str = "Arial"
    SUBTITLE_FONT_SIZE: int = 96
    SUBTITLE_PRIMARY_COLOR: str = "&H00FFFFFF"   # white
    SUBTITLE_OUTLINE_COLOR: str = "&H00000000"   # black
    SUBTITLE_MARGIN_V: int = 470                  # safe above Shorts handle/description UI

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
    if not settings.RAPIDAPI_KEY:
        warnings.append("RAPIDAPI_KEY missing — transcript discovery will use yt-dlp fallback")
    if not settings.SERPAPI_KEY:
        warnings.append("SERPAPI_KEY missing — market-news fallback disabled")
    if settings.ENABLE_INSTAGRAM and not all((settings.INSTAGRAM_ACCESS_TOKEN, settings.INSTAGRAM_USER_ID, settings.INSTAGRAM_VIDEO_URL)):
        warnings.append("Instagram enabled but credentials/video URL are incomplete — Instagram upload will be skipped")
    if not settings.GEMINI_IMAGE_API_KEY:
        warnings.append("GEMINI_IMAGE_API_KEY missing — AI image generation disabled")
    if not settings.GEMINI_LIVE_API_KEY:
        warnings.append("GEMINI_LIVE_API_KEY missing — voice will use gTTS fallback")

    # Ensure output dir exists
    settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    return warnings
