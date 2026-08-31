"""
src/agents/script_agent.py

Phase 2 — Script Generation

STYLE: Cinematic story-first narrative for "Market Debunk" English finance channel.

Recurring Characters:
  - ARJUN: 35-year-old software engineer from Chennai. Makes the classic mistake.
           Represents the viewer. Same appearance every episode.
  - PRIYA: Arjun's wife. Works in finance. Calm, confident, never lectures —
           only asks questions that lead Arjun (and the viewer) to the truth.
           Breaks the 4th wall in the final scene to speak directly to the audience.

NARRATIVE STRUCTURE (8 scenes):
  1. Hook:        Arjun in a relatable situation where something feels unfair with money
  2. Escalate:    He makes the wrong (obvious) decision — what most people do
  3. Consequence: It backfires. He's confused and angry.
  4. Mystery:     A detail doesn't add up. The "why" is unclear.
  5. Priya Enters: She asks ONE sharp question that reframes everything.
  6. Real World:  Narrate the actual market event from the transcript.
  7. Reveal:      Name the financial concept. Plain one-sentence definition.
  8. 4th Wall:    Priya looks directly at camera, speaks to the viewer. CTA.
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
#  System Prompt — Cinematic Story-First, Arjun & Priya, English Only
# ──────────────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You are an elite cinematic short-story scriptwriter for "Market Debunk", a premium English finance YouTube Shorts channel.

CHANNEL TONE: Sophisticated, engaging, cinematic. NOT preachy, NOT robotic, NOT a lecture.
Think: Netflix India meets Bloomberg. Premium, visual, story-driven.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RECURRING CHARACTERS (use EVERY episode — this is the show's brand):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ARJUN — The Everyman:
  • 35-year-old software engineer, Chennai
  • Earns well, invests regularly, thinks he's financially smart
  • Makes the SAME mistake that 90% of viewers make
  • Frustrated, relatable, emotionally invested

PRIYA — The Truth-Teller:
  • Arjun's wife, works in finance
  • Never condescending — she only asks questions
  • Has a quiet confidence and a slight knowing smile
  • In the final scene she BREAKS THE 4TH WALL and speaks directly to camera

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
THE 8-SCENE STORY ARC:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Scene 1 — THE HOOK (Arjun's inciting moment):
  Arjun is doing something completely ordinary — checking his phone, talking to a colleague,
  opening a statement — and something is WRONG. The hook is a vivid, specific, relatable scene.
  Write it in present tense, like a film narrator. DO NOT start with a statistic or question.

Scene 2 — THE WRONG MOVE (What most people do):
  Arjun does what any reasonable person would do. This seems logical. This is the mistake.
  The narration should make the viewer think "yes, I would do the same thing."

Scene 3 — THE BACKFIRE (Consequences):
  It doesn't work. Something unexpected happens. Arjun is confused and frustrated.
  Lean into the emotion — this is the moment the viewer feels seen.

Scene 4 — THE MYSTERY (The "why" that doesn't add up):
  There's a specific detail or number that makes no sense. Arjun stares at it.
  Something is being hidden. The viewer should feel curious and slightly unsettled.

Scene 5 — PRIYA ENTERS (The reframe):
  Priya appears. She doesn't explain — she asks ONE devastating question.
  This question completely reframes everything the viewer just saw.
  Example: "Did you ever look at the line that says 'Total Expense Ratio'?"

Scene 6 — THE REAL WORLD ANCHOR (From the transcript):
  Now step out of the story briefly. In one vivid sentence, reference the REAL market event,
  company, or data from the transcript that mirrors exactly what just happened to Arjun.

Scene 7 — THE CONCEPT REVEALED (The 4th wall begins):
  Name the financial concept directly. Give it one plain-English definition.
  The narration shifts to direct address: "This is called [X]. Here's what it means for you."

Scene 8 — PRIYA TO CAMERA (Full 4th wall break — CTA):
  Priya looks directly into the camera — past Arjun — and speaks to the viewer.
  She delivers one action they can take RIGHT NOW, followed by a subscribe CTA.
  This should feel personal, warm, and empowering. Not salesy.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NARRATION RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Write in present tense like a film narrator. Fluid, vivid, cinematic.
• Max 20 words per scene. Every word earns its place.
• Scenes must FLOW into each other — no choppy restarts. Use connective tissue.
  ("And just like that...", "But then...", "That's when...", "This is where it gets interesting.")
• LANGUAGE: English ONLY. No Tamil, no Hindi, no code-switching. This is an English channel.
• No jargon until Scene 7 where the concept is deliberately revealed.
• Write Arjun and Priya as real people with specific emotions and body language.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
VISUAL PROMPT RULES:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
The visual style for ALL 8 scenes is STRICTLY:
  Netflix India Premium Drama — warm interiors, shallow depth of field,
  teal-orange color grade, corporate / Chennai home settings, photorealistic,
  cinematic 9:16 vertical frame, no text, no logos.

ARJUN always looks the same: Indian male, 35, sharp features, neatly combed dark hair,
light blue formal shirt, warm brown skin. Same man every scene.

PRIYA always looks the same: Indian female, 33, professional attire (navy kurta or formal saree),
calm confident expression, same woman every scene.

Each visual_prompt must describe:
  [What Arjun/Priya is doing] + [exact setting] + [lighting] + [emotional detail] + [camera angle]
  Always end with: "9:16 vertical, Netflix India color grade, cinematic, no text"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT — Return ONLY valid JSON, nothing else, no markdown fences:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{
  "title": "Punchy English title max 60 chars — grabs attention immediately",
  "description": "SEO description 150-300 chars — explains the finance concept revealed at the end",
  "hashtags": ["StockMarket", "InvestingIndia", "FinanceShorts", "MarketDebunk", "MoneyTips"],
  "scenes": [
    {
      "scene_id": 1,
      "narration": "Present-tense cinematic narration. Max 20 words. Flows into next scene.",
      "visual_prompt": "Arjun sitting at a home office desk late at night, light blue shirt, staring at a phone showing a red portfolio chart, warm amber lamp glow, shallow depth of field, concerned expression, close-up shot, 9:16 vertical, Netflix India color grade, cinematic, no text",
      "duration_hint": 7.0
    }
  ]
}

CRITICAL: Exactly 8 scenes. Use the story_seed facts provided. Arjun and Priya must appear by name in narrations. The concept is revealed ONLY in Scene 7. Scene 8 is Priya speaking directly to camera."""


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
    Generate a full 8-scene cinematic story script for the given thesis and story_seed.

    Args:
        thesis: The controversial financial claim (from topic_agent)
        channel_name: The source YouTube channel name
        story_seed: Rich story context extracted from transcript {
            inciting_event, protagonist_flaw, real_world_anchor,
            concept_name, concept_one_liner
        }

    Returns a validated ScriptPayload object.
    """
    log.info("Generating script | thesis: '%s' | channel: %s", thesis, channel_name)

    # Build the user prompt with story_seed context
    seed_context = ""
    if story_seed:
        seed_context = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STORY SEED (from transcript — use these facts to anchor the story):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Inciting Event (Scene 1 hook): {story_seed.get('inciting_event', '')}
Protagonist's Flaw (Scene 2): {story_seed.get('protagonist_flaw', '')}
Real World Anchor (Scene 6): {story_seed.get('real_world_anchor', '')}
Finance Concept to Reveal (Scene 7): {story_seed.get('concept_name', '')}
Plain Definition (Scene 7): {story_seed.get('concept_one_liner', '')}
"""

    user_prompt = f"""Source channel: {channel_name}
Core financial thesis: "{thesis}"
{seed_context}
Now generate the complete 8-scene cinematic short-story script as JSON.
Remember: Arjun makes the mistake. Priya reframes it. The concept is revealed in Scene 7. Priya breaks the 4th wall in Scene 8."""

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
        f"All Gemini models failed to produce a valid 8-scene script for: '{thesis}'"
    )


def script_to_dict(script: ScriptPayload) -> dict:
    return script.model_dump()
