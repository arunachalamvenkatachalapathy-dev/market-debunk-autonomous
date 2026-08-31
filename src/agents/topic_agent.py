"""
src/agents/topic_agent.py

Phase 1 — Topic Discovery

Rotates through 7 Indian Financial YouTube channels by day of week,
extracts the latest video, downloads its transcript (Tamil/Hinglish/mixed),
and uses Gemini to distil a story_seed object for the script agent.

Channel schedule (0=Monday … 6=Sunday):
  Mon: MONEY PECHU       Tue: PR SUNDAR         Wed: MONEY PURSE
  Thu: TRADE ACHIEVERS   Fri: MARKET DRIVER     Sat: TAMIL NIFTY ANALYSIS
  Sun: ZERO1 BY ZERODHA

Data flow:
  rotate_channel() → resolve_channel_id() → fetch_latest_video()
    → download_transcript() → summarize_to_story_seed()
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
#  Story Seed Extraction (Gemini Summarization — NEW)
# ──────────────────────────────────────────────────────────────────────────────

def summarize_to_story_seed(raw_transcript: str, video_title: str = "") -> dict:
    """
    Pipes the raw (possibly Tamil/Hinglish) transcript through Gemini
    to extract a rich story_seed object for the script agent.

    Returns a dict with:
        - thesis: single controversial English sentence
        - story_seed: {inciting_event, protagonist_flaw, real_world_anchor,
                       concept_name, concept_one_liner}
    """
    if not raw_transcript.strip():
        return _fallback_story_seed(video_title)

    prompt = f"""You are a financial content analyst and creative storytwriter specialising in Indian stock markets.

The following is a raw YouTube video transcript (may be in Tamil, Hindi, Hinglish, or a mix).
Video title: "{video_title}"

TRANSCRIPT:
{raw_transcript[:5000]}

Your task: Extract a story seed to be turned into a cinematic short-form video about finance.

Output ONLY a valid JSON object with exactly these keys (all values in English):
{{
  "thesis": "One sentence (max 25 words): the most controversial or provocative financial claim from this content. Should make viewers say 'wait, really?!'",
  "story_seed": {{
    "inciting_event": "A specific, relatable everyday moment that sets up the story (e.g. 'Arjun checks his mutual fund app and his returns are 0% despite the Nifty being up 12%')",
    "protagonist_flaw": "The common mistake most people make, which Arjun will also make (e.g. 'He trusted his fund manager blindly and never checked the expense ratio')",
    "real_world_anchor": "The actual market fact, company name, or financial event from the transcript that this story is based on (e.g. 'HDFC AMC quietly raised its expense ratio from 1.05% to 1.35% this quarter')",
    "concept_name": "The official finance term being explained (e.g. 'Expense Ratio Drag')",
    "concept_one_liner": "One plain-English sentence explaining what this concept means (e.g. 'Even when markets go up, hidden fund fees quietly eat your profits every year')"
  }}
}}

Output ONLY the JSON. No explanation, no preamble, no markdown fences."""

    # Try Gemini (via Vertex AI)
    try:
        from google import genai
        client = genai.Client(vertexai=True, project="exalted-shape-502013-q5", location="us-central1")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        raw_json = response.text.strip()
        # Strip markdown if present
        if "```" in raw_json:
            raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json, flags=re.MULTILINE)
            raw_json = re.sub(r"\s*```\s*$", "", raw_json, flags=re.MULTILINE)
        result = json.loads(raw_json)
        log.info("Gemini story seed extracted | concept: %s | thesis: %s",
                 result.get("story_seed", {}).get("concept_name", "?"),
                 result.get("thesis", "?"))
        return result
    except Exception as exc:
        log.warning("Gemini story seed extraction failed, falling back to Groq: %s", exc)

    # Groq fallback — simpler thesis only
    if settings.GROQ_API_KEY:
        try:
            from groq import Groq
            client = Groq(api_key=settings.GROQ_API_KEY)
            completion = client.chat.completions.create(
                model=settings.GROQ_FALLBACK_MODEL,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=600,
                temperature=0.7,
            )
            raw_json = completion.choices[0].message.content.strip()
            if "```" in raw_json:
                raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json, flags=re.MULTILINE)
                raw_json = re.sub(r"\s*```\s*$", "", raw_json, flags=re.MULTILINE)
            result = json.loads(raw_json)
            log.info("Groq story seed: %s", result.get("thesis", "?"))
            return result
        except Exception as exc:
            log.error("Groq story seed extraction also failed: %s", exc)

    return _fallback_story_seed(video_title)


def _fallback_story_seed(video_title: str) -> dict:
    """Minimal fallback when all LLM calls fail."""
    return {
        "thesis": video_title or "Indian market analysis and investment insights",
        "story_seed": {
            "inciting_event": "Arjun checks his investment portfolio and finds his returns are far lower than expected",
            "protagonist_flaw": "He trusted conventional advice without understanding the underlying mechanics",
            "real_world_anchor": video_title or "Indian stock market recent movement",
            "concept_name": "Market Mispricing",
            "concept_one_liner": "When prices don't reflect real value, savvy investors profit while others lose"
        }
    }


# ──────────────────────────────────────────────────────────────────────────────
#  Main Entry Point with Cascading Scan
# ──────────────────────────────────────────────────────────────────────────────

def discover_topic(day_override: Optional[int] = None) -> dict:
    """
    Full topic discovery pipeline with cascading fallback across 7 Indian finance channels:
      0. Monday:    MONEY PECHU
      1. Tuesday:   PR SUNDAR
      2. Wednesday: MONEY PURSE
      3. Thursday:  TRADE ACHIEVERS
      4. Friday:    MARKET DRIVER
      5. Saturday:  TAMIL NIFTY ANALYSIS
      6. Sunday:    ZERO1 BY ZERODHA

    Starts at today's scheduled channel. If no video is found or transcript
    extraction fails, automatically cascades to the next channel in the rotation
    until a valid topic & transcript are found.
    """
    start_day = day_override if day_override is not None else datetime.now().weekday()
    num_channels = len(settings.CHANNEL_REGISTRY)
    attempted_channels = []

    for offset in range(num_channels):
        current_day = (start_day + offset) % num_channels
        channel_name = settings.CHANNEL_REGISTRY[current_day]
        attempted_channels.append(channel_name)

        if offset == 0:
            log.info("🎯 Primary scheduled channel (Day %d): %s", current_day, channel_name)
        else:
            log.warning("🔄 Cascading to fallback channel %d/%d (Day %d): %s", offset + 1, num_channels, current_day, channel_name)

        video_meta = fetch_latest_video(channel_name)
        if not video_meta:
            log.warning("⚠️ No latest video found for '%s' — cascading...", channel_name)
            continue

        video_id = video_meta.get("video_id")
        video_title = video_meta.get("title", "")

        if not video_id:
            log.warning("⚠️ Invalid video metadata for '%s' — cascading...", channel_name)
            continue

        transcript = download_transcript(video_id)
        if not transcript or not transcript.strip():
            log.warning("⚠️ Empty transcript for [%s] '%s' on '%s' — cascading...", video_id, video_title, channel_name)
            continue

        seed_data = summarize_to_story_seed(transcript, video_title)
        thesis = seed_data.get("thesis", video_title)
        story_seed = seed_data.get("story_seed", {})

        log.info("✅ Successfully discovered topic & story seed from '%s' (Video: %s)", channel_name, video_id)
        return {
            "channel": channel_name,
            "video_id": video_id,
            "video_title": video_title,
            "thesis": thesis,
            "story_seed": story_seed,
            "transcript_length": len(transcript),
        }

    raise RuntimeError(
        f"All 7 channels failed in cascading scan. Attempted: {', '.join(attempted_channels)}"
    )

