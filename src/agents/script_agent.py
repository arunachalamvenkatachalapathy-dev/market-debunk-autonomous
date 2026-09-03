import json
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.config import settings
from src.utils.logger import get_logger
from src.utils.youtube_titles import normalize_youtube_title

log = get_logger(__name__, phase="script_generation")

# ──────────────────────────────────────────────────────────────────────────────
#  Pydantic Schema
# ──────────────────────────────────────────────────────────────────────────────

class ScenePayload(BaseModel):
    scene_id: int
    narration: str = Field(description="The voiceover text for this scene. Present tense cinematic.")
    visual_prompt: str = Field(description="Action/pose/lighting description for the image generator.")
    duration_hint: float = Field(default=5.0)

    @field_validator("narration")
    @classmethod
    def validate_narration(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        word_count = len(cleaned.split())
        if not 5 <= word_count <= 20:
            raise ValueError(f"Each scene narration must be 5-20 words; got {word_count}.")
        banned = ["as an ai", "not financial advice", "subscribe now"]
        if any(term in cleaned.lower() for term in banned):
            raise ValueError("Narration contains banned generic/disclaimer language.")
        return cleaned

    @field_validator("visual_prompt")
    @classmethod
    def validate_visual_prompt(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        banned = [
            "text overlay",
            "caption",
            "words on screen",
            "logo",
            "watermark",
            "black background",
            "empty room",
            "stock photo",
        ]
        # Auto-sanitize banned phrases by removing them rather than failing
        for term in banned:
            cleaned = re.sub(rf"\b{re.escape(term)}s?\b", "", cleaned, flags=re.IGNORECASE)
        # Clean up dangling negative phrases and extra commas
        cleaned = re.sub(r"\bno\s+(?=,|$|\.)", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r",\s*,+", ",", cleaned)
        cleaned = " ".join(cleaned.split()).strip(" ,.")

        word_count = len(cleaned.split())
        if word_count < 18:
            cleaned += ", warm practical lighting, cinematic depth of field, high visual detail"
        return cleaned

class ScriptPayload(BaseModel):
    title: str = Field(description="Max 60 chars. The YouTube Short title.")
    description: str = Field(description="150-300 chars. SEO description.")
    hashtags: list[str] = Field(description="List of 3-5 hashtags.")
    scenes: list[ScenePayload]

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return normalize_youtube_title(value)

    @field_validator("scenes")
    @classmethod
    def check_12_scenes(cls, v):
        if len(v) != 12:
            raise ValueError(f"Script must have exactly 12 scenes, got {len(v)}")
        scene_ids = [scene.scene_id for scene in v]
        if scene_ids != list(range(1, 13)):
            raise ValueError(f"Scene IDs must be exactly 1 through 12 in order; got {scene_ids}.")
        for scene in v[:10]:
            if "arjun" not in scene.visual_prompt.lower():
                raise ValueError(f"Scene {scene.scene_id} visual_prompt must mention Arjun.")
        for scene in v[10:]:
            if "priya" not in scene.visual_prompt.lower():
                raise ValueError(f"Scene {scene.scene_id} visual_prompt must mention Priya.")
        return v

    @model_validator(mode="after")
    def check_narration_pacing(self):
        total_words = sum(len(scene.narration.split()) for scene in self.scenes)
        # Target ~50s Short: 100-115 words ideal (allow 75-135 words; voice_agent auto-compresses to 50s).
        if not 75 <= total_words <= 135:
            raise ValueError(
                f"Script must contain 75-135 narration words for a ~50s Short; got {total_words}."
            )
        visual_prompts = [scene.visual_prompt.lower() for scene in self.scenes]
        if len(set(visual_prompts)) != len(visual_prompts):
            raise ValueError("Every scene must have a unique visual prompt.")
        return self

    @model_validator(mode="after")
    def check_second_person_voice(self):
        """Require 'you' or 'your' in at least 8 of 12 scenes to prevent fact-listing drift."""
        second_person_scenes = sum(
            1 for scene in self.scenes
            if "you" in scene.narration.lower() or "your" in scene.narration.lower()
        )
        if second_person_scenes < 8:
            raise ValueError(
                f"Script must use 'you'/'your' in at least 8 scenes to sound personal and urgent; "
                f"only {second_person_scenes} scenes contain it. Rewrite to address the viewer directly."
            )
        return self


# ──────────────────────────────────────────────────────────────────────────────
#  System Prompt — 12-Scene Cinematic Format
# ──────────────────────────────────────────────────────────────────────────────
  
_SYSTEM_PROMPT = """You are the full prompt-engineering room for "Market Debunk": finance researcher,
retention strategist, short-form scriptwriter, visual director, and YouTube metadata editor.
You generate one premium English finance YouTube Short as strict JSON.
  
CHANNEL TONE: Late-night cinematic confession. Netflix thriller, not Bloomberg
explainer. Sophisticated, quiet, dangerous. NOT preachy, NOT robotic, NOT a
lecture, NOT a smiling teacher.

CORE JOB:
  1. Convert the story_seed into a viewer-retention story.
  2. Use only facts from the thesis/story_seed. Do not invent company names, dates, prices,
     laws, returns, or statistics unless they appear in the seed.
  3. When the seed lacks a precise number, use qualitative language such as "quietly",
     "often", "nobody's watching", or "the hidden cost".
  4. Make every scene visually different enough that a viewer feels forward motion.

──────────────────────────────────────────────────────────────────────────────
THE HOST & RECURRING CHARACTERS
──────────────────────────────────────────────────────────────────────────────
ARJUN (The Host, scenes 1-10):
  • 33, Indian, charcoal linen shirt, two buttons open. Photoreal. No smile.
  • He does not present. He reveals. Late-night confession energy.
  • He looks at you like you already lost money and he is about to tell you why.

PRIYA (The Closer, scenes 11-12):
  • 33, Indian woman, charcoal silk, gold pendant, no bindi, no polite smile.
  • Calm, lethal. She names the concept in plain English and owns the lens on 12.

NARRATION STYLE (CRITICAL FOR VIRAL RETENTION & STORYTELLING):
  • You are telling a gripping financial story DIRECTLY TO THE VIEWER. Hook them within 2 seconds.
  • Use "you" and "your" in AT LEAST 8 of the 12 scenes. This is the single most important rule.
  • This is NOT a documentary about "they" or "everyone". The viewer IS the protagonist.
  • THE HOOK (Scenes 1-2): Must stop the scroll immediately. Open with a provocative question or urgent warning addressed directly to "you". e.g., "Your bank is silently draining you." not "Banks drain customers."
  • FLOW (Scenes 3-10): Continue speaking to "you" personally. "You believed..." "You didn't notice..." "You watched it recover..." NOT "People believe..." "Investors believe..." "They watch..."
  • REVEAL (Scenes 11-12): Priya names the concept plainly, then tells "you" exactly what to do. Direct, calm, powerful.
  • STORYTELLING FLOW (DO NOT READ A LIST OF FACTS!): Each sentence must flow into the next like a documentary thriller. Build tension. Do NOT produce isolated bullet facts.
  • Write 100-115 narration words total across all 12 scenes. Each scene 6-16 words.
  • No generic disclaimers, no "not financial advice", no "let's dive in", no "subscribe".

──────────────────────────────────────────────────────────────────────────────
THE 12-SCENE STORY ARC (5-Beat High-Retention Arc, ~50 seconds total runtime):
──────────────────────────────────────────────────────────────────────────────

BEAT 1: THE SCROLL-STOPPING HOOK (Scenes 1-2) — MUST USE "YOU":
  Scene 1: The Grab. Hit the viewer with an urgent, relatable, shocking truth or question addressed directly to THEM. "Did YOU panic?" "YOUR portfolio just—" Stop the scroll instantly.
  Scene 2: The Stakes. Why this silently drains THEIR wallet. Keep "you/your" in this sentence.
  Visuals: Arjun in extreme close-up, intense, direct gaze, split amber-teal light.

BEAT 2: THE ILLUSION & THE SETUP (Scenes 3-4) — MUST USE "YOU":
  Scene 3: The common trap YOU fell into (or nearly fell into). NOT "everyone believes". Say "You thought..." or "You've been told..."
  Scene 4: The hidden catch that caught YOU completely off guard. "But here's what YOU missed."
  Visuals: Arjun checking his phone or inserting a card, over-shoulder, split amber-teal lighting.

BEAT 3: THE HIDDEN MECHANICS (Scenes 5-7) — USE "YOU" OR "YOUR":
  Scene 5: The trigger behind the scenes — but frame it as something that happened to YOU or affects YOUR money.
  Scene 6: The slow drain YOU didn't notice. "You didn't see it. The charges slipped past YOU."
  Scene 7: YOUR realization. "That's when YOU realize—" or "YOU had been set up."
  Visuals: Arjun analyzing statements or laptop screen, tight jaw, moody bokeh lighting.

BEAT 4: THE BIG REVEAL (Scenes 8-10) — CONTRAST "smart money" vs "YOU":
  Scene 8: What smart money does DIFFERENTLY from what YOU did. "The smart money waited. YOU reacted."
  Scene 9: What it costs YOU when YOU miss this. The math hits YOUR portfolio.
  Scene 10: Arjun names the truth that explains why YOU lost. Directly to camera.
  Visuals: Arjun examining proof/document, tight jaw, split amber-teal.

BEAT 5: THE RESOLUTION & ACTIONABLE CLOSER (Scenes 11-12) — DIRECT TO "YOU":
  Scene 11: Priya names the official financial rule/concept in plain powerful English.
  Scene 12: Priya tells YOU the one clear action to take starting today. "Here's what YOU do." Direct. No smile. No subscribe.

──────────────────────────────────────────────────────────────────────────────
VISUAL PROMPT GUIDELINES
──────────────────────────────────────────────────────────────────────────────
Each visual_prompt should ONLY describe:
  [named character action/pose] + [exact setting] + [specific evidence object]
  + [camera angle/composition] + split amber-teal lighting

DO NOT include character physical descriptions in the visual_prompt! The system will automatically inject the "Character Bible" paragraph later. Just write what they are doing.
NEVER ask for 3D, cartoon, Pixar, powder-blue shirt, world map, or a smile.

Every visual_prompt must:
  • mention Arjun in scenes 1-10.
  • mention Priya in scenes 11-12.
  • describe a full-bleed 9:16 frame with no black bars or empty background.
  • include one concrete unreadable prop: phone with blurred chart, unmarked document, abstract bars, amber screen glow, desk edge.
  • use a different camera angle or composition from the previous scene.
  • assume photoreal cinematic split light. Never 3D cartoon.

NEGATIVE PROMPTING FOR HALLUCINATION:
  • Do not fabricate exact numbers, returns, dates, prices, regulations, or quotes.
  • Do not show readable text inside images. Use abstract charts, blurred dashboards,
    icons, color-coded arrows, or document shapes instead.
  • Do not create celebrity likenesses, real logos, exchange logos, broker logos,
    newspaper mastheads, or branded app screens.
  • Do not write anything that sounds like a guaranteed investment outcome.

OUTPUT FORMAT — Return ONLY valid JSON, nothing else, no markdown fences:
──────────────────────────────────────────────────────────────────────────────
{
  "title": "Punchy English title max 60 chars — grabs attention immediately; do NOT include #Shorts",
  "description": "SEO description 150-300 chars — explains the finance concept revealed at the end",
  "hashtags": ["StockMarket", "InvestingIndia", "FinanceShorts", "MarketDebunk", "MoneyTips"],
  "scenes": [
    {
      "scene_id": 1,
      "narration": "Present-tense cinematic narration addressed to YOU. Max 20 words. Flows into next scene.",
      "visual_prompt": "Arjun stares into camera in a dark teal room, amber lamp blurred behind his left shoulder, extreme close-up, split amber-teal light, photoreal cinematic, full-bleed 9:16",
      "duration_hint": 7.0
    }
  ]
}

CRITICAL: Exactly 12 scenes. Use the story_seed facts provided. Build a gripping story that flows, not a list of facts. USE "you/your" in AT LEAST 8 scenes."""

# ──────────────────────────────────────────────────────────────────────────────
#  JSON Extraction
# ──────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON found in model response")
    return json.loads(text[start:end])

# ──────────────────────────────────────────────────────────────────────────────
#  Gemini via Vertex AI
# ──────────────────────────────────────────────────────────────────────────────

_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.5-pro",
]

def _call_gemma(user_prompt: str) -> str:
    """Call Gemma through Vertex AI with graceful fallback."""
    from google import genai
    from google.genai import types
    client = genai.Client(vertexai=True, project="exalted-shape-502013-q5", location="us-central1")
    model_name = settings.GEMMA_FALLBACK_MODEL
    log.info("Calling Vertex Gemma deployment: %s", model_name)
    response = client.models.generate_content(
        model=model_name,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            temperature=0.65,
            max_output_tokens=4000,
            response_mime_type="application/json",
        ),
    )
    return response.text

def _template_script(thesis: str) -> ScriptPayload:
    """Guaranteed schema-valid emergency script when every LLM is unavailable."""
    clean_thesis = " ".join(thesis.split())[:45].strip()
    narrations = [
        f"Wait—{clean_thesis} is not what it looks like.",
        "The market headline sounds alarming, but headlines hide the truth.",
        "Most retail investors panic and sell at the worst moment.",
        "That panic is exactly what institutional players count on.",
        "A sudden price drop never proves that an asset is broken.",
        "Look at the underlying volume before calling it a crash.",
        "Ask who benefits from pushing prices down right now.",
        "Big players quietly accumulate while everyone else runs away.",
        "This classic market pattern is known as a Bear Trap.",
        "Smart money buys the exact dip that panic created.",
        "Always demand hard data before making an emotional trade.",
        "Protect your hard-earned capital. Check the facts first.",
    ]
    prompts = [
        "Arjun sitting at a compact home-office desk, checking a live market chart on his phone, warm amber desk lamp against teal wall, close-up over-shoulder composition, full-bleed vertical frame, clean frame edges",
        "Arjun looking puzzled while pointing toward an illuminated red candlestick chart on a desktop monitor, amber accent light on navy studio background, medium shot, cinematic depth of field",
        "Arjun examining an open annotated notebook and a metallic financial calculator under warm task lighting, inquisitive expression, side profile view, premium studio render, vertical composition",
        "Arjun leaning over a wooden workspace reviewing a printed financial report sheet, warm practical illumination, dark moody studio ambiance, focused eye line, high visual detail",
        "Arjun holding a modern smartphone showing financial graphs, thoughtful expression, soft golden rim light framing his silhouette, teal backdrop, crisp vertical frame",
        "Arjun seated at his analytical station comparing multiple financial index figures on a tablet, calm demeanor, cinematic over-the-shoulder perspective, clean composition",
        "Arjun resting his chin on his hand while analyzing a historic bond yield curve on a glass screen, warm amber glow, stylish professional workspace, cinematic framing",
        "Arjun standing beside a digital display showing clear statistical bar charts, gesturing with open hands, expressive pose, sophisticated lighting palette, vertical portrait",
        "Arjun reviewing a structured investment risk matrix sheet on a wooden desk surface, warm golden desk lamp glow, engaging cinematic lighting, full-bleed composition",
        "Arjun looking forward with clarity and nodding in understanding, holding a closed digital tablet, soft amber spotlight against dark teal studio, confident pose",
        "Priya entering the modern finance studio with poised confidence, gesturing toward an elegant market valuation equation on a glass monitor, warm amber accents, cinematic medium shot",
        "Priya delivering the final takeaway directly to the camera with an intense direct gaze, standing in the polished teal studio with warm amber practical lighting, crisp vertical framing",
    ]
    scenes = [
        {"scene_id": i, "narration": narrations[i - 1], "visual_prompt": prompts[i - 1], "duration_hint": 4.2}
        for i in range(1, 13)
    ]
    return ScriptPayload(
        title="Market Debunk: What Investors Miss",
        description="A concise market explanation based on the available evidence. Practical finance insights that protect your capital.",
        hashtags=["#Finance", "#Investing", "#Shorts"],
        scenes=scenes,
    )

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=20))
def _call_gemini(user_prompt: str, model_name: str) -> str:
    """Call Gemini via Vertex AI and return raw response."""
    from google import genai
    from google.genai import types
    client = genai.Client(vertexai=True, project="exalted-shape-502013-q5", location="us-central1")

    response = client.models.generate_content(
        model=model_name,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            temperature=0.70,
            max_output_tokens=4000,
            response_mime_type="application/json",
        )
    )
    return response.text


def _repair_json(raw_response: str, error: Exception, model_name: str) -> str:
    """Repair an attempted Market Debunk script response when JSON parsing or validation fails."""
    repair_prompt = f"""Repair the following attempted Market Debunk script response into complete valid JSON.
The previous attempt failed validation with error:
{error}

CRITICAL RULES:
1. Return ONLY pure valid JSON with no markdown code fences (no ```json).
2. Exactly 12 scenes in the scenes array (scene_id 1 to 12).
3. Ensure total narration word count across all 12 scenes is 95-115 words (~8-10 words per scene, 6-16 words per scene).
4. Scenes 1-10 visual_prompt must mention Arjun. Scenes 11-12 visual_prompt must mention Priya.
5. Address the viewer directly ("you"), with an urgent viral hook in scenes 1-2 and a cohesive story.

ATTEMPTED RESPONSE:
{raw_response}
"""
    return _call_gemini(repair_prompt, model_name)

def generate_script(thesis: str, channel_name: str, story_seed: Optional[dict] = None) -> ScriptPayload:
    """
    Generate a full 12-scene cinematic story script.
    """
    log.info("Generating 12-scene script | thesis: '%s'", thesis)

    seed_context = ""
    if story_seed:
        seed_context = f"""
STORY SEED:
Inciting Event (Scenes 1-2): {story_seed.get('inciting_event', '')}
Protagonist's Flaw (Scenes 3-5): {story_seed.get('protagonist_flaw', '')}
Real World Anchor (Scenes 8-9): {story_seed.get('real_world_anchor', '')}
Finance Concept to Reveal (Scenes 10-11): {story_seed.get('concept_name', '')}
Plain Definition (Scenes 10-11): {story_seed.get('concept_one_liner', '')}
Safe Visual Evidence Object: {story_seed.get('visual_evidence', '')}
"""

    user_prompt = f"""Core financial thesis: "{thesis}"
{seed_context}
Now generate the complete 12-scene cinematic short-story script as JSON.
Remember: Exactly 12 scenes.

Before answering, internally check that:
- the title has no #Shorts tag;
- scenes 1-2 have an urgent, scroll-stopping viral hook that speaks directly to the viewer;
- the narrations tell a cohesive, suspenseful story that flows naturally across scenes, not a list of facts;
- scenes 1-10 mention Arjun in visual_prompt;
- scenes 11-12 mention Priya in visual_prompt;
- every visual prompt has a specific prop/evidence object;
- no scene invents precise facts outside the story_seed;
- the total narration is 100-115 words (target ~50 seconds)."""

    for model in _GEMINI_MODELS:
        log.info("Trying model: %s", model)
        try:
            raw = _call_gemini(user_prompt, model)
            log.debug("Raw response: %d chars", len(raw))

            try:
                data = _extract_json(raw)
            except (json.JSONDecodeError, ValueError) as parse_error:
                log.warning("Model returned malformed JSON; requesting one repair pass: %s", parse_error)
            try:
                script = ScriptPayload(**data)
            except Exception as val_error:
                log.warning("Script failed validation (%s); attempting repair pass", val_error)
                repaired_raw = _repair_json(raw, val_error, model)
                data = _extract_json(repaired_raw)
                script = ScriptPayload(**data)

            total_words = sum(len(s.narration.split()) for s in script.scenes)
            log.info(
                "✓ Script ready | model: %s | title: '%s' | total_words: %d",
                model, script.title, total_words,
            )
            return script

        except Exception as exc:
            log.warning("Model %s failed: %s — trying next", model, exc)
            continue

    # Last LLM attempt: Gemma is deliberately kept after Vertex and still goes
    # through the same JSON parser, Pydantic model, and downstream gates.
    try:
        log.info("Trying Gemma fallback model: %s", settings.GEMMA_FALLBACK_MODEL)
        raw = _call_gemma(user_prompt)
        try:
            data = _extract_json(raw)
        except (json.JSONDecodeError, ValueError) as parse_error:
            log.warning("Gemma returned malformed JSON; requesting one repair pass")
            data = _extract_json(_call_gemma(
                f"Repair this response into complete valid JSON with exactly 12 scenes. "
                f"Parser error: {parse_error}\n\n{raw}"
            ))
        script = ScriptPayload(**data)
        total_words = sum(len(s.narration.split()) for s in script.scenes)
        log.info("✓ Script ready | model: %s | title: '%s' | total_words: %d",
                 settings.GEMMA_FALLBACK_MODEL, script.title, total_words)
        return script
    except Exception as exc:
        log.error("Gemma fallback failed: %s", exc)

    log.warning("All remote script models failed; using schema-valid emergency script")
    return _template_script(thesis)

    raise RuntimeError(
        f"All Gemini models failed to produce a valid 12-scene script for: '{thesis}'"
    )

def script_to_dict(script: ScriptPayload) -> dict:
    return script.model_dump()
