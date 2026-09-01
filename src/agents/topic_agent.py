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
import os

import json
import re
import time
import xml.etree.ElementTree as ET
import http.cookiejar
from datetime import datetime
from pathlib import Path
from typing import Optional

import feedparser
import requests
from tenacity import retry, stop_after_attempt, wait_exponential
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound

from src.agents import evaluator
from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="topic_discovery")

_CHANNEL_IDS_PATH = settings.DATA_DIR / "channel_ids.json"
_SERP_QUERIES = ("nifty50", "sensex", "share market")


# ──────────────────────────────────────────────────────────────────────────────
#  Channel ID Resolution
# ──────────────────────────────────────────────────────────────────────────────

def _load_channel_id_cache() -> dict[str, Optional[str]]:
    """Loads cached channel IDs or returns hardcoded defaults."""
    cache = {
        "MONEY PECHU": "UC7fQFl37yAOaPaoxQm-TqSA",
        "PR SUNDAR": "UCS2NdYUmv_PUyyKeDAo5zYA",
        "MONEY PURSE": "UChBT5TlUeG68PKvJSg6MkqQ",
        "TRADE ACHIEVERS": "UCzk4zJEoZMnjvpoN0HlKjHQ",
        "MARKET DRIVER": "UCo5CAieenL0ExXzvjzs17QQ",
        "TAMIL NIFTY ANALYSIS": "UCft3VdKoq4HNBYd4MRnQF6Q",
        "ZERO1 BY ZERODHA": "UCUUlw3anBIkbW9W44Y-eURw"
    }
    if _CHANNEL_IDS_PATH.exists():
        with open(_CHANNEL_IDS_PATH, "r", encoding="utf-8") as f:
            cache.update(json.load(f))
    return cache


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


def _fetch_latest_video_ytdlp(channel_id: str) -> Optional[dict]:
    """Fallback: yt-dlp to scrape latest video (bypasses RSS IP blocks)."""
    try:
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'extract_flat': True,
            'playlist_items': '1', # Get only the latest 1 video
            'force_generic_extractor': False,
        }
        uploads_playlist_id = f"UU{channel_id[2:]}" if channel_id.startswith("UC") else channel_id
        url = f"https://www.youtube.com/playlist?list={uploads_playlist_id}"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info and info['entries']:
                entry = info['entries'][0]
                video_id = entry.get("id") or entry.get("url")
                if not video_id or video_id == channel_id:
                    log.warning("yt-dlp returned an invalid video id for channel %s: %s", channel_id, video_id)
                    return None
                return {
                    "video_id": video_id,
                    "title": entry.get("title", ""),
                    "published_at": "", # We can't easily get date from flat extract, but it's not strictly needed
                }
    except Exception as exc:
        log.error("yt-dlp fetch failed for channel %s: %s", channel_id, exc)
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
            log.warning("API fetch failed, falling back to yt-dlp: %s", exc)

    # yt-dlp fallback (requires channel_id)
    if channel_id:
        video = _fetch_latest_video_ytdlp(channel_id)
        if video:
            log.info("Found video via yt-dlp: [%s] %s", video["video_id"], video["title"])
            return video

    log.error("Could not fetch latest video for channel: %s", channel_name)
    return None


# ──────────────────────────────────────────────────────────────────────────────
#  Transcript Download
# ──────────────────────────────────────────────────────────────────────────────

def download_transcript(video_id: str) -> str:
    """
    Downloads the YouTube transcript using the RapidAPI WEBVTT endpoint.
    Handles Tamil, Hindi, Hinglish, or mixed-language transcripts.
    Returns the raw concatenated text.
    """
    log.info("Downloading transcript via RapidAPI for video: %s", video_id)

    # Priority: Tamil -> Hindi -> English
    lang_priority = ["ta", "hi", "en-IN", "en", "auto"]

    if not settings.RAPIDAPI_KEY:
        log.warning("RAPIDAPI_KEY missing. Skipping RapidAPI transcript provider.")
        return _download_transcript_ytdlp(video_id, "cookies.txt" if os.path.exists("cookies.txt") else None)
    
    headers = {
        'X-RapidAPI-Key': settings.RAPIDAPI_KEY,
        'X-RapidAPI-Host': 'youtube-captions-transcript-subtitles-video-combiner.p.rapidapi.com'
    }
    
    url = f"https://youtube-captions-transcript-subtitles-video-combiner.p.rapidapi.com/download-webvtt/{video_id}"

    for lang in lang_priority:
        try:
            querystring = {"language": lang, "response_mode": "default"}
            response = requests.get(url, headers=headers, params=querystring, timeout=15)
            
            if response.status_code == 200 and "WEBVTT" in response.text:
                # Parse WEBVTT into raw text
                lines = response.text.split('\n')
                raw_text = []
                for line in lines:
                    line = line.strip()
                    # Skip empty lines, timestamps, WEBVTT headers, and metadata
                    if not line or '-->' in line or line == 'WEBVTT' or line.startswith('Kind:') or line.startswith('Language:') or line.startswith('Style:'):
                        continue
                    # Remove any inline styling like <c.color> or <b>
                    line = re.sub(r'<[^>]+>', '', line)
                    if line not in raw_text[-3:]: # Basic deduplication
                        raw_text.append(line)
                
                final_text = " ".join(raw_text)
                log.info("Downloaded transcript (%s) via RapidAPI: %d chars", lang, len(final_text))
                if len(final_text) > 50:
                    return final_text
        except Exception as exc:
            log.warning("RapidAPI failed for lang %s: %s", lang, exc)
            continue

    log.error("RapidAPI exhausted all languages. Attempting ultimate yt-dlp fallback.")
    return _download_transcript_ytdlp(video_id, "cookies.txt" if os.path.exists("cookies.txt") else None)

def _download_transcript_ytdlp(video_id: str, cookies_path: Optional[str] = None) -> str:
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
                ]
                + (["--cookies", cookies_path] if cookies_path else [])
                + [url],
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

    prompt = f"""You are the Market Debunk research desk: financial content analyst, fact checker,
story editor, and short-form retention strategist specialising in Indian stock markets.

The following is a raw YouTube video transcript (may be in Tamil, Hindi, Hinglish, or a mix).
Video title: "{video_title}"

TRANSCRIPT:
{raw_transcript[:5000]}

Your task: Extract a story seed to be turned into a cinematic short-form video about finance.

Anti-hallucination rules:
- Use only claims, companies, sectors, events, or concepts supported by the transcript/title.
- Do not invent exact percentages, dates, prices, index levels, earnings figures, laws, or quotes.
- If the transcript is vague, write qualitative evidence instead of pretending certainty.
- The thesis must be provocative but still defensible.
- The story_seed should give the script agent concrete props and situations, not generic advice.

Output ONLY a valid JSON object with exactly these keys (all values in English):
{{
  "thesis": "One sentence (max 25 words): the most controversial or provocative financial claim from this content. Should make viewers say 'wait, really?!'",
  "story_seed": {{
    "inciting_event": "A specific, relatable everyday moment that sets up the story (e.g. 'Arjun checks his mutual fund app and his returns are 0% despite the Nifty being up 12%')",
    "protagonist_flaw": "The common mistake most people make, which Arjun will also make (e.g. 'He trusted his fund manager blindly and never checked the expense ratio')",
    "real_world_anchor": "The actual market fact, company name, or financial event from the transcript that this story is based on (e.g. 'HDFC AMC quietly raised its expense ratio from 1.05% to 1.35% this quarter')",
    "concept_name": "The official finance term being explained (e.g. 'Expense Ratio Drag')",
    "concept_one_liner": "One plain-English sentence explaining what this concept means (e.g. 'Even when markets go up, hidden fund fees quietly eat your profits every year')",
    "visual_evidence": "One concrete non-branded visual object that can appear on screen, such as a blurred app chart, invoice, calculator, newspaper-like clipping, or marked notebook"
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
            "concept_one_liner": "When prices don't reflect real value, savvy investors profit while others lose",
            "visual_evidence": "a blurred portfolio chart and marked notebook on a desk"
        }
    }


def _fetch_serp_news(query: str) -> Optional[dict]:
    """Use SerpApi Google News only after all seven channel candidates fail."""
    if not settings.SERPAPI_KEY:
        return None
    response = requests.get(
        "https://serpapi.com/search.json",
        params={
            "engine": "google_news",
            "q": query,
            "api_key": settings.SERPAPI_KEY,
            "gl": "in",
            "hl": "en",
        },
        timeout=20,
    )
    response.raise_for_status()
    for item in response.json().get("news_results", []):
        title = (item.get("title") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        if not title or evaluator.is_duplicate(title)[0]:
            continue
        source = item.get("source") or "market news"
        date = item.get("date") or ""
        raw_text = f"{title}. {snippet} Source: {source}. Published: {date}."
        return {
            "channel": "SERPAPI market news",
            "video_id": "",
            "video_title": title,
            "raw_text": raw_text,
        }
    return None


def _discover_from_serp() -> Optional[dict]:
    for query in _SERP_QUERIES:
        try:
            candidate = _fetch_serp_news(query)
            if not candidate:
                continue
            seed_data = summarize_to_story_seed(candidate["raw_text"], candidate["video_title"])
            return {
                **{key: candidate[key] for key in ("channel", "video_id", "video_title")},
                "thesis": seed_data.get("thesis", candidate["video_title"]),
                "story_seed": seed_data.get("story_seed", {}),
                "transcript_length": len(candidate["raw_text"]),
            }
        except Exception as exc:
            log.warning("SERPAPI query '%s' failed: %s", query, exc)
    return None


# ──────────────────────────────────────────────────────────────────────────────
#  Main Entry Point
# ──────────────────────────────────────────────────────────────────────────────

def discover_topic(day_override: Optional[int] = None) -> dict:
    """
    Full topic discovery pipeline with cascading fallback.
    Starts with the channel of the day, and if it fails (no video or empty transcript),
    cascades to the next channel in the rotation until a valid topic is found.
    
    Returns dict with keys: channel, video_id, video_title, thesis, story_seed, transcript_length
    """
    start_day = day_override if day_override is not None else datetime.now().weekday()
    title_only_candidate: Optional[dict] = None
    
    for offset in range(7):
        current_day_index = (start_day + offset) % 7
        channel_name = settings.CHANNEL_REGISTRY[current_day_index]
        
        log.info("--- Attempt %d/7: Scanning channel '%s' ---", offset + 1, channel_name)
        
        try:
            video_meta = fetch_latest_video(channel_name)

            if not video_meta:
                log.warning("No video found for %s. Cascading to next channel...", channel_name)
                continue

            video_id = video_meta["video_id"]
            video_title = video_meta["title"]
            if evaluator.is_source_video_used(video_id):
                log.info("Already-used source video %s. Cascading...", video_id)
                continue
            if title_only_candidate is None:
                title_only_candidate = {
                    "channel": channel_name,
                    "video_id": video_id,
                    "video_title": video_title,
                }

            transcript = download_transcript(video_id)
            if not transcript or not transcript.strip():
                log.warning("Empty transcript for %s. Cascading to next channel...", channel_name)
                continue

            seed_data = summarize_to_story_seed(transcript, video_title)

            thesis = seed_data.get("thesis", video_title)
            story_seed = seed_data.get("story_seed", {})

            # A channel may have a new upload that is still the same market
            # story already covered by this channel. Cascade instead of
            # stopping the entire run; SerpAPI is then used after all seven
            # channel candidates are exhausted.
            if evaluator.is_duplicate(thesis)[0] or evaluator.is_duplicate(video_title, threshold=0.90)[0]:
                log.info("Channel candidate is already covered. Cascading to the next source.")
                continue

            log.info("Success! Extracted topic from %s", channel_name)
            return {
                "channel": channel_name,
                "video_id": video_id,
                "video_title": video_title,
                "thesis": thesis,
                "story_seed": story_seed,
                "transcript_length": len(transcript),
            }
        except Exception as exc:
            log.error("Failed processing %s: %s. Cascading to next channel...", channel_name, exc)
            continue

    serp_result = _discover_from_serp()
    if serp_result:
        log.info("No fresh channel source available; selected a new SERPAPI market-news item.")
        return serp_result

    if title_only_candidate:
        log.warning(
            "All transcript providers failed. Falling back to title-only topic seed from %s: %s",
            title_only_candidate["channel"],
            title_only_candidate["video_title"],
        )
        seed_data = _fallback_story_seed(title_only_candidate["video_title"])
        return {
            **title_only_candidate,
            "thesis": seed_data["thesis"],
            "story_seed": seed_data["story_seed"],
            "transcript_length": 0,
        }

    raise RuntimeError("Cascading scan failed: Could not fetch a valid video and transcript from ANY of the 7 channels.")

