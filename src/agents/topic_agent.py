"""
src/agents/topic_agent.py

Phase 1 — Topic Discovery

Rotates through 7 Indian Financial YouTube channels by day of week,
extracts the latest video, downloads its transcript (Tamil/Hinglish/mixed),
and uses Gemini to distil a single controversial thesis in English.

Channel schedule (0=Monday … 6=Sunday):
  Mon: MONEY PECHU       Tue: PR SUNDAR         Wed: MONEY PURSE
  Thu: TRADE ACHIEVERS   Fri: MARKET DRIVER     Sat: TAMIL NIFTY ANALYSIS
  Sun: ZERO1 BY ZERODHA

Data flow:
  rotate_channel() → resolve_channel_id() → fetch_latest_video()
    → download_transcript() → summarize_to_thesis()
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Optional

import feedparser
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="topic_discovery")

_CHANNEL_IDS_PATH = settings.DATA_DIR / "channel_ids.json"


# ──────────────────────────────────────────────────────────────────────────────
#  Channel ID Resolution
# ──────────────────────────────────────────────────────────────────────────────

def _load_channel_id_cache() -> dict[str, Optional[str]]:
    if _CHANNEL_IDS_PATH.exists():
        with open(_CHANNEL_IDS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {name: None for name in settings.CHANNEL_REGISTRY}


def _save_channel_id_cache(cache: dict[str, Optional[str]]) -> None:
    with open(_CHANNEL_IDS_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def resolve_channel_id(channel_name: str) -> Optional[str]:
    """
    Returns the YouTube channel ID for a given channel name.
    Tries the local cache first; on a miss, searches via YouTube Data API v3.
    If YT_API_KEY is absent, returns None (caller will use RSS name-based URL).
    """
    cache = _load_channel_id_cache()

    if cache.get(channel_name):
        return cache[channel_name]

    if not settings.YT_API_KEY:
        log.warning("YT_API_KEY not set — cannot resolve channel ID for '%s'", channel_name)
        return None

    log.info("Resolving channel ID for '%s' via YouTube API …", channel_name)
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "q": channel_name,
        "type": "channel",
        "maxResults": 3,
        "key": settings.YT_API_KEY,
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if items:
            channel_id = items[0]["id"]["channelId"]
            cache[channel_name] = channel_id
            _save_channel_id_cache(cache)
            log.info("Resolved '%s' → %s", channel_name, channel_id)
            return channel_id
    except Exception as exc:
        log.error("Failed to resolve channel ID for '%s': %s", channel_name, exc)

    return None


# ──────────────────────────────────────────────────────────────────────────────
#  Day-Based Channel Rotation
# ──────────────────────────────────────────────────────────────────────────────

def rotate_channel(day_override: Optional[int] = None) -> str:
    """
    Returns the channel name to use for today.
    day_override (0-6) lets you force a specific day (useful for testing).
    """
    day = day_override if day_override is not None else datetime.now().weekday()
    channel = settings.CHANNEL_REGISTRY[day % 7]
    log.info("Day %d → using channel: %s", day, channel)
    return channel


# ──────────────────────────────────────────────────────────────────────────────
#  Latest Video Fetching
# ──────────────────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_latest_video_api(channel_id: str) -> Optional[dict]:
    """Primary: YouTube Data API v3."""
    url = "https://www.googleapis.com/youtube/v3/search"
    params = {
        "part": "snippet",
        "channelId": channel_id,
        "order": "date",
        "type": "video",
        "maxResults": 1,
        "key": settings.YT_API_KEY,
    }
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        return None
    item = items[0]
    return {
        "video_id": item["id"]["videoId"],
        "title": item["snippet"]["title"],
        "published_at": item["snippet"]["publishedAt"],
    }


def _fetch_latest_video_rss(channel_id: str) -> Optional[dict]:
    """Fallback: YouTube RSS feed (no API key needed)."""
    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    try:
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            return None
        entry = feed.entries[0]
        video_id = entry.get("yt_videoid") or re.search(r"v=([^&]+)", entry.get("link", ""))
        if hasattr(video_id, "group"):
            video_id = video_id.group(1)
        return {
            "video_id": str(video_id),
            "title": entry.get("title", ""),
            "published_at": entry.get("published", ""),
        }
    except Exception as exc:
        log.error("RSS fetch failed for channel %s: %s", channel_id, exc)
        return None


def fetch_latest_video(channel_name: str) -> Optional[dict]:
    """
    Fetches the latest video metadata for a channel.
    Returns dict with keys: video_id, title, published_at
    """
    channel_id = resolve_channel_id(channel_name)

    # Try API first
    if channel_id and settings.YT_API_KEY:
        try:
            video = _fetch_latest_video_api(channel_id)
            if video:
                log.info("Found video via API: [%s] %s", video["video_id"], video["title"])
                return video
        except Exception as exc:
            log.warning("API fetch failed, falling back to RSS: %s", exc)

    # RSS fallback (requires channel_id)
    if channel_id:
        video = _fetch_latest_video_rss(channel_id)
        if video:
            log.info("Found video via RSS: [%s] %s", video["video_id"], video["title"])
            return video

    log.error("Could not fetch latest video for channel: %s", channel_name)
    return None


# ──────────────────────────────────────────────────────────────────────────────
#  Transcript Download
# ──────────────────────────────────────────────────────────────────────────────

def download_transcript(video_id: str) -> str:
    """
    Downloads the YouTube transcript (auto-generated or manual).
    Handles Tamil, Hindi, Hinglish, or mixed-language transcripts.
    Returns the raw concatenated text.
    """
    log.info("Downloading transcript for video: %s", video_id)

    # Priority: Tamil → Hindi → English auto-generated
    lang_priority = ["ta", "hi", "en-IN", "en"]

    try:
        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(video_id)

        for lang in lang_priority:
            try:
                transcript = transcript_list.find_transcript([lang])
                entries = transcript.fetch()
                raw = " ".join(e["text"] for e in entries)
                log.info("Downloaded transcript (%s): %d chars", lang, len(raw))
                return raw
            except Exception:
                continue

        # Try any available transcript
        for t in transcript_list:
            try:
                entries = t.fetch()
                raw = " ".join(e["text"] for e in entries)
                log.info("Downloaded transcript (%s): %d chars", t.language_code, len(raw))
                return raw
            except Exception:
                continue

    except Exception as exc:
        log.warning("youtube_transcript_api failed (%s) — trying yt-dlp fallback", exc)

    # yt-dlp fallback
    return _download_transcript_ytdlp(video_id)


def _download_transcript_ytdlp(video_id: str) -> str:
    """Last-resort transcript extraction via yt-dlp."""
    import subprocess
    import tempfile

    import sys

    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m", "yt_dlp",
                    "--write-auto-sub",
                    "--sub-lang", "ta,hi,en",
                    "--skip-download",
                    "--sub-format", "vtt",
                    "-o", f"{tmpdir}/%(id)s",
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
            # Find any .vtt file
            vtt_files = list(Path(tmpdir).glob("*.vtt"))
            if vtt_files:
                raw = vtt_files[0].read_text(encoding="utf-8")
                # Strip VTT formatting
                lines = [
                    re.sub(r"<[^>]+>", "", line).strip()
                    for line in raw.split("\n")
                    if line.strip() and not line.startswith("WEBVTT")
                    and not re.match(r"\d{2}:\d{2}", line)
                    and not "-->" in line
                ]
                return " ".join(filter(None, lines))
        except Exception as exc:
            log.error("yt-dlp transcript extraction failed: %s", exc)

    log.warning("All transcript methods failed — returning empty string")
    return ""


# ──────────────────────────────────────────────────────────────────────────────
#  Thesis Extraction (Gemini Summarization)
# ──────────────────────────────────────────────────────────────────────────────

def summarize_to_thesis(raw_transcript: str, video_title: str = "") -> str:
    """
    Pipes the raw (possibly Tamil/Hinglish) transcript through Gemini
    to extract a single, controversial English thesis sentence.
    Falls back to a Groq-based summary if Gemini image key is unavailable.
    """
    if not raw_transcript.strip():
        return video_title or "Market trends and financial analysis"

    prompt = f"""You are a financial content analyst specialising in Indian stock markets.

The following is a raw YouTube video transcript (may be in Tamil, Hindi, Hinglish, or a mix).
Video title: "{video_title}"

TRANSCRIPT:
{raw_transcript[:4000]}

Your task:
1. Identify the SINGLE most controversial or provocative financial thesis from this content.
2. Translate it cleanly into English if it is in another language.
3. Express it as ONE sentence (max 30 words) that will make viewers say "wait, really?!"
4. Focus on stocks, sectors, indices, companies, or economic policies discussed.

Output ONLY the thesis sentence. No explanation, no preamble, no quotes.
"""

    # Try Gemini (via Vertex AI)
    try:
        from google import genai
        client = genai.Client(vertexai=True, project="exalted-shape-502013-q5", location="us-central1")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        thesis = response.text.strip().strip('"').strip("'")
        log.info("Gemini thesis: %s", thesis)
        return thesis
    except Exception as exc:
        log.warning("Gemini summarization failed, falling back to Groq: %s", exc)

    # Groq fallback
    if settings.GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=settings.GROQ_API_KEY)
            completion = client.chat.completions.create(
                model=settings.GROQ_FALLBACK_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.7,
            )
            thesis = completion.choices[0].message.content.strip()
            log.info("Groq thesis: %s", thesis)
            return thesis
        except Exception as exc:
            log.error("Groq summarization also failed: %s", exc)

    return video_title or "Indian market analysis and investment insights"


# ──────────────────────────────────────────────────────────────────────────────
#  Main Entry Point
# ──────────────────────────────────────────────────────────────────────────────

def discover_topic(day_override: Optional[int] = None) -> dict:
    """
    Full topic discovery pipeline.
    Returns dict with keys: channel, video_id, video_title, thesis
    """
    channel_name = rotate_channel(day_override)
    video_meta = fetch_latest_video(channel_name)

    if not video_meta:
        raise RuntimeError(f"Could not fetch any video from channel: {channel_name}")

    video_id = video_meta["video_id"]
    video_title = video_meta["title"]

    transcript = download_transcript(video_id)
    thesis = summarize_to_thesis(transcript, video_title)

    return {
        "channel": channel_name,
        "video_id": video_id,
        "video_title": video_title,
        "thesis": thesis,
        "transcript_length": len(transcript),
    }
