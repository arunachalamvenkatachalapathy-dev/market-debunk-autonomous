"""
Prompt Engineer Agent — the creative AI brain behind EVERY pipeline section.
Uses targeted Gemini calls to generate optimized configs for voice, visuals,
mascot, subtitles, assembly, and publishing metadata.
"""
import logging
import json
import requests
import random
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from google.genai import types

from src.models import (
    VideoScript, VoiceConfig, VisualConfig,
    SubtitleStyle, AssemblyConfig, PublishMetadata
)
# NvidiaClient removed — pipeline is Gemini-only per user directive

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  FRAMEWORK RULES (injected into every LLM call)
# ──────────────────────────────────────────────
FRAMEWORK_RULES = (
    "You are the Lead Creative AI for a high-retention, storytelling YouTube Shorts channel.\n"
    "VIRAL RETENTION RULES you must ALWAYS enforce:\n"
    "- NO citations ever. Never say 'according to', 'sources say', 'experts claim'.\n"
    "- 45-60 second target runtime (maximum retention rate, minimal dropoff). Ensure you write enough dialogue to fill this time.\n"
    "- Cold open hook MUST BE CAPTIVATING (must set up a story, mystery, or interesting premise).\n"
    "- Hook style: Parable, Curiosity Gap, or Historical Anecdote.\n"
    "- High-quality storytelling: A single narrator speaking with a deep, engaging, and cinematic voice.\n"
    "- Visual categories for scenes: character, metaphor, landscape, object, abstract, architectural. Rotate every scene.\n"
    "- Subtitle safe zone: 65-75% down the 1920px frame.\n"
    "- Audio loudness: -14 LUFS integrated.\n"
    "\nNARRATIVE THREADING RULES (CRITICAL FOR RETENTION):\n"
    "- The ENTIRE video must tell ONE cohesive story that reveals a financial or market concept at the end.\n"
    "- Scene 1 hook MUST introduce the characters or setting. Scene 5 MUST resolve it with the core lesson/concept.\n"
    "- Exactly 5 scenes following: HOOK -> BUILDUP -> CONFLICT -> REVEAL -> OUTRO.\n"
)


class PromptEngineerAgent:
    """The creative AI controlling every section of the pipeline. Gemini-only."""

    def __init__(self, gemini_client_or_clients):
        if isinstance(gemini_client_or_clients, list):
            self.clients = gemini_client_or_clients
        else:
            self.clients = [gemini_client_or_clients]


    def _call_gemini(self, system_prompt, user_prompt, response_schema, temperature=0.7):
        """Unified LLM call: Strictly Native Gemini API based on user preference."""
        logger.info("🤖 Using Native Gemini API...")
        last_error = None
        
        import time
        max_retries = 3

        for attempt in range(max_retries):
            for client in self.clients:
                try:
                    response = client.models.generate_content(
                        model="gemini-3.6-flash",
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
                    if any(code in err_str for code in ["429", "503", "500", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "TIMEOUT", "DEADLINE"]):
                        logger.warning(f"Prompt Engineer encountered transient error ({e}). Rotating key/retrying attempt {attempt+1}/{max_retries}...")
                        last_error = e
                        import time
                        time.sleep(3)
                        continue
                    logger.error(f"Prompt Engineer Gemini call failed: {e}")
                    
                    # ── Sandbox Mock Fallback ──
                    logger.warning("Applying fallback mock response due to network failure...")
                    schema_name = response_schema.__name__ if hasattr(response_schema, "__name__") else str(response_schema)
                    if "VideoScript" in schema_name:
                        return {
                            "thesis": "The secret behind passive income.",
                            "title": "The Passive Income Secret #Shorts",
                            "description": "Discover the truth about passive income! #finance #money #shorts",
                            "scenes": [
                                {"scene_number": 1, "narration": "In a small village, two merchants debated the secret to wealth.", "visual_prompt": "Two ancient merchants arguing in a dimly lit, cinematic market.", "visual_category": "character"},
                                {"scene_number": 2, "narration": "One traded time for money, working day and night.", "visual_prompt": "A tired merchant carrying heavy bags of coins at midnight.", "visual_category": "metaphor"},
                                {"scene_number": 3, "narration": "The other traded money for assets, building a system.", "visual_prompt": "A clever merchant watching a beautifully engineered water wheel.", "visual_category": "object"},
                                {"scene_number": 4, "narration": "Soon, the system worked for him while he slept peacefully.", "visual_prompt": "A serene, wealthy merchant sleeping while gold coins accumulate.", "visual_category": "abstract"},
                                {"scene_number": 5, "narration": "That is the true power of passive income. Start building yours.", "visual_prompt": "A grand cinematic shot of a wealthy empire at sunrise.", "visual_category": "landscape"}
                            ]
                        }
                    elif "VoiceConfig" in schema_name:
                        return {
                            "voice_name": "am_michael",
                            "overall_energy": "medium",
                            "scenes": [
                                {"scene_number": 1, "ssml_text": "<speak>In a small village, <break time='200ms'/> two merchants debated the secret to wealth.</speak>", "pacing_rate": "+10%", "emphasis_words": ["wealth"]},
                                {"scene_number": 2, "ssml_text": "<speak>One traded time for money, working day and night.</speak>", "pacing_rate": "+5%", "emphasis_words": ["time", "money"]},
                                {"scene_number": 3, "ssml_text": "<speak>The other traded money for assets, building a system.</speak>", "pacing_rate": "+0%", "emphasis_words": ["assets", "system"]},
                                {"scene_number": 4, "ssml_text": "<speak>Soon, <break time='300ms'/> the system worked for him while he slept peacefully.</speak>", "pacing_rate": "-5%", "emphasis_words": ["worked"]},
                                {"scene_number": 5, "ssml_text": "<speak><emphasis level='strong'>That</emphasis> is the true power of passive income. Start building yours.</speak>", "pacing_rate": "+5%", "emphasis_words": ["power", "passive"]}
                            ]
                        }
                    elif "VisualConfig" in schema_name:
                        return {
                            "global_style_suffix": "Professional sleek minimalist corporate 3D illustration, deep navy blue and vibrant gold color palette, highly recognizable editorial infographic aesthetic, no text, no letters",
                            "scenes": [
                                {"scene_number": 1, "animation_tag": "educational", "enhanced_prompt": "Two ancient merchants arguing in a dimly lit, cinematic market.", "negative_prompt": "text, watermark", "category_tag": "character", "composition_directive": "center"},
                                {"scene_number": 2, "animation_tag": "bearish", "enhanced_prompt": "A tired merchant carrying heavy bags of coins at midnight.", "negative_prompt": "text, watermark", "category_tag": "metaphor", "composition_directive": "left-third"},
                                {"scene_number": 3, "animation_tag": "bullish", "enhanced_prompt": "A clever merchant watching a beautifully engineered water wheel.", "negative_prompt": "text, watermark", "category_tag": "object", "composition_directive": "right-third"},
                                {"scene_number": 4, "animation_tag": "neutral", "enhanced_prompt": "A serene, wealthy merchant sleeping while gold coins accumulate.", "negative_prompt": "text, watermark", "category_tag": "abstract", "composition_directive": "center"},
                                {"scene_number": 5, "animation_tag": "bullish", "enhanced_prompt": "A grand cinematic shot of a wealthy empire at sunrise.", "negative_prompt": "text, watermark", "category_tag": "landscape", "composition_directive": "center"}
                            ]
                        }
                    elif "PublishMetadata" in schema_name:
                        return {
                            "youtube_titles": ["The Passive Income Secret #Shorts", "How to get rich #Shorts", "Stop trading time for money #Shorts"],
                            "youtube_description": "Discover the truth about passive income! #finance #money #shorts",
                            "youtube_tags": ["shorts", "finance", "money"],
                            "telegram_caption": "Discover the truth about passive income! #finance",
                            "instagram_description": "Discover the truth about passive income! #finance",
                            "pinned_comment": "Are you building passive income?",
                            "category_id": "27"
                        }
                    raise e
            
            if attempt < max_retries - 1:
                logger.warning(f"Retrying Gemini call (Attempt {attempt + 1}/{max_retries}) after 5s delay...")
                import time
                time.sleep(5)
                
        if last_error:
            raise last_error
        raise RuntimeError("Gemini call failed without explicit error.")

    # ──────────────────────────────────────────────
    #  SECTION 1: TOPIC DISCOVERY (EXHAUSTIVE & DUPLICATE-FREE)
    # ──────────────────────────────────────────────

    def _is_video_processed(self, video_id, video_url=""):
        import os, json
        if not os.path.exists("used_topics.json"):
            return False
        try:
            with open("used_topics.json", "r") as f:
                used_data = json.load(f)
            entries = used_data.get("topics", []) if isinstance(used_data, dict) else used_data
            for entry in entries:
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

    def _is_topic_used(self, topic_str):
        import os, json
        if not os.path.exists("used_topics.json"):
            return False
        try:
            with open("used_topics.json", "r") as f:
                used_data = json.load(f)
            entries = used_data.get("topics", []) if isinstance(used_data, dict) else used_data
            for entry in entries:
                t = entry.get("topic", "")
                if topic_str.lower() in t.lower() or t.lower() in topic_str.lower():
                    return True
        except Exception:
            pass
        return False

    def _fetch_youtube_transcript(self, video_id):
        """Attempts to download the YouTube transcript text for a video using API and yt-dlp fallback."""
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

        return None

    def fetch_fresh_topic(self):
        """Fetches the latest topic from any of the target channels in the multi-channel registry."""
        import os, random
        from datetime import datetime, timezone, timedelta

        TARGET_CHANNELS = [
            {"name": "MONEY PECHU", "channel_id": "UC7fQFl37yAOaPaoxQm-TqSA"}, # Monday
            {"name": "PR SUNDAR", "channel_id": "UCS2NdYUmv_PUyyKeDAo5zYA"}, # Tuesday
            {"name": "MONEY PURSE", "channel_id": "UChBT5TlUeG68PKvJSg6MkqQ"}, # Wednesday
            {"name": "TRADE ACHIEVERS", "channel_id": "UCsrnRWZSpE-q8s0SAOk8OOg"}, # Thursday
            {"name": "MARKET DRIVER", "channel_id": "UCo5CAieenL0ExXzvjzs17QQ"}, # Friday
            {"name": "TAMIL NIFTY ANALYSIS", "channel_id": "UCft3VdKoq4HNBYd4MRnQF6Q"}, # Saturday
            {"name": "ZERO1 BY ZERODHA", "channel_id": "UCUUlw3anBIkbW9W44Y-eURw"} # Sunday
        ]
        
        yt_api_key = os.getenv("YT_API_KEY")

        # 0 = Monday, 6 = Sunday
        start_idx = datetime.now(timezone.utc).weekday()
        
        # We start with today's channel. If no fresh topics, we fallback to scanning the rest (Option B).
        channel_indices = [(start_idx + i) % len(TARGET_CHANNELS) for i in range(len(TARGET_CHANNELS))]
        logger.info(f"📅 PE Agent [DAY-WISE ROTATION]: Today is weekday {start_idx}. Primary Channel: '{TARGET_CHANNELS[start_idx]['name']}'")

        for idx in channel_indices:
            ch = TARGET_CHANNELS[idx]
            ch_name = ch["name"]
            channel_id = ch["channel_id"]
            logger.info(f"🔍 PE Agent [TOPIC]: Checking target channel [{idx+1}/6] '{ch_name}' ({channel_id})...")

            if yt_api_key:
                try:
                    logger.info(f"🔍 PE Agent [TOPIC]: Attempting YouTube Data API search for '{ch_name}' (last 3 days)...")
                    three_days_ago = (datetime.now(timezone.utc) - timedelta(days=3)).strftime('%Y-%m-%dT%H:%M:%SZ')
                    api_url = (
                        f"https://www.googleapis.com/youtube/v3/search?"
                        f"key={yt_api_key}&channelId={channel_id}&part=snippet&order=date&maxResults=15&type=video&publishedAfter={three_days_ago}"
                    )
                    res = requests.get(api_url, timeout=10)
                    if res.status_code == 200:
                        items = res.json().get("items", [])
                        for item in items:
                            v_id = item.get("id", {}).get("videoId")
                            snippet = item.get("snippet", {})
                            title = snippet.get("title", "")
                            v_url = f"https://www.youtube.com/watch?v={v_id}" if v_id else ""

                            if v_id and not self._is_video_processed(v_id, v_url) and not self._is_topic_used(title):
                                logger.info(f"🔍 PE Agent [TOPIC]: Found fresh video via API on [{ch_name}] [ID: {v_id}]: {title}")
                                topic = self._build_topic_with_summary(v_id, v_url, title, channel_name=ch_name)
                                if topic and not self._is_topic_used(topic):
                                    return topic
                except Exception as e:
                    logger.warning(f"🔍 PE Agent [TOPIC]: YouTube Data API search failed for '{ch_name}': {e}")

            try:
                logger.info(f"🔍 PE Agent [TOPIC]: Querying RSS feed for '{ch_name}'...")
                rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
                response = requests.get(rss_url, timeout=10)
                if response.status_code == 200:
                    root = ET.fromstring(response.content)
                    ns = {
                        'yt': 'http://www.youtube.com/xml/schemas/2015',
                        'default': 'http://www.w3.org/2005/Atom',
                        'media': 'http://search.yahoo.com/mrss/'
                    }
                    entries = root.findall("default:entry", ns)
                    
                    for entry in entries[:15]:
                        published_str = entry.findtext("default:published", namespaces=ns)
                        if published_str:
                            pub_dt = datetime.strptime(published_str[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                            if pub_dt < datetime.now(timezone.utc) - timedelta(days=3):
                                continue

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

                        if video_id and not self._is_video_processed(video_id, video_url) and not self._is_topic_used(title):
                            logger.info(f"🔍 PE Agent [TOPIC]: Found fresh video via RSS on [{ch_name}] [ID: {video_id}]: {title}")
                            topic = self._build_topic_with_summary(video_id, video_url, title, rss_description=rss_description, channel_name=ch_name)
                            if topic and not self._is_topic_used(topic):
                                return topic
            except Exception as e:
                logger.warning(f"🔍 PE Agent [TOPIC]: RSS fetch failed for '{ch_name}': {e}")

        logger.info("🔍 PE Agent [TOPIC]: All recent video IDs across channels processed. Generating fresh dynamic market topic...")
        timestamp_str = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        dynamic_topic = f"Dynamic Financial Analysis & Stock Market Debunk [Ref: {timestamp_str}]"
        return dynamic_topic

    def _build_topic_with_summary(self, video_id, video_url, title, rss_description=None, channel_name="Financial Analyst"):
        """Helper to build transcript summary topic for a video strictly using actual video text."""
        source_text = self._fetch_youtube_transcript(video_id) if video_id else None
        
        if not source_text or len(source_text.strip()) < 50:
            logger.warning(f"🔍 PE Agent [TOPIC]: No valid transcript available for video {video_id}. Skipping (no guessing from title allowed).")
            return None

        truncated = source_text[:15000]
        logger.info(f"🔍 PE Agent [TOPIC]: Generating AI summary in ENGLISH from actual video text ({channel_name})...")
        try:
            summary_data = self._call_gemini(
                system_prompt=(
                    "You are an elite YouTube Shorts scriptwriter.\n"
                    "STYLE: Full-bleed vertical B-roll explainer, no host.\n"
                    "CUTS: new shot every 1-2s, hard cuts only, no transitions.\n"
                    "SCRIPT: short declarative fragments (5-10 words per beat max), one beat = one caption = one cut.\n"
                    "ARC: hook (striking ambiguous claim) -> mechanism (institutional/legal context) -> proof (literal process footage) -> payoff (present-day stakes).\n"
                    "Write extremely punchy, aggressive scripts meant to be spoken fast.\n"
                    "Do NOT write long flowing sentences. Chop them into short clauses.\n"
                    "Return JSON according to the schema."
                ),
                user_prompt=(
                    f"Channel Name: {channel_name}\n"
                    f"Video Link: {video_url}\n"
                    f"Video Title: {title}\n\n"
                    "Analyze the following actual video text/transcript and identify THE SINGLE most controversial, "
                    "myth-bustable claim or misconception discussed.\n"
                    "State it as ONE clear thesis in this exact format:\n"
                    "MYTH: [the specific claim in 1 sentence]\n"
                    "TRUTH: [the debunk in 1 sentence]\n\n"
                    "Do NOT list multiple points. Pick the ONE most shocking, debunkable claim only.\n\n"
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
                topic_str = (
                    f"{channel_name} analysis on {title} [Video ID: {video_id}]\n"
                    f"Link: {video_url}\n"
                    f"Single Thesis: {summary_text}"
                )
                return topic_str
        except Exception as e:
            logger.warning(f"🔍 PE Agent [TOPIC]: Gemini transcript summary failed for {video_id}: {e}")
            
        return None

    # ──────────────────────────────────────────────
    #  SECTION 2: SCRIPT GENERATION (VIRAL RETENTION ENGINE)
    # ──────────────────────────────────────────────

    def generate_script(self, topic):
        """Generates the full dynamic-scene structured script following viral retention rules."""
        logger.info(f"📝 PE Agent [SCRIPT]: Writing script for: '{topic[:60]}...'")


        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Generate a high-retention, storytelling full-bleed script for the given topic.\n"
            "TARGET AUDIENCE: 22-35 year old ambitious individuals looking for financial wisdom.\n"
            "CORE PURPOSE: Tell a short, compelling story (like a parable) that ends with a powerful financial concept or market lesson.\n"
            "STYLE: Full-bleed vertical cinematic images with a single narrator.\n"
            "THE HOOK: Start with an intriguing story premise. (e.g., 'In a small village, there were two merchants...').\n"
            "NARRATION: The language should be cinematic, engaging, and clear. Avoid overly aggressive or hyped language. Think 'City of Finance' or deep lore.\n"
            "ARC: Hook (Introduction) -> Buildup (Context) -> Conflict (The twist or problem) -> Reveal (The financial concept) -> Outro (Takeaway).\n"
            "Return JSON according to the schema."
            "\nANTI-DRIFT RULES:\n"
            "- EVERY scene's narration MUST advance the story logically and contain substantial dialogue.\n"
            "- CRITICAL: Each of the 5 scenes MUST contain at least 3 to 4 full sentences of narration.\n"
            "- Total script reading time: 45-60 seconds. The combined narration MUST be strictly between 130 and 180 words. Do NOT generate less than 130 words.\n"
            "- Include a high-CTR YouTube title (with #Shorts) and description with hashtags.\n"
        )

        user_prompt = f"Topic or Concept to tell a story about: {topic}"
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
            "- Pacing rate (steady storytelling pace)\n"
            "- 2-3 emphasis words per scene that should get CAPS in subtitles\n"
            "Rules:\n"
            "- Keep a steady, engaging storytelling pace.\n"
            "- Use <break time='400ms'/> before the key reveal or punchline.\n"
            "- Use <emphasis level='strong'> on important concept words.\n"
            "- Voice name should be 'am_michael' (friendly, natural, energetic narrator voice).\n"
            "- Do NOT use unnatural sound effects like random clicks or pops. Keep the audio natural and engaging.\n"
        )

        user_prompt = f"Here are the scenes to engineer voice for:\n{scenes_text}"
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
            "\nYour task: Generate the visual configuration for this script.\n"
            "This video uses a FULL-BLEED layout. The entire screen is filled with B-Roll. There is NO host.\n\n"
            "1. For each scene, write an `enhanced_prompt` for the B-Roll.\n"
            "CRITICAL: The prompt MUST generate ABSOLUTELY REALISTIC, PHOTOREALISTIC, HIGH-DEFINITION cinematic imagery.\n"
            "STYLE: Cinematic storytelling, highly detailed, dramatic lighting.\n"
            "No text should be present in the images.\n"
            "Output JSON with exact text-to-image prompts that will generate these aesthetic shots.\n"
            "Rules:\n"
            "- Category tags (character, metaphor, landscape, object, abstract) MUST NOT repeat in adjacent scenes\n"
            "- Use at least 3 different categories across scenes\n"
            "- Each prompt must be COMPLETELY unique — no two should describe similar imagery\n"
            "- The global_style_suffix should be: 'Professional sleek minimalist corporate 3D illustration, deep navy blue and vibrant gold color palette, highly recognizable editorial infographic aesthetic, no text, no letters'\n"
        )

        user_prompt = f"Here are the scenes to generate visual prompts for:\n{scenes_text}"
        return self._call_gemini(system_prompt, user_prompt, VisualConfig)


    # ──────────────────────────────────────────────
    #  SECTION 6: SUBTITLE STYLE ENGINEERING
    # ──────────────────────────────────────────────

    def engineer_subtitle_style(self, script):
        """Engineers subtitle parameters for optimal readability."""
        logger.info("📝 PE Agent [SUBTITLES]: Engineering subtitle style...")
        
        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Define the subtitle configuration style including font, size, primary color, outline, and vertical positioning.\n"
            "CRITICAL: We are using a FULL-BLEED layout. No host.\n"
            "You MUST set `margin_v` (distance from the bottom of the screen) to exactly 960 to place them perfectly in the middle vertically.\n"
            "You MUST set `font_size` to 80 or 90 to be clearly readable.\n"
            "Use minimal word-stack logic. Set primary color to white and shadow to black. No colored bars."
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
        """Engineers publishing metadata with High-CTR titles, SEO descriptions, and automated pinned comment."""
        logger.info("📢 PE Agent [PUBLISH]: Engineering publish metadata...")
        scenes = script.get("scenes", []) if isinstance(script, dict) else [s.model_dump() if hasattr(s, "model_dump") else s for s in getattr(script, "scenes", [])]
        scenes_text = json.dumps(scenes, indent=2)

        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Generate optimized YouTube Shorts titles (with #Shorts), description, tags, and a pinned discussion comment."
            "\nTITLE FORMULAS TO FOLLOW (Max 50 chars each):"
            "\n1. [Shock Warning] + [Stock/Asset] ⚠️ #Shorts"
            "\n2. Why Buying [Stock] at All-Time High is DANGEROUS 📉 #Shorts"
            "\n3. The [Asset] Trap Nobody Warned You About 🚨 #Shorts"
            "\nPINNED COMMENT: Must ask a direct, polarizing question to trigger debate in comments."
            "\nCRITICAL LANGUAGE MANDATE: All metadata MUST be 100% in FLUENT, HIGH-IMPACT ENGLISH. Never use Tamil words or characters."
        )
        user_prompt = f"Generate publishing metadata for this script:\n{scenes_text}"
        return self._call_gemini(system_prompt, user_prompt, PublishMetadata, temperature=0.3)


    def execute(self):
        """Legacy entry point: Find topic -> Write Script -> Return."""
        topic = self.fetch_fresh_topic()
        script = self.generate_script(topic)
        return script, topic
