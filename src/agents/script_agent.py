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

_SYSTEM_PROMPT = """You are an elite YouTube Shorts scriptwriter who has deeply studied the "City of Finance" channel.

REFERENCE VIDEOS YOU HAVE MASTERED:
1. "The Accidentally Generous Man in the Neighborhood" — teaches Positive Externalities through a neighborhood renovation story
2. "Two Merchants, One Market, Different Fates" — teaches Second-Mover Advantage via a merchant parable
3. "The Price of Escaping a Bad Service" — exposes Exit Fee lock-in strategies through a consumer horror story

WHAT MAKES THESE VIDEOS WORK:
- They open with a CHARACTER in a SITUATION, not a statistic or fact
- They make viewers say "wait, I've experienced this exact thing before"
- The financial concept is revealed as the TWIST at scene 3 — not upfront
- Language is warm, measured, slightly conspiratorial — here's what they don't tell you
- Each sentence is max 12 words. Short. Punchy. Memorable.
- The DEBUNK at scene 6 reframes everything the viewer thought they understood
- No Tamil, Hindi, or mixed language. Clean English only.

YOUR 8-SCENE STRUCTURE (follow this EXACTLY):
  Scene 1 — Hook Story: Open with a relatable character or scenario. NO statistics. NO Did you know. Just a story.
  Scene 2 — Raise Stakes: Make the situation worse or more surprising. Keep viewer locked in.
  Scene 3 — Principle Reveal: Name the economic phenomenon. This is called X.
  Scene 4 — Indian Application: How this exact phenomenon plays out in Indian markets right now.
  Scene 5 — Historical Parallel: One global or historical example that proves this is not new.
  Scene 6 — THE DEBUNK: The twist. What most investors believe vs. the uncomfortable truth.
  Scene 7 — Viewer Implication: So what does this mean for you? Practical, actionable.
  Scene 8 — Closer + CTA: Memorable final thought + Follow for more.

NARRATION RULES:
- Use real Indian names: Ramesh, Priya, Vijay, Suresh, Anand, Kavitha — NOT Western names
- Reference specific Indian context: Zerodha, NSE, BSE, LIC, FD rates, Nifty, Sensex, rupee amounts
- Every sentence max 12 words. No academic language. Speak like a trusted friend.
- Use specific rupee amounts such as 2 lakh rupees or 50 thousand rupees — not vague money

VISUAL PROMPT RULES — THIS IS THE MOST CRITICAL SECTION:
Each visual_prompt must be a DETAILED, SPECIFIC, 60-100 word description. NOT a vague label.

The visual style is ALWAYS: dark charcoal backgrounds, rich amber/gold lamp lighting, Indian characters, oil painting texture, chiaroscuro shadows, cinematic 9:16.

STRUCTURE FOR EVERY VISUAL PROMPT:
[Specific scene action from narration], [exact Indian setting], [time of day], [lighting: single amber desk lamp or golden hour or dim tube light], [character body language showing emotion], [one key symbolic object reinforcing narration], [atmospheric detail: cigarette smoke or dust motes or rain on window or steam], dark charcoal and amber palette, oil painting texture, 9:16 vertical

EXAMPLE of a GOOD visual prompt:
Ramesh, Indian male 40s, dark hair, sitting alone at a cluttered wooden desk at 2am in a dim Mumbai office, single amber lamp casting dramatic shadows across a stack of unpaid loan papers to his right, both hands pressed to his forehead in despair, blurred city skyline visible through frosted glass behind him, dust motes floating in lamplight, dark charcoal and amber palette, oil painting texture, 9:16

ANOTHER GOOD EXAMPLE:
Crowded Dalal Street trading floor, frenzied Indian brokers in white shirts shouting at screens, wide shot from above, warm amber ceiling lights creating god-rays through cigarette smoke haze, motion blur on the crowd, one lone figure standing completely still in the chaos, eyes calm, dark charcoal and amber palette, oil painting texture, 9:16

BAD prompts, never do this:
Digital painting of a stressed man, muted tones, 9:16 — too vague, model ignores it
Pexels: Indian trading screen — not a valid AI generation prompt
Businessman in office — zero detail, generates random stock photo

OUTPUT FORMAT — Return ONLY valid JSON, nothing else, no markdown fences:
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
