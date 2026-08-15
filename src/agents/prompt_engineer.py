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
from .nvidia_client import NvidiaClient

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  FRAMEWORK RULES (injected into every LLM call)
# ──────────────────────────────────────────────
FRAMEWORK_RULES = (
    "You are the Lead Growth & Creative AI for a high-velocity, viral daily 30-50 second "
    "tech/finance Edutainment Short hosted by a fast-paced energetic Tech Host.\n"
    "VIRAL RETENTION RULES you must ALWAYS enforce:\n"
    "- NO citations ever. Never say 'according to', 'sources say', 'experts claim'.\n"
    "- 35-50 second target runtime (maximum retention rate, minimal dropoff).\n"
    "- Cold open hook MUST BE 3 TO 5 PUNCHY WORDS MAXIMUM (must complete speech under 1.8 seconds).\n"
    "- Hook style: Loss Aversion, Number Shock, or Contradiction.\n"
    "- High-energy dialogue: A single host speaking directly to the camera with extreme confidence and pace.\n"
    "- 1-2 punchy sentences per scene with CAPS on 1-2 stressed impact words.\n"
    "- Visual categories for popups: ui, chart, meme, abstract, bold_text, none. Rotate every scene.\n"
    "- Color grade: light slate (#F4F6F9) base, dark accents.\n"
    "- Subtitle safe zone: 65-75% down the 1920px frame.\n"
    "- Audio loudness: -14 LUFS integrated.\n"
    "\nNARRATIVE THREADING RULES (CRITICAL FOR RETENTION):\n"
    "- The ENTIRE video must explore ONE thesis — one topic, tool, or myth. Every scene must directly advance it.\n"
    "- BANNED: Introducing new topics, tangents, or 'also...' transitions mid-video.\n"
    "- Scene 1 hook MUST state the thesis. Scene 5 MUST resolve it.\n"
    "- If a sentence doesn't directly support the thesis → DELETE IT.\n"
    "- The 'thesis' field must be filled with the core topic in max 15 words.\n"
    "- Exactly 5 scenes following: HOOK → INTRO → POINT 1 → POINT 2 → OUTRO.\n"
)


class PromptEngineerAgent:
    """The creative AI controlling every section of the pipeline with NVIDIA NIM & Gemini engines."""

    def __init__(self, gemini_client_or_clients):
        if isinstance(gemini_client_or_clients, list):
            self.clients = gemini_client_or_clients
        else:
            self.clients = [gemini_client_or_clients]
        try:
            self.nvidia = NvidiaClient()
        except Exception as e:
            logger.warning(f"Could not initialize NvidiaClient: {e}. Falling back to Gemini.")
            self.nvidia = None

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
                    if any(code in err_str for code in ["429", "503", "500", "RESOURCE_EXHAUSTED", "UNAVAILABLE", "TIMEOUT", "DEADLINE"]):
                        logger.warning(f"Prompt Engineer encountered transient error ({e}). Rotating key/retrying attempt {attempt+1}/{max_retries}...")
                        last_error = e
                        import time
                        time.sleep(3)
                        continue
                    logger.error(f"Prompt Engineer Gemini call failed: {e}")
                    raise
            
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
        from datetime import datetime, timezone

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
                    logger.info(f"🔍 PE Agent [TOPIC]: Attempting YouTube Data API search for '{ch_name}'...")
                    api_url = (
                        f"https://www.googleapis.com/youtube/v3/search?"
                        f"key={yt_api_key}&channelId={channel_id}&part=snippet&order=date&maxResults=15&type=video"
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
        
        if not source_text and rss_description and len(rss_description.strip()) > 50:
            logger.info(f"🔍 PE Agent [TOPIC]: Using detailed RSS video description fallback for {video_id}")
            source_text = rss_description

        if not source_text or len(source_text.strip()) < 20:
            logger.warning(f"🔍 PE Agent [TOPIC]: No transcript or description available for video {video_id}. Skipping (no guessing from title).")
            return None

        truncated = source_text[:15000]
        logger.info(f"🔍 PE Agent [TOPIC]: Generating AI summary in ENGLISH from actual video text ({channel_name})...")
        try:
            summary_data = self._call_gemini(
                system_prompt=(
                    "You are an expert financial market analyst and mythbuster. "
                    "CRITICAL LANGUAGE MANDATE: Regardless of the source language (Tamil, Telugu, etc.), "
                    "you MUST translate all financial insights, market analysis, and summaries into 100% FLUENT, NATIVE ENGLISH.\n"
                    "CRITICAL: You must identify THE SINGLE most controversial, debunkable claim or misconception from this video. "
                    "Do NOT list multiple insights. Anchor everything to ONE myth."
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

        # Use NVIDIA NIM to brainstorm 3 ultra-punchy viral hooks if available
        suggested_hook = ""
        if self.nvidia:
            try:
                hook_res = self.nvidia.generate_json(
                    prompt=f"Topic: {topic}\nBrainstorm ONE ultra-punchy 3-5 word viral hook in English for a YouTube Short (e.g. 'STOP Buying This Stock!', 'The ₹50,000 ATH Trap!').",
                    system_prompt="You are a YouTube Shorts hook engineer. Output JSON with key 'hook'."
                )
                suggested_hook = hook_res.get("hook", "")
                if suggested_hook:
                    logger.info(f"🔥 NVIDIA NIM Brainstormed Hook: '{suggested_hook}'")
            except Exception as e:
                logger.warning(f"NVIDIA hook brainstorming skipped: {e}")

        system_prompt = (
            FRAMEWORK_RULES +
            "\nYour task: Generate a high-voltage FAST-PACED SINGLE-HOST script (5 scenes) for the given topic.\n"
            "CHARACTERS:\n"
            "  1. 'host': A highly energetic tech/finance creator speaking directly to the camera.\n\n"
            "CRITICAL LANGUAGE MANDATE: The ENTIRE script narration MUST be written in 100% FLUENT, NATIVE ENGLISH.\n"
            "\nSINGLE-THESIS STRUCTURE (EXACTLY 5 SCENES):\n"
            "First, fill the 'thesis' field with THE core topic (max 15 words).\n"
            "Then write exactly 5 scenes following this arc:\n"
            "  Scene 1 — HOOK: 3-5 word ultra-punchy shock statement directly stating the thesis" + (f" (e.g. '{suggested_hook}')" if suggested_hook else "") + ".\n"
            "  Scene 2 — INTRO: Setup the problem or the context. Keep it under 2 sentences.\n"
            "  Scene 3 — POINT 1: The first major data point, tool feature, or insight. popup_text='[Key Stat 1]'.\n"
            "  Scene 4 — POINT 2: The definitive reveal or second insight. popup_text='[REVEAL]'.\n"
            "  Scene 5 — OUTRO: Final takeaway + call to action ('Follow for daily videos').\n"
            "\nANTI-DRIFT RULES:\n"
            "- EVERY scene's narration MUST reference the same thesis from Scene 1.\n"
            "- BANNED: introducing new topics, tangents, 'also...' transitions, or secondary arguments.\n"
            "- Total script reading time: 35-50 seconds.\n"
            "- Include a high-CTR YouTube title (with #Shorts) and description with hashtags.\n"
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
            "- Scene 1 (hook): FASTEST PACING (+25% to +30%) to hook viewer in under 1.8 seconds.\n"
            "- Setup scenes: energetic pacing (+15% to +20%)\n"
            "- Reveal scene: dramatic pacing (+5% to +10%), add <break time='350ms'/> before the key reveal\n"
            "- Final scene (CTA): clear punchy pacing (+10%)\n"
            "- Use <emphasis level='strong'> on reveal words\n"
            "- Voice name should be 'Adam' for ElevenLabs\n"
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
            "This video uses a SPLIT-SCREEN layout. The top half displays your generated B-Roll, and the bottom half is the host.\n\n"
            "1. For each scene, write an `enhanced_prompt` for the top-half B-Roll.\n"
            "CRITICAL: The prompt MUST generate ABSOLUTELY REALISTIC, PHOTOREALISTIC, HIGH-DEFINITION cinematic photography or stock footage.\n"
            "BAN: DO NOT use words like 'illustration', 'cartoon', 'minimalist', 'vector', 'flat design'. \n"
            "MANDATORY STYLE KEYWORDS: 'photorealistic', 'cinematic lighting', 'high definition', 'real world photography', '8k resolution'.\n"
            "Example: 'A photorealistic wide shot of a bustling Wall Street trading floor, cinematic lighting, high contrast, 8k resolution.'\n\n"
            "2. (Optional) Provide a `popup_text` (1-3 words max, e.g., 'CRASH!', '90% LOSS') to display cleanly over the B-Roll.\n"
            "- A negative_prompt to avoid bad generations\n"
            "- A category_tag from: vaults, crowds, paperwork, growth, digital, hands\n"
            "- A composition_directive: center, left-third, right-third, top-heavy, bottom-heavy\n"
            "Rules:\n"
            "- EVERY prompt MUST end with 'bright white and light gray studio background, cinematic lighting, 8k resolution'\n"
            "- Category tags MUST NOT repeat in adjacent scenes\n"
            "- Use at least 3 different categories across scenes\n"
            "- Each prompt must be COMPLETELY unique — no two should describe similar imagery\n"
            "- The global_style_suffix should be: 'cinematic lighting, photorealistic, 8k resolution'\n"
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
            "CRITICAL: We are using a SPLIT-SCREEN layout. The B-Roll is on top (0 to 840), and the host is on the bottom (840 to 1920).\n"
            "You MUST set `margin_v` (distance from the bottom of the screen) to exactly 1050 to 1100. This places the subtitles right at the dividing line (Y=820 to 870), ensuring they never block the host's face!\n"
            "You MUST set `font_size` to 80 or 90 to be clearly readable."
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

        # Use NVIDIA NIM for high-CTR title formulas if available
        nvidia_titles = []
        if self.nvidia:
            try:
                res = self.nvidia.generate_json(
                    prompt=(
                        f"Script Summary:\n{scenes_text}\n\n"
                        "Generate 3 VIRAL YouTube Shorts titles (max 50 chars each, include #Shorts, use 1 alert emoji like 🚨, 📉, ❌, ⚠️) "
                        "using Curiosity-Gap & Loss-Aversion formulas. Also generate 1 controversial pinned_comment question for comments."
                    ),
                    system_prompt="You are a YouTube Shorts viral growth specialist. Return JSON with keys: 'titles' (list of 3 strings), 'pinned_comment' (string)."
                )
                nvidia_titles = res.get("titles", [])
                logger.info(f"🔥 NVIDIA NIM Engineered Titles: {nvidia_titles}")
            except Exception as e:
                logger.warning(f"NVIDIA publish metadata skipped: {e}")

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
        data = self._call_gemini(system_prompt, user_prompt, PublishMetadata, temperature=0.3)
        
        # If NVIDIA generated stronger titles, blend them in
        if nvidia_titles and isinstance(data, dict):
            data["youtube_titles"] = [t if "#Shorts" in t else f"{t} #Shorts" for t in nvidia_titles[:3]]
        
        return data


    def execute(self):
        """Legacy entry point: Find topic -> Write Script -> Return."""
        topic = self.fetch_fresh_topic()
        script = self.generate_script(topic)
        return script, topic
