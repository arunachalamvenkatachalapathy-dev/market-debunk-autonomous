"""
Prompt Engineer Agent — the creative AI brain behind EVERY pipeline section.
Uses targeted Gemini calls to generate optimized configs for voice, visuals,
mascot, subtitles, assembly, and publishing metadata.
"""
import logging
import json
import requests
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
    "- Color grade: navy (#0A0E1F) base, orange (#FF6B00) accents.\n"
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
                
        logger.error("All available Gemini API keys have exhausted their rate limits (429).")
        raise last_error

    # ──────────────────────────────────────────────
    #  SECTION 1: TOPIC DISCOVERY
    # ──────────────────────────────────────────────

    def _is_topic_used(self, title):
        import os, json
        if not os.path.exists("used_topics.json"):
            return False
        try:
            with open("used_topics.json", "r") as f:
                used = json.load(f)
            title_words = set(title.lower().split())
            for entry in used:
                prev_words = set(entry.get("topic", "").lower().split())
                if title_words and prev_words:
                    intersection = title_words & prev_words
                    union = title_words | prev_words
                    if len(intersection) / len(union) >= 0.75:
                        return True
        except:
            pass
        return False

    def fetch_fresh_topic(self):
        """Fetches the latest topic directly from PR Sundar's YouTube channel."""
        logger.info("🔍 PE Agent [TOPIC]: Searching PR Sundar's YouTube channel for the latest topic...")

        # Source 1: PR Sundar's YouTube RSS feed
        try:
            # PR Sundar Channel ID: UCaw-1cUd74wvEatvZna0TzQ
            rss_url = "https://www.youtube.com/feeds/videos.xml?channel_id=UCaw-1cUd74wvEatvZna0TzQ"
            response = requests.get(rss_url, timeout=10)
            if response.status_code == 200:
                root = ET.fromstring(response.content)
                # YouTube RSS uses a default namespace
                ns = {'yt': 'http://www.youtube.com/xml/schemas/2015', 'default': 'http://www.w3.org/2005/Atom'}
                entries = root.findall("default:entry", ns)
                
                for entry in entries[:5]:  # Check top 5 for freshness
                    title = entry.findtext("default:title", namespaces=ns)
                    link = entry.find("default:link", namespaces=ns)
                    video_url = link.attrib['href'] if link is not None else ""
                    
                    if title and not self._is_topic_used(title):
                        logger.info(f"🔍 PE Agent [TOPIC]: Found fresh PR Sundar video: {title}")
                        return f"PR Sundar latest analysis on: {title} (Video URL: {video_url})"
        except Exception as e:
            logger.warning(f"🔍 PE Agent [TOPIC]: PR Sundar RSS fetch failed: {e}")

        # Source 2: Reddit scraping would go here (requires API keys)
        # Source 3: Google Trends would go here

        # Fallback: static trending topic
        logger.info("🔍 PE Agent [TOPIC]: Falling back to internal topic pool.")
        fallback_topics = [
            "Are high-yield dividend stocks a safe bet during market volatility?",
            "Is SIP really the safest way to invest in mutual funds?",
            "Do penny stocks actually make you rich or just broke?",
            "Is gold really a hedge against inflation in 2026?",
            "Can you beat the market by following stock tips on social media?",
        ]
        import random
        return random.choice(fallback_topics)

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
            "- EVERY prompt MUST end with 'navy blue and vibrant orange color grading, cinematic lighting, 8k resolution'\n"
            "- Category tags MUST NOT repeat in adjacent scenes\n"
            "- Use at least 3 different categories across 5 scenes\n"
            "- Composition should avoid center-bottom (mascot zone) and 60-75% vertical (subtitle zone)\n"
            "- Each prompt must be COMPLETELY unique — no two should describe similar imagery\n"
            "- The global_style_suffix should be: 'navy blue and vibrant orange color grading, cinematic lighting, 8k resolution'\n"
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
        """Engineers the ASS subtitle style parameters for optimal readability."""
        logger.info("📝 PE Agent [SUBTITLES]: Engineering subtitle style...")

        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Engineer the SUBTITLE STYLE for the video.\n"
            "Generate ASS subtitle format parameters:\n"
            "- font_name: 'DejaVu Sans' or 'Arial Black' (bold sans-serif)\n"
            "- font_size: 80-90 for 1080x1920 resolution\n"
            "- primary_color: Use ASS hex format. Yellow '&H0000FFFF' or White '&H00FFFFFF'\n"
            "- emphasis_color: Orange '&H000080FF' for CAPS words\n"
            "- outline_color: Black '&H00000000'\n"
            "- outline_width: 5-7 for readability\n"
            "- shadow_depth: 2-4\n"
            "- margin_v: MUST be 400-550 (places text at 60-75% down on 1920px frame)\n"
            "- alignment: 2 (bottom-center)\n"
        )

        user_prompt = (
            "Generate the optimal subtitle style for a finance mythbusting Short. "
            "The video has dark navy backgrounds with orange accents. "
            "Subtitles must be readable against busy AI-generated backgrounds."
        )
        return self._call_gemini(system_prompt, user_prompt, SubtitleStyle, temperature=0.3)

    # ──────────────────────────────────────────────
    #  SECTION 7: ASSEMBLY CONFIG ENGINEERING
    # ──────────────────────────────────────────────

    def engineer_assembly_config(self, script, processed_scenes=None):
        """Engineers FFmpeg assembly parameters for the final render."""
        logger.info("🎬 PE Agent [ASSEMBLY]: Engineering assembly config...")

        scene_count = len(script.get("scenes", []))

        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Engineer the ASSEMBLY CONFIG for the FFmpeg final render.\n"
            "Generate optimal parameters:\n"
            "- ken_burns_zoom_rate: 0.0003-0.0008 (subtle to dramatic zoom)\n"
            "- loudness_target_i: MUST be -14 (LUFS)\n"
            "- loudness_lra: 11 (loudness range)\n"
            "- loudness_tp: -1.5 (true peak)\n"
            "- logo_scale_width: 120-180 pixels\n"
            "- logo_padding: 30 pixels from top-right\n"
            "- suspense_bed_volume: 0.10-0.20 (ducked under voiceover)\n"
            "- output_fps: 25 or 30\n"
            "- output_codec: 'libx264'\n"
            "- audio_codec: 'aac'\n"
        )

        user_prompt = (
            f"Generate assembly config for a {scene_count}-scene finance Short. "
            "The video needs dramatic but not distracting Ken Burns motion, "
            "loud and punchy audio for mobile speakers, and a subtle background music bed."
        )
        return self._call_gemini(system_prompt, user_prompt, AssemblyConfig, temperature=0.3)

    # ──────────────────────────────────────────────
    #  SECTION 8: PUBLISH METADATA ENGINEERING
    # ──────────────────────────────────────────────

    def engineer_publish_metadata(self, script, topic):
        """Engineers optimized publishing metadata for YouTube, Telegram, Instagram."""
        logger.info("📢 PE Agent [PUBLISH]: Engineering publish metadata...")

        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Engineer PUBLISHING METADATA for maximum reach.\n"
            "Generate:\n"
            "- youtube_titles: Exactly 3 options, each ≤50 chars, include '#Shorts', clickbait-worthy\n"
            "- youtube_description: Highly engaging, SEO-optimized summary targeting relevant keywords + 5-8 hashtags at the end, max 600 chars, NO citations\n"
            "- youtube_tags: 5-15 SEO tags including: shorts, finance, market, myth, India\n"
            "- telegram_caption: SEO-optimized, highly engaging caption with emojis + 3-5 hashtags, max 250 chars\n"
            "- instagram_description: SEO-optimized, highly engaging caption with emojis + 10-15 hashtags, max 600 chars\n"
            "- category_id: '27' for Education\n"
            "Rules:\n"
            "- Titles must trigger curiosity — use questions, contradictions, or surprising claims\n"
            "- Never use citation language in any metadata\n"
            "- First YouTube title should be the MOST clickable\n"
        )

        title = script.get("title", topic)
        user_prompt = (
            f"Topic: {topic}\n"
            f"Script title: {title}\n"
            f"Script description: {script.get('description', '')}\n"
            "Generate the publishing metadata."
        )
        return self._call_gemini(system_prompt, user_prompt, PublishMetadata)

    # ──────────────────────────────────────────────
    #  MAIN EXECUTE (backward compat, runs topic + script only)
    # ──────────────────────────────────────────────

    def execute(self):
        """Legacy entry point: Find topic -> Write Script -> Return."""
        topic = self.fetch_fresh_topic()
        script = self.generate_script(topic)
        return script, topic
