"""
Prompt Engineer Agent — the creative AI brain behind EVERY pipeline section.
Uses targeted Gemini calls to generate optimized configs for voice, visuals,
mascot, subtitles, assembly, and publishing metadata.
"""
import logging
import json
import requests
import random
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
        """Attempts to download the YouTube transcript text for a video."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            transcript_obj = YouTubeTranscriptApi().fetch(video_id)
            full_text = " ".join([snippet.text for snippet in transcript_obj.snippets])
            return full_text
        except Exception as e:
            logger.warning(f"🔍 PE Agent [TOPIC]: Could not fetch transcript for {video_id}: {e}")
            return None

    def fetch_fresh_topic(self):
        """Fetches the latest topic directly from PR Sundar's YouTube channel."""
        logger.info("🔍 PE Agent [TOPIC]: Searching PR Sundar's YouTube channel for the latest topic...")
        import os, random

        channel_id = "UCS2NdYUmv_PUyyKeDAo5zYA"
        yt_api_key = os.getenv("YT_API_KEY")

        # Source 1: YouTube Data API v3 Search (if YT_API_KEY is available)
        if yt_api_key:
            try:
                logger.info("🔍 PE Agent [TOPIC]: Attempting YouTube Data API v3 search...")
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
                            logger.info(f"🔍 PE Agent [TOPIC]: Found fresh video via Data API [ID: {v_id}]: {title}")
                            topic = self._build_topic_with_summary(v_id, v_url, title)
                            if topic:
                                return topic
                else:
                    logger.warning(f"🔍 PE Agent [TOPIC]: YouTube Data API returned status {res.status_code}: {res.text[:150]}")
            except Exception as e:
                logger.warning(f"🔍 PE Agent [TOPIC]: YouTube Data API v3 search failed: {e}")

        # Source 2: PR Sundar's YouTube RSS feed (Fallback if no API key or API limit)
        try:
            logger.info("🔍 PE Agent [TOPIC]: Querying PR Sundar's YouTube RSS feed...")
            rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
            response = requests.get(rss_url, timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                ns = {'yt': 'http://www.youtube.com/xml/schemas/2015', 'default': 'http://www.w3.org/2005/Atom'}
                entries = root.findall("default:entry", ns)
                
                for entry in entries[:5]:
                    title = entry.findtext("default:title", namespaces=ns) or ""
                    link = entry.find("default:link", namespaces=ns)
                    video_url = link.attrib['href'] if link is not None else ""
                    
                    video_id = None
                    if "v=" in video_url:
                        video_id = video_url.split("v=")[1].split("&")[0]
                    elif "youtu.be/" in video_url:
                        video_id = video_url.split("youtu.be/")[1].split("?")[0]

                    if not self._is_video_processed(video_id, video_url):
                        logger.info(f"🔍 PE Agent [TOPIC]: Found fresh video via RSS [ID: {video_id}]: {title}")
                        topic = self._build_topic_with_summary(video_id, video_url, title)
                        if topic:
                            return topic
        except Exception as e:
            logger.warning(f"🔍 PE Agent [TOPIC]: PR Sundar RSS fetch failed: {e}")

        # Fallback: static trending topic
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

    def _build_topic_with_summary(self, video_id, video_url, title):
        """Helper to build transcript summary topic for a video."""
        transcript = self._fetch_youtube_transcript(video_id) if video_id else None
        summary_text = ""

        if transcript:
            truncated = transcript[:15000]
            logger.info("🔍 PE Agent [TOPIC]: Generating AI summary from actual video transcript...")
            try:
                summary_data = self._call_gemini(
                    system_prompt="You are an expert financial market analyst and mythbuster.",
                    user_prompt=(
                        f"Video Link: {video_url}\n"
                        f"Video Title: {title}\n\n"
                        "What is the important, shocking summary of today's market analysis from this video?\n"
                        "Analyze the following transcript and extract the most important, shocking insights, "
                        "core financial takeaways, market movements, or myth-busting points in 3-4 concise, energetic sentences.\n\n"
                        f"Transcript:\n{truncated}"
                    ),
                    response_schema=types.Schema(
                        type=types.Type.OBJECT,
                        properties={
                            "summary": types.Schema(type=types.Type.STRING)
                        },
                        required=["summary"]
                    )
                )
                if isinstance(summary_data, dict) and "summary" in summary_data:
                    summary_text = summary_data["summary"]
            except Exception as e:
                logger.warning(f"🔍 PE Agent [TOPIC]: Failed to generate summary from transcript: {e}")

        if summary_text:
            return f"PR Sundar analysis on {title} [Video ID: {video_id}]\nLink: {video_url}\nShocking Summary Today: {summary_text}"
        else:
            return f"PR Sundar latest market update: {title} [Video ID: {video_id}]\nLink: {video_url}"

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

        scenes_text = json.dumps(script.get("scenes", []), indent=2)

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

        user_prompt = f"Here are the 5 scenes — determine the mascot timeline:\n{scenes_text}"
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
