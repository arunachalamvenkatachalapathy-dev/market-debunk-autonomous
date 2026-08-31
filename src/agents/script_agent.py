"""
src/agents/script_agent.py

Phase 2 — Script Generation (Gemma Heavy Weight via Google AI Studio)

STYLE: Derived from deep analysis of "City of Finance" YouTube Shorts
  - uo6HAxa_nnU: "Accidentally Generous Man" → Positive Externalities parable
  - hIYPnRJ1ouA: "Two Merchants, One Market" → Second-Mover Advantage story
  - OZRN4hczkKc: "Price of Escaping a Bad Service" → Exit Fee expose

NARRATIVE STRUCTURE (8 scenes):
  1. Hook: Relatable story/character/scenario (NOT a statistic)
  2. Deepen: Raise the stakes of the story
  3. Principle: Reveal the financial concept hidden in plain sight
  4. Application: How this plays out in Indian markets specifically
  5. Historical: Global or historical example that validates the thesis
  6. Debunk/Twist: What most people get wrong (THE moment of surprise)
  7. Implication: What this means for the viewer RIGHT NOW
  8. Closer: CTA + thought-provoking final line

API: Google AI Studio (GEMINI_SCRIPT_API_KEY)
Model: gemma-3-27b-it (heavyweight)
Fallback: gemma-3-12b-it
"""
from __future__ import annotations

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

class Scene(BaseModel):
    scene_id: int = Field(ge=1, le=8)
    narration: str = Field(min_length=10)
    visual_prompt: str = Field(min_length=5)
    duration_hint: float = Field(default=8.0, ge=3.0, le=20.0)

    @field_validator("narration")
    @classmethod
    def narration_clean(cls, v: str) -> str:
        return v.strip()


class ScriptPayload(BaseModel):
    title: str = Field(min_length=5, max_length=100)
    description: str = Field(min_length=20, max_length=5000)
    hashtags: list[str] = Field(min_length=5, max_length=15)
    scenes: list[Scene] = Field(min_length=8, max_length=8)

    @field_validator("scenes")
    @classmethod
    def exactly_eight(cls, v: list) -> list:
        if len(v) != 8:
            raise ValueError(f"Expected exactly 8 scenes, got {len(v)}")
        return v


# ──────────────────────────────────────────────────────────────────────────────
#  System Prompt (City of Finance style DNA baked in)
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an elite, award-winning screenwriter specializing in dramatic, story-driven financial documentaries. 

YOUR PRIME DIRECTIVE: ZERO ROBOTIC SCRIPTING. ABSOLUTELY NO LISTS. NO BULLET POINTS. NO DRY ACADEMIC TONE. 
Every script MUST be a cinematic story with characters, emotion, stakes, and narrative flow. 

WHAT MAKES THESE VIDEOS WORK:
- They NEVER open with "Did you know?" or "Today we will discuss..." 
- They always open with a relatable character in a high-stakes financial situation.
- The financial concept is revealed naturally through the character's experience.
- The language is emotional, dramatic, and deeply human. Tell a story!
- The DEBUNK is the climax of the story, shattering what the viewer previously believed.
- No Tamil, Hindi, or mixed language. Clean, dramatic English only.

YOUR 8-SCENE NARRATIVE ARC (follow this EXACTLY, but seamlessly like a movie):
  Scene 1 - The Hook: Introduce the protagonist (e.g., Ramesh) in the middle of a financial crisis or dilemma. Hook the viewer with empathy.
  Scene 2 - The Escalation: The situation gets worse or a shocking twist happens to the character.
  Scene 3 - The Principle: Explain the unseen economic force that caused the character's situation. Give it a name.
  Scene 4 - The Indian Reality: How this exact invisible force is manipulating everyday Indian investors right now.
  Scene 5 - The History: A quick flashback to a historical parallel showing this trap is older than time.
  Scene 6 - THE DEBUNK: The plot twist. What the character (and the viewer) thought was the safe choice was actually the trap.
  Scene 7 - The Lesson: The emotional resolution. How to escape the trap.
  Scene 8 - The Closer: A haunting, memorable final thought + Subscribe/Follow CTA.

NARRATION RULES:
- MUST SOUND LIKE A DRAMATIC STORY, NOT A LECTURE.
- Use real Indian names (Ramesh, Kavitha, Suresh) and build a world around them.
- Reference specific Indian context (Zerodha, Dalal Street, LIC, Nifty) organically within the story.
- Speak like a cinematic narrator in a high-budget thriller. Short, punchy, dramatic sentences.

VISUAL PROMPT RULES - THIS IS THE MOST CRITICAL SECTION:
Each visual_prompt must be a DETAILED, SPECIFIC, 60-100 word description. NOT a vague label.

The visual style is ALWAYS: dark charcoal backgrounds, rich amber/gold lamp lighting, Indian characters, oil painting texture, chiaroscuro shadows, cinematic 9:16.

STRUCTURE FOR EVERY VISUAL PROMPT:
[Specific scene action from narration], [exact Indian setting], [time of day], [lighting: single amber desk lamp or golden hour or dim tube light], [character body language showing emotion], [one key symbolic object reinforcing narration], [atmospheric detail: cigarette smoke or dust motes or rain on window or steam], dark charcoal and amber palette, oil painting texture, 9:16 vertical

EXAMPLE of a GOOD visual prompt:
Ramesh, Indian male 40s, dark hair, sitting alone at a cluttered wooden desk at 2am in a dim Mumbai office, single amber lamp casting dramatic shadows across a stack of unpaid loan papers to his right, both hands pressed to his forehead in despair, blurred city skyline visible through frosted glass behind him, dust motes floating in lamplight, dark charcoal and amber palette, oil painting texture, 9:16

OUTPUT FORMAT - Return ONLY valid JSON, nothing else, no markdown fences:
{
  "title": "Short punchy title story-first max 60 chars",
  "description": "SEO description 150-300 chars with core thesis",
  "hashtags": ["StockMarket", "IndianMarket", "EconomicsExplained", "MoneyTips", "NiftyBSE", "FinanceTamil", "InvestingIndia"],
  "scenes": [
    {
      "scene_id": 1,
      "narration": "Spoken words for this scene. Max 25 words. Short punchy sentences.",
      "visual_prompt": "Specific Pexels query OR AI image generation prompt for this scene",
      "duration_hint": 8.0
    }
  ]
}

CRITICAL: Exactly 8 scenes. Each narration max 25 words. Total script should read as one cohesive story."""


# ──────────────────────────────────────────────────────────────────────────────
#  JSON Extraction
# ──────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> dict:
    text = text.strip()
    # Strip markdown fences
    if "```" in text:
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
        text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
    # Find outermost JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON found in model response")
    return json.loads(text[start:end])


# ──────────────────────────────────────────────────────────────────────────────
#  Gemma via Google AI Studio
# ──────────────────────────────────────────────────────────────────────────────

# Available Gemini models on Vertex AI
_GEMMA_MODELS = [
    "gemini-2.5-flash",
]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=20))
def _call_gemma(thesis: str, channel_name: str, model_name: str) -> str:
    """Call Gemini via Vertex AI and return raw response."""
    from google import genai
    from google.genai import types
    client = genai.Client(vertexai=True, project="exalted-shape-502013-q5", location="us-central1")

    user_prompt = f"""Channel context: {channel_name} (Indian Tamil finance YouTube channel)
Core financial thesis to script: "{thesis}"

Now generate the complete 8-scene YouTube Short script JSON."""

    response = client.models.generate_content(
        model=model_name,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            temperature=0.8,
            max_output_tokens=4000,
            response_mime_type="application/json",
        )
    )
    return response.text


def generate_script(thesis: str, channel_name: str) -> ScriptPayload:
    """
    Generate a full 8-scene script for the given thesis.
    Uses Gemma 27B (heavyweight) via Google AI Studio.
    Falls back to smaller Gemma models on failure.

    Returns a validated ScriptPayload object.
    """
    log.info("Generating script | thesis: '%s' | channel: %s", thesis, channel_name)

    for model in _GEMMA_MODELS:
        log.info("Trying Gemma model: %s", model)
        try:
            raw = _call_gemma(thesis, channel_name, model)
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
        f"All Gemma models failed to produce a valid 8-scene script for: '{thesis}'"
    )


def script_to_dict(script: ScriptPayload) -> dict:
    return script.model_dump()
