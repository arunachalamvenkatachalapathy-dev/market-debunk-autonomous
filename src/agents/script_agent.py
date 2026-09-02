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
        if not 9 <= word_count <= 24:
            raise ValueError(f"Each scene narration must be 9-24 words; got {word_count}.")
        banned = ["as an ai", "not financial advice", "subscribe now"]
        if any(term in cleaned.lower() for term in banned):
            raise ValueError("Narration contains banned generic/disclaimer language.")
        return cleaned

    @field_validator("visual_prompt")
    @classmethod
    def validate_visual_prompt(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        word_count = len(cleaned.split())
        if word_count < 18:
            raise ValueError(f"Visual prompt is too thin for a premium scene; got {word_count} words.")
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
        if any(term in cleaned.lower() for term in banned):
            raise ValueError("Visual prompt contains banned visual direction.")
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
        if not 140 <= total_words <= 240:
            raise ValueError(
                f"Script must contain 100-145 narration words for a 40-59s Short; got {total_words}."
            )
        visual_prompts = [scene.visual_prompt.lower() for scene in self.scenes]
        if len(set(visual_prompts)) != len(visual_prompts):
            raise ValueError("Every scene must have a unique visual prompt.")
        return self


# ──────────────────────────────────────────────────────────────────────────────
#  System Prompt — 12-Scene Cinematic Format
# ──────────────────────────────────────────────────────────────────────────────
  
_SYSTEM_PROMPT = """You are the full prompt-engineering room for "Market Debunk": finance researcher,
retention strategist, short-form scriptwriter, visual director, and YouTube metadata editor.
You generate one premium English finance YouTube Short as strict JSON.
  
CHANNEL TONE: Sophisticated, engaging, cinematic. NOT preachy, NOT robotic, NOT a lecture.
Think: Netflix India meets Bloomberg. Premium, visual, story-driven.

CORE JOB:
  1. Convert the story_seed into a viewer-retention story.
  2. Use only facts from the thesis/story_seed. Do not invent company names, dates, prices,
     laws, returns, or statistics unless they appear in the seed.
  3. When the seed lacks a precise number, use qualitative language such as "quietly",
     "often", "many investors", or "the hidden cost".
  4. Make every scene visually different enough that a viewer feels forward motion.

──────────────────────────────────────────────────────────────────────────────
THE HOST & RECURRING CHARACTERS
──────────────────────────────────────────────────────────────────────────────
ARJUN (The Host):
  • A confident Indian man in his early-to-mid 30s.
  • He is the anchor of the channel. He appears in almost every scene and drives the narrative.

PRIYA (The Truth-Teller):
  • Mid-30s Indian woman, calm, professional.
  • She MUST appear in Scenes 11 and 12 to deliver the final reveal and CTA. She is the closer.

NARRATION STYLE (CRITICAL FOR AUDIO):
  • You are telling a story, not reading a textbook.
  • Write for the ear, not the eye — use contractions, sentence fragments, and varied sentence length.
  • Avoid three sentences of the same length and rhythm in a row.
  • Keep it punchy, conversational, and direct. Break up complex ideas into short beats.
  • Write 100-145 narration words across all 12 scenes (target 125-140 for a 40-56 second Short). This is non-negotiable.
  • Each scene narration must be 9-24 words.
  • No generic disclaimers, no "not financial advice", no motivational filler.

──────────────────────────────────────────────────────────────────────────────
THE 12-SCENE STORY ARC (Exactly 12 Scenes. 60-90 seconds total runtime):
──────────────────────────────────────────────────────────────────────────────

Scenes 1-2 — THE HOOK (Arjun's inciting moment):
  Arjun is the center. He is doing something specific and relatable (e.g., checking a portfolio, staring at a laptop).
  Write narration in present tense, like a film narrator. DO NOT start with a statistic or question.
  Visuals: Arjun must be visible. Deep teal-navy background with warm amber practical lighting.

Scenes 3-5 — THE MYTH / THE FLAW:
  The common mistake most people make, which Arjun is experiencing. 
  Explain the psychological or strategic error over a few beats.

Scenes 6-7 — THE FRUSTRATION:
  Arjun realizes the math isn't adding up. The emotional low point of the story.

Scenes 8-9 — THE EVIDENCE / REAL WORLD ANCHOR:
  Introduce the actual market fact, law, or historical trend.
  Visuals: Arjun reviewing data, charts, or an abstract representation.

Scenes 10-11 — THE REVEAL (The Financial Concept):
  The twist. Reveal the official finance term and explain it in plain English.
  Visuals: Priya enters the scene and explains the concept to Arjun. (Name Priya in the prompt).

Scene 12 — THE CALL TO ACTION (CTA):
  The closing beat. What should the viewer do differently?
  Visuals: Priya delivering the final takeaway with confidence, looking directly at camera.

──────────────────────────────────────────────────────────────────────────────
VISUAL PROMPT GUIDELINES
──────────────────────────────────────────────────────────────────────────────
Each visual_prompt should ONLY describe:
  [named character action/pose] + [exact setting] + [specific evidence object]
  + [lighting mood/amber accents on teal background] + [camera angle/composition]
  
DO NOT include character physical descriptions in the visual_prompt! The system will automatically inject the "Character Bible" paragraph later. Just write what they are doing.

Every visual_prompt must:
  • mention Arjun in scenes 1-10.
  • mention Priya in scenes 11-12.
  • describe a full-bleed 9:16 frame with no black bars or empty background.
  • include one concrete prop or evidence object: phone app, portfolio chart, invoice,
    contract page, news clipping, calculator, dashboard, exchange board, or marked notebook.
  • use a different camera angle or composition from the previous scene.

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
      "narration": "Present-tense cinematic narration. Max 20 words. Flows into next scene.",
      "visual_prompt": "Arjun sits at a compact home-office desk, checking a blurred red portfolio chart on his phone, amber desk lamp against teal wall, close-up over-shoulder composition, full-bleed vertical frame",
      "duration_hint": 7.0
    }
  ]
}

CRITICAL: Exactly 12 scenes. Use the story_seed facts provided. Arjun must appear by name in narrations."""

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
]

def _call_gemma(user_prompt: str) -> str:
    """Call Gemma through Google AI Studio as the last structured-output fallback."""
    api_key = settings.GEMINI_SCRIPT_API_KEY or settings.GEMINI_API_KEY
    if not api_key:
        raise RuntimeError("GEMINI_SCRIPT_API_KEY or GEMINI_API_KEY is not configured for Gemma fallback")
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    model_name = settings.GEMMA_FALLBACK_MODEL
    # Model availability differs between AI Studio API versions and keys.
    # Resolve an actually callable Gemma model instead of trusting one name.
    try:
        available = list(client.models.list())
        candidates = [model_name, "gemma-3-27b", "gemma-3-12b-it", "gemma-3-4b-it", "gemma-2-27b-it"]
        for candidate in candidates:
            for model in available:
                name = getattr(model, "name", "")
                methods = getattr(model, "supported_actions", []) or getattr(model, "supported_methods", [])
                if name.endswith(candidate) and (not methods or "generateContent" in methods):
                    model_name = name.removeprefix("models/")
                    break
            else:
                continue
            break
    except Exception as exc:
        log.warning("Could not list Gemma models; trying configured name: %s", exc)
    log.info("Resolved Gemma model: %s", model_name)
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
    narrations = [
        f"Wait—{thesis[:90]} deserves a closer look before investors react.",
        "The headline sounds alarming, but headlines are not the whole market.",
        "Start by separating confirmed evidence from predictions and market speculation.",
        "Then ask what changed, and who benefits from this situation today.",
        "That simple question exposes the mistake many investors make under pressure.",
        "A lower price alone cannot prove that something is genuinely undervalued.",
        "Look for the business reason behind the move before calling it opportunity.",
        "Next, identify the risk that could invalidate the popular investment story.",
        "The key idea is always risk compared with realistic potential reward.",
        "Use a clear plan, check the facts, and avoid emotional predictions.",
        "Markets change quickly, so review the evidence before taking action.",
        "Subscribe for the next practical Market Debunk finance explanation.",
    ]
    scenes = []
    for i, narration in enumerate(narrations, 1):
        character = "Arjun" if i <= 10 else "Priya"
        scenes.append({"scene_id": i, "narration": narration,
                       "visual_prompt": f"{character} in a teal finance studio examining a clear market chart and notebook, cinematic vertical composition",
                       "duration_hint": 4.0})
    return ScriptPayload(title="Market Debunk: What Investors Miss", description="A concise market explanation based on the available evidence. Subscribe for more practical finance insights.", hashtags=["#Finance", "#Investing", "#Shorts"], scenes=scenes)

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
            temperature=0.85,
            max_output_tokens=4000,
            response_mime_type="application/json",
        )
    )
    return response.text


def _repair_json(raw_response: str, error: Exception, model_name: str) -> str:
    """Spend one small repair call only when a valid-content response has malformed JSON."""
    repair_prompt = f"""Repair the following attempted Market Debunk script response.
Return ONLY complete valid JSON. Keep the original meaning and all 12 scenes.
Do not add markdown fences or commentary. The parser error was: {error}

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
- scenes 1-10 mention Arjun in visual_prompt;
- scenes 11-12 mention Priya in visual_prompt;
- every visual prompt has a specific prop/evidence object;
- no scene invents precise facts outside the story_seed;
- the total narration is 100-145 words (target 125-140 words, about 40-56 seconds)."""

    for model in _GEMINI_MODELS:
        log.info("Trying model: %s", model)
        try:
            raw = _call_gemini(user_prompt, model)
            log.debug("Raw response: %d chars", len(raw))

            try:
                data = _extract_json(raw)
            except (json.JSONDecodeError, ValueError) as parse_error:
                log.warning("Model returned malformed JSON; requesting one repair pass: %s", parse_error)
                data = _extract_json(_repair_json(raw, parse_error, model))
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
