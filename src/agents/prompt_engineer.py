"""
Prompt Engineer Agent — the creative AI brain behind EVERY pipeline section.
Uses targeted Gemini calls to generate optimized configs for voice, visuals,
mascot, subtitles, assembly, and publishing metadata.
"""
import logging
import json
import requests
import random
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from google.genai import types

from src.models import (
    VideoScript, VoiceConfig, VisualConfig,
    MascotTimeline, SubtitleStyle, AssemblyConfig, PublishMetadata
)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  FRAMEWORK RULES (injected into every Gemini call)
# ──────────────────────────────────────────────
FRAMEWORK_RULES = (
    "You are the Prompt Engineer AI for 'Market Debunk' — a daily 30-60 second "
    "finance mythbusting Short hosted by Market, a mascot shaped like an arrow.\n"
    "CORE RULES you must ALWAYS enforce:\n"
    "- NO citations ever. Never say 'according to', 'sources say', 'experts claim'.\n"
    "- 40-60 second target runtime.\n"
    "- Cold open hook ≤8 words, phrased as a question or contradiction.\n"
    "- Energetic delivery: vary sentence lengths, CAPS on stressed words (max 1-2/sentence), "
    "em-dashes/ellipses for breath beats, hyped-friend tone.\n"
    "- One rhetorical question per 15 seconds.\n"
    "- Mascot Arrow: 'arrow_up' (green) for Setup/Truth, 'arrow_down' (red) for Reveal/Myth.\n"
    "- Visual categories: vaults/security, crowds/markets, paperwork/bureaucracy, "
    "growth/decline, digital/data, hands/decisions. Use 3-4 per video, never same twice in a row.\n"
    "- Asset Pool Tags: For 'animation_tag', pick EXACTLY one of: 'bullish', 'bearish', 'neutral', 'educational'. "
    "This must match the emotion of the scene to pull the correct 3D character animation.\n"
    "- Color grade: light slate (#F4F6F9) base, dark accents.\n"
    "- Subtitle safe zone: 60-75% down the 1920px frame.\n"
    "- Audio loudness: -14 LUFS integrated.\n"
)


class PromptEngineerAgent:
    """The creative AI controlling every section of the pipeline."""

    def __init__(self, gemini_client_or_clients):
        if isinstance(gemini_client_or_clients, list):
            self.clients = gemini_client_or_clients
        else:
            self.clients = [gemini_client_or_clients]

    def _call_gemini(self, system_prompt, user_prompt, response_schema, temperature=0.7):
        """Unified Gemini call with structured output and API key rotation for rate limits."""
        last_error = None
        
        import time
        max_retries = 3
        for attempt in range(max_retries):
            for client in self.clients:
                try:
                    response = client.models.generate_content(
                        model="gemini-3.1-flash-lite",
                        contents=[system_prompt, user_prompt],
                        config=types.GenerateContentConfig(
                            response_mime_type="application/json",
                            response_schema=response_schema,
                            temperature=temperature
                        ),
                    )

                    if hasattr(response, "parsed") and response.parsed:
                        data = response.parsed
                        if hasattr(data, "model_dump"):
                            return data.model_dump()
                        return data

                    return json.loads(response.text)
                    
                except Exception as e:
                    err_str = str(e).upper()
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                        logger.warning(f"Prompt Engineer hit Rate Limit (429). Rotating to next API key... ({len(self.clients)} total keys)")
                        last_error = e
                        continue
                    logger.error(f"Prompt Engineer Gemini call failed: {e}")
                    raise
            
            if attempt < max_retries - 1:
                logger.warning(f"All available Gemini API keys exhausted (429). Waiting 35 seconds before retry {attempt + 1}/{max_retries}...")
                time.sleep(35)
                
        logger.error("All available Gemini API keys have exhausted their rate limits (429) after retries.")
        raise last_error

    # ──────────────────────────────────────────────
    #  SECTION 1: TOPIC DISCOVERY (EXHAUSTIVE & DUPLICATE-FREE)
    # ──────────────────────────────────────────────

    def _is_video_processed(self, video_id, video_url=""):
        import os, json
        if not os.path.exists("used_topics.json"):
            return False
        try:
            with open("used_topics.json", "r") as f:
                used = json.load(f)
            for entry in used:
                if video_id and entry.get("video_id") == video_id:
                    return True
                topic_str = entry.get("topic", "")
                if video_id and video_id in topic_str:
                    return True
                if video_url and video_url in topic_str:
                    return True
        except Exception:
            pass
        return False

    def _save_processed_topic(self, video_id, topic_string):
        import os, json
        used = []
        if os.path.exists("used_topics.json"):
            try:
                with open("used_topics.json", "r") as f:
                    used = json.load(f)
            except Exception:
                used = []
        
        # Append new entry
        used.append({
            "video_id": video_id,
            "topic": topic_string,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        try:
            with open("used_topics.json", "w") as f:
                json.dump(used, f, indent=2)
            logger.info(f"💾 PE Agent [MEMORY]: Successfully recorded video ID {video_id} to used_topics.json")
        except Exception as e:
            logger.error(f"❌ PE Agent [MEMORY]: Failed to save used_topics.json: {e}")

    def _fetch_youtube_transcript(self, video_id):
        """Attempts to download the YouTube transcript text for a video using API and yt-dlp fallback."""
        # Method 1: youtube_transcript_api
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            ytt = YouTubeTranscriptApi()
            try:
                transcript_list = ytt.fetch(video_id, languages=('ta', 'en'))
            except Exception:
                transcript_list = ytt.fetch(video_id)
            
            lines = []
            for item in transcript_list:
                text_item = item.get('text', '') if isinstance(item, dict) else str(item)
                if text_item:
                    lines.append(text_item)
            full_text = " ".join(lines)
            if full_text.strip():
                logger.info(f"🔍 PE Agent [TOPIC]: Successfully fetched transcript via youtube-transcript-api for {video_id}")
                return full_text
        except Exception as e:
            logger.warning(f"🔍 PE Agent [TOPIC]: youtube-transcript-api failed for {video_id}: {e}")

        # Method 2: yt_dlp with js_runtimes node
        try:
            import yt_dlp, xml.etree.ElementTree as ET
            url = f"https://www.youtube.com/watch?v={video_id}"
            ydl_opts = {
                'skip_download': True,
                'writeautosub': True,
                'subtitleslangs': ['ta', 'en'],
                'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
                'js_runtimes': {'node': {}},
                'quiet': True
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                subs = info.get('automatic_captions') or info.get('subtitles')
                if subs:
                    target_track = None
                    for lang in ['ta', 'ta-orig', 'en']:
                        if lang in subs:
                            target_track = subs[lang]
                            break
                    if not target_track:
                        target_track = list(subs.values())[0]
                    
                    sub_url = None
                    for fmt in target_track:
                        if fmt.get('ext') in ['json3', 'srv1', 'vtt']:
                            sub_url = fmt.get('url')
                            break
                    if not sub_url and target_track:
                        sub_url = target_track[0].get('url')
                        
                    if sub_url:
                        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                        r = requests.get(sub_url, headers=headers, timeout=10)
                        if r.status_code == 200 and r.text:
                            try:
                                data = r.json()
                                text_parts = []
                                for e in data.get('events', []):
                                    for s in e.get('segs', []):
                                        utf8_str = s.get('utf8', '').strip()
                                        if utf8_str and utf8_str != '\n':
                                            text_parts.append(utf8_str)
                                full_text = " ".join(text_parts)
                                if full_text.strip():
                                    logger.info(f"🔍 PE Agent [TOPIC]: Successfully fetched transcript via yt-dlp node for {video_id}")
                                    return full_text
                            except Exception:
                                root = ET.fromstring(r.text)
                                lines = [elem.text for elem in root.findall('.//text') if elem.text]
                                full_text = " ".join(lines)
                                if full_text.strip():
                                    logger.info(f"🔍 PE Agent [TOPIC]: Successfully fetched transcript via yt-dlp XML for {video_id}")
                                    return full_text
        except Exception as e:
            logger.warning(f"🔍 PE Agent [TOPIC]: yt-dlp node transcript fetch failed for {video_id}: {e}")

        # Method 3: Direct HTML scraping of ytInitialPlayerResponse
        try:
            import json, re, xml.etree.ElementTree as ET
            url = f"https://www.youtube.com/watch?v={video_id}"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept-Language': 'en-US,en;q=0.9,ta;q=0.8'
            }
            r = requests.get(url, headers=headers, timeout=10)
            match = re.search(r'ytInitialPlayerResponse\s*=\s*({.+?});(?:var\s+|</script>)', r.text)
            if match:
                data = json.loads(match.group(1))
                caption_tracks = data.get('captions', {}).get('playerCaptionsTracklistRenderer', {}).get('captionTracks', [])
                for track in caption_tracks:
                    sub_baseUrl = track.get('baseUrl')
                    if sub_baseUrl:
                        fmt_url = f"{sub_baseUrl}&fmt=json3"
                        sub_r = requests.get(fmt_url, headers=headers, timeout=10)
                        if sub_r.status_code == 200 and len(sub_r.text) > 50:
                            jdata = sub_r.json()
                            text_parts = []
                            for e in jdata.get('events', []):
                                for s in e.get('segs', []):
                                    utf8_str = s.get('utf8', '').strip()
                                    if utf8_str and utf8_str != '\n':
                                        text_parts.append(utf8_str)
                            full_text = " ".join(text_parts)
                            if full_text.strip():
                                logger.info(f"🔍 PE Agent [TOPIC]: Successfully fetched transcript via HTML scraping for {video_id}")
                                return full_text
        except Exception as e:
            logger.warning(f"🔍 PE Agent [TOPIC]: HTML transcript scraping failed for {video_id}: {e}")

        return None

    def fetch_fresh_topic(self):
        """Fetches the latest topic from any of the target channels in the multi-channel registry."""
        import os, random

        TARGET_CHANNELS = [
            {"name": "Money Pechu", "channel_id": "UCqhL6vNCwYLC9_jePXOIvBg"},
            {"name": "Makkal Pechu", "channel_id": "UCRySNNVhiuLWciU_20H84-Q"},
            {"name": "Rupee Driver", "channel_id": "UCo5CAieenL0ExXzvjzs17QQ"},
            {"name": "Trade Achievers", "channel_id": "UCsrnRWZSpE-q8s0SAOk8OOg"},
            {"name": "Money Purse", "channel_id": "UChBT5TlUeG68PKvJSg6MkqQ"}
        ]
        
        yt_api_key = os.getenv("YT_API_KEY")

        for ch in TARGET_CHANNELS:
            ch_name = ch["name"]
            channel_id = ch["channel_id"]
            logger.info(f"🔍 PE Agent [TOPIC]: Checking target channel '{ch_name}' ({channel_id})...")

            # Source 1: YouTube Data API v3 Search
            if yt_api_key:
                try:
                    logger.info(f"🔍 PE Agent [TOPIC]: Attempting YouTube Data API search for '{ch_name}'...")
                    api_url = (
                        f"https://www.googleapis.com/youtube/v3/search?"
                        f"key={yt_api_key}&channelId={channel_id}&part=snippet&order=date&maxResults=5&type=video"
                    )
                    res = requests.get(api_url, timeout=10)
                    if res.status_code == 200:
                        items = res.json().get("items", [])
                        for item in items:
                            v_id = item.get("id", {}).get("videoId")
                            snippet = item.get("snippet", {})
                            title = snippet.get("title", "")
                            v_url = f"https://www.youtube.com/watch?v={v_id}" if v_id else ""

                            if v_id and not self._is_video_processed(v_id, v_url):
                                logger.info(f"🔍 PE Agent [TOPIC]: Found fresh video via API on '{ch_name}' [ID: {v_id}]: {title}")
                                topic = self._build_topic_with_summary(v_id, v_url, title, channel_name=ch_name)
                                if topic:
                                    return topic
                except Exception as e:
                    logger.warning(f"🔍 PE Agent [TOPIC]: YouTube Data API search failed for '{ch_name}': {e}")

            # Source 2: YouTube RSS Feed (100% reliable fallback)
            try:
                logger.info(f"🔍 PE Agent [TOPIC]: Querying RSS feed for '{ch_name}'...")
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                response = requests.get(rss_url, timeout=10)
                if response.status_code == 200:
                    import xml.etree.ElementTree as ET
                    root = ET.fromstring(response.content)
                    ns = {
                        'yt': 'http://www.youtube.com/xml/schemas/2015',
                        'default': 'http://www.w3.org/2005/Atom',
                        'media': 'http://search.yahoo.com/mrss/'
                    }
                    entries = root.findall("default:entry", ns)
                    
                    for entry in entries[:5]:
                        title = entry.findtext("default:title", namespaces=ns) or ""
                        link = entry.find("default:link", namespaces=ns)
                        video_url = link.attrib['href'] if link is not None else ""
                        
                        group = entry.find("media:group", ns)
                        rss_description = group.findtext("media:description", namespaces=ns) if group is not None else ""
                        
                        video_id = entry.findtext("yt:videoId", namespaces=ns)
                        if not video_id:
                            if "v=" in video_url:
                                video_id = video_url.split("v=")[1].split("&")[0]
                            elif "youtu.be/" in video_url:
                                video_id = video_url.split("youtu.be/")[1].split("?")[0]

                        if video_id and not self._is_video_processed(video_id, video_url):
                            logger.info(f"🔍 PE Agent [TOPIC]: Found fresh video via RSS on '{ch_name}' [ID: {video_id}]: {title}")
                            topic = self._build_topic_with_summary(video_id, video_url, title, rss_description=rss_description, channel_name=ch_name)
                            if topic:
                                return topic
            except Exception as e:
                logger.warning(f"🔍 PE Agent [TOPIC]: RSS fetch failed for '{ch_name}': {e}")

        # Fallback: static trending topic pool
        logger.info("🔍 PE Agent [TOPIC]: Falling back to internal topic pool.")
        fallback_topics = [
            "Are high-yield dividend stocks a safe bet during market volatility?",
            "Is SIP really the safest way to invest in mutual funds?",
            "Do penny stocks actually make you rich or just broke?",
            "Is gold really a hedge against inflation in 2026?",
            "Can you beat the market by following stock tips on social media?"
        ]
        for topic in fallback_topics:
            if not self._is_video_processed("", topic):
                return topic
        return random.choice(fallback_topics)

    def _build_topic_with_summary(self, video_id, video_url, title, rss_description=None, channel_name="Financial Analyst"):
        """Helper to build transcript summary topic for a video strictly using actual video text."""
        source_text = self._fetch_youtube_transcript(video_id) if video_id else None
        
        if not source_text and rss_description and len(rss_description.strip()) > 50:
            logger.info(f"🔍 PE Agent [TOPIC]: Using detailed RSS video description fallback for {video_id}")
            source_text = rss_description

        if not source_text or len(source_text.strip()) < 20:
            logger.warning(f"🔍 PE Agent [TOPIC]: No transcript or description available for video {video_id}. Skipping (no guessing from title).")
            return None

        truncated = source_text[:15000]
        logger.info(f"🔍 PE Agent [TOPIC]: Generating AI summary from actual video text ({channel_name})...")
        try:
            summary_data = self._call_gemini(
                system_prompt="You are an expert financial market analyst and mythbuster.",
                user_prompt=(
                    f"Channel Name: {channel_name}\n"
                    f"Video Link: {video_url}\n"
                    f"Video Title: {title}\n\n"
                    f"What is the important, shocking summary of today's market and financial analysis from {channel_name}?\n"
                    "Analyze the following actual video text/transcript and extract the most important, shocking insights, "
                    "core financial takeaways, market movements, or myth-busting points in 3-4 concise, energetic sentences.\n\n"
                    f"Actual Video Text:\n{truncated}"
                ),
                response_schema=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "summary": types.Schema(type=types.Type.STRING)
                    },
                    required=["summary"]
                )
            )
            if isinstance(summary_data, dict) and "summary" in summary_data and summary_data["summary"]:
                summary_text = summary_data["summary"]
                return (
                    f"{channel_name} analysis on {title} [Video ID: {video_id}]\n"
                    f"Link: {video_url}\n"
                    f"Shocking Summary Today: {summary_text}"
                )
        except Exception as e:
            logger.warning(f"🔍 PE Agent [TOPIC]: Gemini transcript summary failed for {video_id}: {e}")
            
        return None

    # ──────────────────────────────────────────────
    #  SECTION 2: SCRIPT GENERATION
    # ──────────────────────────────────────────────

    def generate_script(self, topic):
        """Generates the full dynamic-scene structured script following framework rules."""
        logger.info(f"📝 PE Agent [SCRIPT]: Writing script for: '{topic[:60]}...'")

        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Generate a complete 5-12 scene video script for the given PR Sundar video topic.\n"
            "CRITICAL: You must use your internal knowledge (Gemini) to find the absolute latest real-world information, stock prices, or news related to this exact topic to build the script. Do NOT just invent generic advice.\n"
            "CRITICAL: Do NEVER mention PR Sundar's name, his channel, or the source video anywhere in the script, title, or description. You must act as an independent analyst discussing the topic itself.\n"
            "Requirements:\n"
            "- Between 5 and 12 scenes\n"
            "- Hook (scene 1 narration opening) MUST be ≤8 words\n"
            "- Each scene needs: narration, visual_prompt, visual_category, arrow_state\n"
            "- Visual categories must rotate — never repeat the same category in adjacent scenes\n"
            "- CRITICAL DIALOGUE DYNAMIC: The script must be a conversation. The Red Arrow (arrow_down) acts as the skeptic asking questions/presenting the debunked theory, and the Green Arrow (arrow_up) acts as the expert answering and providing the facts.\n"
            "- Explicitly alternate between 'arrow_down' (Red Arrow questioning) and 'arrow_up' (Green Arrow answering) across the scenes.\n"
            "- Include a YouTube title and description with hashtags\n"
        )

        user_prompt = f"Topic to debunk/analyze: {topic}"
        return self._call_gemini(system_prompt, user_prompt, VideoScript)

    # ──────────────────────────────────────────────
    #  SECTION 3: VOICE ENGINEERING
    # ──────────────────────────────────────────────

    def engineer_voice_config(self, script):
        """Engineers optimal voice/SSML configuration for each scene."""
        logger.info("🎙️ PE Agent [VOICE]: Engineering voice config...")

        scenes_text = json.dumps(script.get("scenes", []), indent=2)

        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Engineer the VOICE configuration for each scene.\n"
            "For each scene, generate:\n"
            "- SSML-enriched text with <emphasis>, <break>, <prosody> tags\n"
            "- Pacing rate (hooks faster, reveals slower)\n"
            "- 2-3 emphasis words per scene that should get CAPS in subtitles\n"
            "Rules:\n"
            "- Scene 1 (hook): fastest pacing (+15% to +20%)\n"
            "- Reveal scene: slightly slower pacing (+5% to +10%), add <break time='400ms'/> before the key reveal\n"
            "- Final scene (CTA): medium pacing (+10%)\n"
            "- Use <emphasis level='strong'> on reveal words\n"
            "- Voice name should be 'Adam' for ElevenLabs\n"
        )

        user_prompt = f"Here are the 5 scenes to engineer voice for:\n{scenes_text}"
        return self._call_gemini(system_prompt, user_prompt, VoiceConfig)

    # ──────────────────────────────────────────────
    #  SECTION 4: VISUAL ENGINEERING
    # ──────────────────────────────────────────────

    def engineer_visual_prompts(self, script):
        """Engineers enhanced, detailed visual prompts with category enforcement."""
        logger.info("🎨 PE Agent [VISUALS]: Engineering visual prompts...")

        scenes_text = json.dumps(script.get("scenes", []), indent=2)

        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Engineer DETAILED image generation prompts for each scene.\n"
            "For each scene, generate:\n"
            "- An enhanced_prompt that is 30-60 words, highly descriptive, cinematic\n"
            "- A negative_prompt to avoid bad generations\n"
            "- A category_tag from: vaults, crowds, paperwork, growth, digital, hands\n"
            "- A composition_directive: center, left-third, right-third, top-heavy, bottom-heavy\n"
            "Rules:\n"
            "- EVERY prompt MUST end with 'bright white and light gray studio background, cinematic lighting, 8k resolution'\n"
            "- Category tags MUST NOT repeat in adjacent scenes\n"
            "- Use at least 3 different categories across 5 scenes\n"
            "- Composition should avoid center-bottom (mascot zone) and 60-75% vertical (subtitle zone)\n"
            "- Each prompt must be COMPLETELY unique — no two should describe similar imagery\n"
            "- The global_style_suffix should be: 'bright white and light gray studio background, cinematic lighting, 8k resolution'\n"
        )

        user_prompt = f"Here are the 5 scenes to generate visual prompts for:\n{scenes_text}"
        return self._call_gemini(system_prompt, user_prompt, VisualConfig)

    # ──────────────────────────────────────────────
    #  SECTION 5: MASCOT TIMELINE ENGINEERING
    # ──────────────────────────────────────────────

    def engineer_mascot_timeline(self, script):
        """Engineers precise mascot arrow state transitions with rationale."""
        logger.info("🏹 PE Agent [MASCOT]: Engineering mascot timeline...")

        scenes = script.get("scenes", []) if isinstance(script, dict) else [s.model_dump() if hasattr(s, "model_dump") else s for s in getattr(script, "scenes", [])]
        scenes_text = json.dumps(scenes, indent=2)

        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Engineer the MASCOT TIMELINE for the Market arrow character.\n"
            "For each scene, specify:\n"
            "- arrow_state: 'arrow_up' (green, confident) or 'arrow_down' (red, knowing)\n"
            "- transition_rationale: WHY the arrow is in this state\n"
            "- position_x: horizontal position formula, use '(W-w)/2' for center\n"
            "- position_y: vertical position formula, use 'H-h-600' to stay above subtitles\n"
            "Rules:\n"
            "- The arrow starts 'arrow_up' during the myth/setup phase\n"
            "- The arrow flips to 'arrow_down' at the REVEAL moment (usually scene 3 or 4)\n"
            "- The flip_scene should be the scene number where the myth gets busted\n"
            "- Once flipped to 'arrow_down', it stays down for the rest of the video\n"
            "- Position must not overlap with subtitle safe zone (60-75% down = pixels 1152-1440)\n"
        )

        user_prompt = f"Here are the scenes — determine the mascot timeline:\n{scenes_text}"
        return self._call_gemini(system_prompt, user_prompt, MascotTimeline, temperature=0.3)

    # ──────────────────────────────────────────────
    #  SECTION 6: SUBTITLE STYLE ENGINEERING
    # ──────────────────────────────────────────────

    def engineer_subtitle_style(self, script):
        """Engineers subtitle parameters for optimal readability."""
        logger.info("📝 PE Agent [SUBTITLES]: Engineering subtitle style...")
        
        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Define the subtitle configuration style including font, size, primary color, outline, and vertical positioning."
        )
        user_prompt = "Generate optimal subtitle styling config."
        return self._call_gemini(system_prompt, user_prompt, SubtitleStyle, temperature=0.3)

    def engineer_assembly_config(self, script, *args, **kwargs):
        """Engineers assembly parameters."""
        logger.info("🎬 PE Agent [ASSEMBLY]: Engineering assembly config...")
        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Define the assembly configuration including resolution (1080x1920), fps (30), and audio loudness normalization (-14 LUFS)."
        )
        user_prompt = "Generate optimal assembly config for 9:16 vertical Short video."
        return self._call_gemini(system_prompt, user_prompt, AssemblyConfig, temperature=0.3)

    def engineer_publish_metadata(self, script, *args, **kwargs):
        """Engineers publishing metadata (title, description, tags)."""
        logger.info("📢 PE Agent [PUBLISH]: Engineering publish metadata...")
        scenes = script.get("scenes", []) if isinstance(script, dict) else [s.model_dump() if hasattr(s, "model_dump") else s for s in getattr(script, "scenes", [])]
        scenes_text = json.dumps(scenes, indent=2)
        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Generate optimized YouTube Shorts title (with #Shorts), description, and tags for the video."
        )
        user_prompt = f"Generate publishing metadata for this script:\n{scenes_text}"
        return self._call_gemini(system_prompt, user_prompt, PublishMetadata, temperature=0.3)
