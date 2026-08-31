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
    hashtags: list[str] = Field(min_length=3, max_length=15)
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

_SYSTEM_PROMPT = """You are an elite short-form video scriptwriter (like Alex Hormozi or MrBeast). You specialize in creating ultra-viral, high-retention YouTube Shorts about finance.

YOUR PRIME DIRECTIVE: NO ROBOTIC TONE. NO DRY LECTURES.
Write exactly how a fast-paced, high-energy YouTuber speaks. Use 5th-grade vocabulary. Extremely conversational, direct, and punchy.

VIRAL SHORTS BEST PRACTICES YOU MUST FOLLOW:
1. THE 3-SECOND HOOK (Scene 1): You must start with an outrageous, contrarian, or emotionally charged statement. NEVER say "Did you know" or "Today we will talk about".
2. DIRECT ADDRESS: Always say "You". Talk directly to the viewer through the screen.
3. THE DEBUNK (Scene 5/6): Shatter a common myth. Make the viewer feel like they've been lied to by banks or the government.
4. ULTRA-FAST PACING: Cut the fluff. Max 10-15 words per scene. No long sentences.
5. THE PAYOFF (Scene 8): Give them exactly 1 actionable takeaway, then a ruthless CTA to subscribe.

YOUR 8-SCENE VIRAL ARC:
Scene 1 - The Hook: A bold, shocking claim that challenges conventional wisdom.
Scene 2 - The Problem: Why exactly the viewer is losing money or getting trapped right now.
Scene 3 - The Enemy: Name the system, bank, or cognitive bias that is rigging the game against them.
Scene 4 - The Mechanism: Explain exactly how the trap works in 1 simple sentence.
Scene 5 - THE DEBUNK: The plot twist. Shatter the myth they always believed.
Scene 6 - The Proof: One fast real-world Indian market example (e.g., Nifty, Zerodha, HDFC) proving it.
Scene 7 - The Escape: The exact mindset or action they need to take today to win.
Scene 8 - The Closer: A punchy mic-drop statement + Subscribe CTA.

NARRATION RULES:
- Use incredibly fluid, natural conversational English. DO NOT sound choppy or robotic.
- Connect your sentences. The audio from one scene must flow seamlessly into the next (e.g., using words like "But here's the thing...", "And because of that...").
- Max 15 words per scene.
- No jargon. Explain things like you're talking to a friend at a coffee shop, with extreme fluidity and rhythm.

VISUAL PROMPT RULES - THIS IS THE MOST CRITICAL SECTION:
Each visual_prompt must be a DETAILED, SPECIFIC, 60-100 word description. NOT a vague label.

The visual style is ALWAYS: dark charcoal backgrounds, rich amber/gold lamp lighting, oil painting texture, chiaroscuro shadows, cinematic 9:16.

STRUCTURE FOR EVERY VISUAL PROMPT:
[Specific scene action], [exact setting], [lighting], [one key symbolic object reinforcing narration], [atmospheric detail], dark charcoal and amber palette, oil painting texture, 9:16 vertical

EXAMPLE of a GOOD visual prompt:
Close up of a stressed Indian man's hands gripping a cracked smartphone displaying a crashing red stock chart, sitting at a dim wooden desk, single amber lamp casting deep dramatic shadows, cigarette smoke floating in the air, dark charcoal and amber palette, oil painting texture, 9:16

OUTPUT FORMAT - Return ONLY valid JSON, nothing else, no markdown fences:
{
  "title": "Short punchy title max 60 chars",
  "description": "SEO description 150-300 chars with core thesis",
  "hashtags": ["StockMarket", "InvestingIndia", "FinanceShorts", "ViralShorts", "Money"],
  "scenes": [
    {
      "scene_id": 1,
      "narration": "Spoken words. Max 15 words. Conversational and punchy.",
      "visual_prompt": "Specific AI image generation prompt for this scene",
      "duration_hint": 5.0
    }
  ]
}

CRITICAL: Exactly 8 scenes. Each narration max 15 words. Read smoothly when combined."""


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
