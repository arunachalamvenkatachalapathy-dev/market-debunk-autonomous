import json
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from tenacity import retry, stop_after_attempt, wait_exponential

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="script_generation")

# ──────────────────────────────────────────────────────────────────────────────
#  Pydantic Schema
# ──────────────────────────────────────────────────────────────────────────────

class ScenePayload(BaseModel):
    scene_id: int
    narration: str = Field(description="The voiceover text for this scene. Present tense cinematic.")
    visual_prompt: str = Field(description="Action/pose/lighting description for the image generator.")
    duration_hint: float = Field(default=5.0)

class ScriptPayload(BaseModel):
    title: str = Field(description="Max 60 chars. The YouTube Short title.")
    description: str = Field(description="150-300 chars. SEO description.")
    hashtags: list[str] = Field(description="List of 3-5 hashtags.")
    scenes: list[ScenePayload]

    @field_validator("scenes")
    @classmethod
    def check_12_scenes(cls, v):
        if len(v) != 12:
            raise ValueError(f"Script must have exactly 12 scenes, got {len(v)}")
        return v


# ──────────────────────────────────────────────────────────────────────────────
#  System Prompt — 12-Scene Cinematic Format
# ──────────────────────────────────────────────────────────────────────────────
  
_SYSTEM_PROMPT = """You are an elite cinematic short-story scriptwriter for "Market Debunk", a premium English 
finance YouTube Shorts channel.
  
CHANNEL TONE: Sophisticated, engaging, cinematic. NOT preachy, NOT robotic, NOT a lecture.
Think: Netflix India meets Bloomberg. Premium, visual, story-driven.

──────────────────────────────────────────────────────────────────────────────
THE HOST & RECURRING CHARACTERS
──────────────────────────────────────────────────────────────────────────────
ARJUN (The Host):
  • A confident Indian man in his early-to-mid 30s.
  • He is the anchor of the channel. He appears in almost every scene and drives the narrative.

PRIYA (Optional Secondary Character):
  • Mid-30s Indian woman.
  • Use sparingly, only in the final scenes (11-12) if needed. She is NOT the host.

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
  Visuals: Arjun having a "lightbulb" moment or looking directly at the camera.

Scene 12 — THE CALL TO ACTION (CTA):
  The closing beat. What should the viewer do differently?
  Visuals: Arjun (or Priya) delivering the final takeaway with confidence.

──────────────────────────────────────────────────────────────────────────────
VISUAL PROMPT GUIDELINES
──────────────────────────────────────────────────────────────────────────────
Each visual_prompt should ONLY describe:
  [What character is doing/pose] + [exact setting] + [lighting mood/amber accents on teal background] + [camera angle]
  
DO NOT include character physical descriptions in the visual_prompt! The system will automatically inject the "Character Bible" paragraph later. Just write what they are doing.

OUTPUT FORMAT — Return ONLY valid JSON, nothing else, no markdown fences:
──────────────────────────────────────────────────────────────────────────────
{
  "title": "Punchy English title max 60 chars — grabs attention immediately",
  "description": "SEO description 150-300 chars — explains the finance concept revealed at the end",
  "hashtags": ["StockMarket", "InvestingIndia", "FinanceShorts", "MarketDebunk", "MoneyTips"],
  "scenes": [
    {
      "scene_id": 1,
      "narration": "Present-tense cinematic narration. Max 20 words. Flows into next scene.",
      "visual_prompt": "Arjun sitting at a home office desk late at night, light blue shirt, staring at a phone showing a red portfolio chart, warm amber lamp glow, shallow depth of field, concerned expression, close-up shot",
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
"""

    user_prompt = f"""Core financial thesis: "{thesis}"
{seed_context}
Now generate the complete 12-scene cinematic short-story script as JSON.
Remember: Exactly 12 scenes."""

    for model in _GEMINI_MODELS:
        log.info("Trying model: %s", model)
        try:
            raw = _call_gemini(user_prompt, model)
            log.debug("Raw response: %d chars", len(raw))

            data = _extract_json(raw)
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

    raise RuntimeError(
        f"All Gemini models failed to produce a valid 12-scene script for: '{thesis}'"
    )

def script_to_dict(script: ScriptPayload) -> dict:
    return script.model_dump()
