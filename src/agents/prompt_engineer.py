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
    "- 110-140 second target runtime (maximum retention rate, minimal dropoff). Ensure you write enough dialogue to fill this time.\n"
    "- Hook style: Unexplained paradox or contrast stated up front.\n"
    "- High-quality storytelling: A single narrator speaking with a deep, engaging, and cinematic voice.\n"
    "- Audio loudness: -14 LUFS integrated.\n"
    "- Music: gentle ambient acoustic/folk instrumental, calm and melodic.\n"
    "\nNARRATIVE THREADING RULES (CRITICAL FOR RETENTION):\n"
    "- The ENTIRE video must be a Parable with an ensemble cast (usually 2 characters) embodying opposing economic positions.\n"
    "- Exactly 8 scenes following this EXACT arc:\n"
    "  1. Cold open (paradox/hook)\n"
    "  2. Introduce character A (investment/cost)\n"
    "  3. Introduce character B (lack of resources)\n"
    "  4. Complication (uncontrollable variable)\n"
    "  5. Twist (shown visually before it is explained)\n"
    "  6. Harvest/payoff (outcome disparity)\n"
    "  7. Concept Named (definition and diagram)\n"
    "  8. Modern real-world analogy (closing)\n"
    "- Never explain the concept before scene 7 — the story must do the persuading first.\n"
)


class PromptEngineerAgent:
    """The creative AI controlling every section of the pipeline. Gemini-only."""

    def __init__(self, api_keys, openrouter_key=None, nvidia_key=None, groq_key=None):
        self.api_keys = api_keys if isinstance(api_keys, list) else [api_keys]
        from google import genai
        self.clients = [genai.Client(api_key=k) for k in self.api_keys if k]
        self.current_client_idx = 0
        self.openrouter_key = openrouter_key
        self.nvidia_key = nvidia_key
        self.groq_key = groq_key


    def _call_gemini(self, system_prompt, user_prompt, response_schema, temperature=0.7):
        """Unified LLM call: Tries Gemini, falls back to OpenRouter, then NVIDIA."""
        import time
        max_retries = 3

        if self.clients:
            logger.info("🤖 Using Native Gemini API...")
            for attempt in range(max_retries):
                for i in range(len(self.clients)):
                    self.current_client_idx = (self.current_client_idx + 1) % len(self.clients)
                    client = self.clients[self.current_client_idx]
                    
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

                        time.sleep(2.5)

                        if hasattr(response, "parsed") and response.parsed:
                            data = response.parsed
                            if hasattr(data, "model_dump"):
                                return data.model_dump()
                            return data

                        return json.loads(response.text)
                        
                    except Exception as e:
                        err_str = str(e).upper()
                        if any(code in err_str for code in ["429", "503", "500", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "TIMEOUT", "DEADLINE"]):
                            logger.warning(f"Gemini error (429/503) on Key {self.current_client_idx + 1}.")
                            
                            if i < len(self.clients) - 1:
                                logger.info(f"Hot-swapping to next available Gemini Key...")
                                continue
                                
                            logger.warning(f"All Gemini keys exhausted.")
                            break # Break inner loop
                        logger.error(f"Prompt Engineer Gemini call failed: {e}")
                
                # If we broke out of the inner loop due to exhaustion, we break the outer loop to trigger fallback
                break

        # --- FALLBACK TO GROQ ---
        if self.groq_key:
            logger.info("🤖 Falling back to Groq (groq/compound)...")
            try:
                import openai
                import re
                client = openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=self.groq_key)
                schema_dict = response_schema.model_json_schema() if hasattr(response_schema, "model_json_schema") else response_schema.schema()
                response = client.chat.completions.create(
                    model="groq/compound",
                    messages=[
                        {"role": "system", "content": system_prompt + "\n\nYou MUST return a valid JSON object matching this schema:\n" + json.dumps(schema_dict)},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=temperature,
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content
                match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
                if match:
                    content = match.group(1)
                return json.loads(content.strip())
            except Exception as e:
                logger.error(f"Groq call failed: {e}")

        # --- FALLBACK TO OPENROUTER ---
        if self.openrouter_key:
            logger.info("🤖 Falling back to OpenRouter (google/gemini-1.5-flash)...")
            try:
                import openai
                import re
                client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=self.openrouter_key)
                schema_dict = response_schema.model_json_schema() if hasattr(response_schema, "model_json_schema") else response_schema.schema()
                response = client.chat.completions.create(
                    model="google/gemini-1.5-flash",
                    messages=[
                        {"role": "system", "content": system_prompt + "\n\nYou MUST return a valid JSON object matching this schema:\n" + json.dumps(schema_dict)},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=temperature,
                    response_format={"type": "json_object"}
                )
                content = response.choices[0].message.content
                match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
                if match:
                    content = match.group(1)
                return json.loads(content.strip())
            except Exception as e:
                logger.error(f"OpenRouter call failed: {e}")

        # --- FALLBACK TO NVIDIA NIM ---
        if self.nvidia_key:
            logger.info("🤖 Falling back to NVIDIA NIM (meta/llama-3.1-70b-instruct)...")
            try:
                import openai
                import re
                client = openai.OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=self.nvidia_key)
                schema_dict = response_schema.model_json_schema() if hasattr(response_schema, "model_json_schema") else response_schema.schema()
                response = client.chat.completions.create(
                    model="meta/llama-3.1-70b-instruct",
                    messages=[
                        {"role": "system", "content": system_prompt + "\n\nYou MUST return a valid JSON object exactly matching this schema:\n" + json.dumps(schema_dict)},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=temperature,
                    max_tokens=2048,
                )
                content = response.choices[0].message.content.strip()
                match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
                if match:
                    content = match.group(1)
                return json.loads(content.strip())
            except Exception as e:
                logger.error(f"NVIDIA NIM call failed: {e}")
                
        raise RuntimeError("All LLM APIs (Gemini, Groq, OpenRouter, NVIDIA NIM) failed to generate a valid response.")
                    

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
            "CORE PURPOSE: Tell a short, compelling parable that ends with a powerful financial concept or market lesson.\n"
            "STYLE: Full-bleed vertical cinematic images with a single narrator.\n"
            "THE HOOK: Start with an intriguing story paradox (e.g., 'One merchant spent 1,000 gold coins, yet his neighbor pocketed the largest fortune...').\n"
            "NARRATION: The language should be cinematic, engaging, and clear. Avoid overly aggressive or hyped language. Think 'storybook narrator'.\n"
            "CAST: You MUST define the `cast` list with the 2+ characters and their visual descriptions.\n"
            "ARC: Exactly 8 scenes (Hook, Intro A, Intro B, Complication, Twist, Payoff, Concept, Analogy).\n"
            "Return JSON according to the schema."
            "\nANTI-DRIFT RULES:\n"
            "- EVERY scene's narration MUST advance the story logically and contain substantial dialogue.\n"
            "- CRITICAL: Each of the 8 scenes MUST contain at least 2 to 4 full sentences of narration.\n"
            "- Total script reading time: 110-140 seconds. The combined narration MUST be strictly between 230 and 280 words.\n"
            "- NEVER use citation language like 'reports show', 'according to', 'sources say', 'experts claim', 'study shows', 'research indicates', 'data suggests', or 'analysts say'.\n"
            "- CRITICAL: No adjacent scenes can share the same `visual_category`. You MUST alternate categories.\n"
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
            "CRITICAL: The prompt MUST generate a flat/painted 2D digital illustration. Storybook-adjacent but adult-appropriate detail density. Do NOT generate photorealism or 3D renders.\n"
            "STYLE: flat 2D storybook illustration, painted digital art, muted earthy tones\n"
            "Output JSON with exact text-to-image prompts that will generate these aesthetic shots.\n"
            "Rules:\n"
            "- Ground each scene's image prompt in the literal content of the script line (e.g. 'counting gold coins' -> hand counting gold coins).\n"
            "- Composition per shot: single clear subject or action per frame, no competing focal points.\n"
            "- Tie color/light to the narrative mood: Season progression (cool indoor -> warm pastoral -> golden autumn) tracks the story's arc.\n"
            "- Include specific character descriptions in the prompt based on the `character_focus` for that scene (Read the descriptions from the `cast` list in the script!).\n"
            "- The global_style_suffix should be: 'flat 2D storybook illustration, painted digital art, highly detailed, no text overlays, no letters'\n"
            "- AGGRESSIVELY populate the `negative_prompt` field with: 'photorealistic, 3D render, photography, text, watermark, blurry'\n"
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
