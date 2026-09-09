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
    broll_keyword: str = Field(default="", description="2-3 English words for vertical stock footage search (e.g. 'credit card payment', 'stock market crash', 'counting money').")
    duration_hint: float = Field(default=5.0)

    @field_validator("narration")
    @classmethod
    def validate_narration(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        word_count = len(cleaned.split())
        if not 4 <= word_count <= 26:
            raise ValueError(f"Each scene narration must be 4-26 words; got {word_count}.")
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
    def check_scenes(cls, v):
        if not (5 <= len(v) <= 7):
            raise ValueError(f"Script must have exactly 6 scenes (Fast-Hook format), got {len(v)}")
        scene_ids = [scene.scene_id for scene in v]
        expected_ids = list(range(1, len(v) + 1))
        if scene_ids != expected_ids:
            raise ValueError(f"Scene IDs must be exactly 1 through {len(v)} in order; got {scene_ids}.")
        for scene in v[1:-1]:
            if "priya" in scene.visual_prompt.lower():
                raise ValueError(f"Scene {scene.scene_id} mentions Priya. Priya is removed; use contextual B-roll objects.")
        return v

    @model_validator(mode="after")
    def enforce_spoken_comment_cta(self):
        """
        Guarantees that final scene voiceover explicitly speaks the comment CTA aloud.
        Ensures Google TTS voices 'Comment GUIDE below' or save/share trigger and subtitles display it.
        """
        last_scene = self.scenes[-1]
        narration = last_scene.narration.strip()
        has_cta = any(
            phrase in narration.lower()
            for phrase in ["comment 'guide'", "comment guide", "comment below", "save this", "share this", "share with"]
        )
        if not has_cta:
            cta_phrase = "Share with a friend and comment 'GUIDE' below."
            sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", narration) if s.strip()]
            if len(sentences) > 1 and len(narration.split()) > 8:
                last_scene.narration = f"{sentences[0]} {cta_phrase}"
            else:
                last_scene.narration = f"{narration.rstrip('.')} — {cta_phrase}"
            log.info("✓ Auto-enforced spoken CTA in final scene narration: '%s'", last_scene.narration)
        return self

    @model_validator(mode="after")
    def check_narration_pacing(self):
        total_words = sum(len(scene.narration.split()) for scene in self.scenes)
        # Fast-Hook Short (< 30s): 55-75 words ideal for 6-scene format.
        if total_words > 90:
            diff = total_words - 80
            for s in reversed(self.scenes[:-1]):
                words = s.narration.split()
                if len(words) > 10 and diff > 0:
                    trim = min(len(words) - 9, diff)
                    s.narration = " ".join(words[:-trim]).rstrip(" ,;:") + "."
                    diff -= trim
            total_words = sum(len(scene.narration.split()) for scene in self.scenes)

        if not 45 <= total_words <= 95:
            raise ValueError(
                f"Script must contain 45-95 narration words for 6-scene Fast-Hook Short (~24s); got {total_words}."
            )
        visual_prompts = [scene.visual_prompt.lower() for scene in self.scenes]
        if len(set(visual_prompts)) != len(visual_prompts):
            raise ValueError("Every scene must have a unique visual prompt.")
        return self

    @model_validator(mode="after")
    def check_second_person_voice(self):
        """Require 'you' or 'your' to maintain conversational viewer-direct focus."""
        min_required = max(2, int(len(self.scenes) * 0.4))
        second_person_scenes = sum(
            1 for scene in self.scenes
            if "you" in scene.narration.lower() or "your" in scene.narration.lower()
        )
        if second_person_scenes < min_required:
            # Auto-correct by injecting conversational direct-address prefix into middle scenes
            for scene in self.scenes[1:]:
                narr = scene.narration.strip()
                if "you" not in narr.lower() and "your" not in narr.lower():
                    words = narr.split()
                    if len(words) <= 18:
                        first_lower = words[0][0].lower() + words[0][1:] if words else ""
                        rest = " ".join(words[1:])
                        scene.narration = f"What you didn't see: {first_lower} {rest}".strip()
                        second_person_scenes += 1
                        if second_person_scenes >= min_required:
                            break

        if second_person_scenes < min_required:
            raise ValueError(
                f"Script must use 'you'/'your' in at least {min_required} scenes to sound personal and urgent; "
                f"only {second_person_scenes} scenes contain it. Rewrite to address the viewer directly."
            )
        return self


# ──────────────────────────────────────────────────────────────────────────────
#  System Prompt — 12-Scene Cinematic Format
# ──────────────────────────────────────────────────────────────────────────────
  
_SYSTEM_PROMPT = """You are the full prompt-engineering room for "Market Debunk": finance researcher,
retention strategist, short-form scriptwriter, visual director, and YouTube metadata editor.
You generate one premium English finance YouTube Short as strict JSON.

CHANNEL TONE: Sharp, satirical financial mythbuster meets late-night cinematic thriller.
Exposes predatory financial schemes, hidden banking traps, and stock market hype with dark wit,
street-smart cynicism, and surgical facts. NOT preachy, NOT robotic, NOT an academic lecture,
NOT a smiling teacher.

CORE JOB:
  1. Convert the story_seed into a viewer-retention story told in EXACTLY 6 scenes.
  2. Use only facts from the thesis/story_seed. Do not invent company names, dates, prices,
     laws, returns, or statistics unless they appear in the seed.
  3. When the seed lacks a precise number, use qualitative language such as "quietly",
     "often", "nobody's watching", or "the hidden cost".
  4. Make every scene visually different enough that a viewer feels forward motion.

TARGET RUNTIME: 22–26 seconds total. 55–75 narration words across all 6 scenes (9–13 words per scene).
This is the exact format YouTube Shorts, Instagram Reels, and Facebook Reels maximally reward in 2026.

──────────────────────────────────────────────────────────────────────────────
THE 6-SCENE FAST-HOOK ARC (~24 SECONDS TOTAL)
──────────────────────────────────────────────────────────────────────────────

Scene 1 — THE HOOK (0–4s): COLD VISUAL PROOF. Stops the scroll in the first spoken word.
  • Name a concrete financial threat in the FIRST 8 words. Use a number or % if the seed has one.
  • Pattern: "Your [familiar thing] just [shocking verb] ₹X — without telling you."
  • STRICTLY BANNED IN SCENE 1: talking heads, portraits, calm people, smiling presenter, text overlays.
  • broll_keyword: high-action financial footage ("stock chart drop", "candlestick crash", "bank alert screen").

Scene 2 — THE COMPLICATION (4–8s): The hidden trap the viewer didn't see.
  • Contextual B-roll objects, screens, documents. NO PEOPLE.
  • Bridge phrase: "What you didn't see:" or "And that's when it started."

Scene 3 — THE MATH (8–13s): Concrete ₹ loss or % spread, shown as B-roll evidence.
  • Contextual B-roll. NO PEOPLE.
  • Use an illustrative number if the seed has one: "₹1,200 vanished. Every single month."

Scene 4 — THE REVEAL (13–18s): Name the financial concept. Name the villain mechanism.
  • Contextual B-roll or motion graphic. NO PEOPLE.
  • "That's called [Concept Name] — and [institution/system] designed it to stay invisible."

Scene 5 — THE RULE (18–22s): One sharp, actionable defense — addressed directly to "you".
  • Contextual B-roll. NO PEOPLE.
  • "Here's the rule: [specific, actionable instruction in plain English]."

Scene 6 — THE CTA (22–26s): Final takeaway + high-converting share & comment trigger.
  • Spoken trigger: "Share this with a friend and comment 'GUIDE' below for the breakdown."
  • Can depict host Arjun in dark teal room, or a macro financial defense checklist close-up.

──────────────────────────────────────────────────────────────────────────────
NARRATION STYLE (CONTINUOUS STORYTELLING — NEVER A LIST OF FACTS)
──────────────────────────────────────────────────────────────────────────────
  • Write ONE continuous spoken story. Every scene must flow into the next with bridges:
    ("And", "So", "Until", "Because", "That's when", "What you didn't see was").
  • Use "you" or "your" in AT LEAST 3 of the 6 scenes to keep it personal and urgent.
  • 55–75 narration words total. 9–13 words per scene.
  • When read aloud from Scene 1 to Scene 6 it MUST sound like ONE seamless 24-second financial story.
  • Banned: "not financial advice", "let's dive in", "subscribe", numbered lists, robotic bullet points.

──────────────────────────────────────────────────────────────────────────────
VISUAL PROMPT GUIDELINES
──────────────────────────────────────────────────────────────────────────────
Scene 1 visual_prompt: tangible finance evidence — plummeting chart, trading screen, ticker board, alert notification. NO HUMAN FACES.
Scenes 2–5 visual_prompts: concrete objects, documents, screens, or environments. NO PEOPLE.
Scene 6 visual_prompt: Arjun (host) in dark teal room OR a macro financial defense checklist.

Every visual_prompt must:
  • describe a full-bleed 9:16 frame with no black bars or empty background.
  • use split amber-teal lighting (#E8A855 amber key, #0D2A32 teal shadow fill).
  • assume photoreal cinematic realism. Never 3D cartoon.

NEGATIVE PROMPTING FOR HALLUCINATION:
  • Do not fabricate exact numbers, returns, dates, prices, regulations, or quotes.
  • No readable text inside images. Use abstract charts, blurred dashboards, icons, color-coded arrows.
  • No celebrity likenesses, real logos, exchange logos, broker logos, or branded app screens.

OUTPUT FORMAT — Return ONLY valid JSON, nothing else, no markdown fences:
──────────────────────────────────────────────────────────────────────────────
{
  "title": "Punchy English title max 60 chars — grabs attention immediately; do NOT include #Shorts",
  "description": "SEO description 150-300 chars — explains the finance concept revealed at the end",
  "hashtags": ["StockMarket", "InvestingIndia", "FinanceShorts", "MarketDebunk", "MoneyTips"],
  "scenes": [
    {
      "scene_id": 1,
      "narration": "Present-tense hook narration addressed to YOU. 9-13 words. Flows into scene 2.",
      "visual_prompt": "Extreme macro close-up of a stock market candlestick chart plummeting off a cliff with sharp red drop lines, glowing trading desk monitors blurred in the background, split amber-teal light, photoreal cinematic, full-bleed 9:16",
      "broll_keyword": "stock chart drop",
      "duration_hint": 4.0
    }
  ]
}

CRITICAL: Exactly 6 scenes. 55–75 total narration words. One seamless 24-second story, NOT a list of facts. Use 'you/your' in at least 3 scenes."""

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

# ──────────────────────────────────────────────────────────────────────────────
#  Model Priority: Gemma is Primary Agent, followed by Gemini API models
#  STATIC TEMPLATES HAVE BEEN PERMANENTLY REMOVED: RUNS VIA API ONLY
# ──────────────────────────────────────────────────────────────────────────────

_MODELS_PRIORITY = [
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest",
]

def _get_api_clients():
    from google import genai
    import os
    keys_str = (
        os.getenv("GEMINI_SCRIPT_API_KEY")
        or os.getenv("GEMINI_API_KEY")
        or os.getenv("LLM_API_KEYS")
        or os.getenv("LLM_API_KEY")
        or getattr(settings, "GEMINI_SCRIPT_API_KEY", "")
        or getattr(settings, "GEMINI_API_KEY", "")
        or ""
    )
    keys = [k.strip() for k in keys_str.split(",") if k.strip()]
    clients = []
    for k in keys:
        try:
            clients.append(genai.Client(api_key=k))
        except Exception:
            pass
    if not clients:
        try:
            clients.append(genai.Client(vertexai=True, project="exalted-shape-502013-q5", location="us-central1"))
        except Exception:
            pass
    return clients

def _get_system_prompt_with_negative_guidance() -> str:
    """Dynamically append deprecated patterns from the 48h analytics sensor to system prompt."""
    prompt = _SYSTEM_PROMPT
    try:
        from src.analytics.analytics_sensor import AnalyticsSensor
        deprecated = AnalyticsSensor().load_deprecated_patterns()
        if deprecated:
            patterns_str = "\n".join(f"  • Underperforming hook format: \"{p}\"" for p in deprecated[:8])
            prompt += (
                f"\n\nNEGATIVE PATTERN GUIDANCE (Live 48h Algorithmic Feedback):\n"
                f"The following hook formulas failed audience retention (< 50% APV) in recent uploads.\n"
                f"DO NOT use or mimic these phrasing patterns:\n"
                f"{patterns_str}\n"
            )
            log.info("✓ Injected %d deprecated patterns into scriptwriter prompt", min(8, len(deprecated)))
    except Exception as exc:
        log.debug("Could not inject deprecated patterns: %s", exc)

    try:
        from src.analytics.tuner_agent import PerformanceTuningAgent
        tuner_directives = PerformanceTuningAgent().get_script_directives_prompt()
        if tuner_directives:
            prompt += tuner_directives
            log.info("✓ Injected algorithmic tuning directives into scriptwriter prompt")
    except Exception as exc:
        log.debug("Could not inject tuning directives: %s", exc)

    return prompt


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=10))
def _call_model(user_prompt: str, model_name: str) -> str:
    """Call Gemma or Gemini API with key rotation and system instruction."""
    from google.genai import types

    clients = _get_api_clients()
    if not clients:
        raise RuntimeError("No Google AI API keys available to call model.")

    system_instruction = _get_system_prompt_with_negative_guidance()

    config_args = {
        "system_instruction": system_instruction,
        "temperature": 0.70,
        "max_output_tokens": 4000,
    }
    if "gemini" in model_name:
        config_args["response_mime_type"] = "application/json"

    last_exc = None
    for client in clients:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=user_prompt,
                config=types.GenerateContentConfig(**config_args),
            )
            if response and response.text:
                return response.text
        except Exception as e:
            last_exc = e
            continue
    raise last_exc or RuntimeError(f"All clients failed for model {model_name}")


def _repair_json(raw_response: str, error: Exception, model_name: str, target_scenes: int = 6) -> str:
    """Repair an attempted Market Debunk script response when JSON parsing or validation fails."""
    repair_prompt = f"""Repair the following attempted Market Debunk script response into complete valid JSON.
The previous attempt failed validation with error:
{error}

CRITICAL RULES:
1. Return ONLY pure valid JSON with no markdown code fences (no ```json).
2. Exactly {target_scenes} scenes in the scenes array (scene_id 1 to {target_scenes}).
3. Ensure total narration word count across all scenes is 55-80 words (~9-12 words per scene).
4. Scene 1 visual_prompt MUST open on cold visual evidence (plummeting candlestick chart, trading screen, bank alert). Scenes 2-{target_scenes-1} MUST describe contextual B-roll objects/screens/documents. Include broll_keyword for all scenes.
5. Address the viewer directly ("you"), with an urgent viral hook in scene 1.
6. CONTINUOUS STORYTELLING: Narrations must read as ONE seamless spoken story with narrative conjunctions ("and", "so", "until", "because", "that's when"), NOT a list of facts or isolated bullets.

ATTEMPTED RESPONSE:
{raw_response}
"""
    return _call_model(repair_prompt, model_name)

def generate_script(
    thesis: str,
    channel_name: str,
    story_seed: Optional[dict] = None,
    target_scenes: int = 6,
) -> ScriptPayload:
    """
    Generate a Fast-Hook cinematic story script under 30 seconds (target 6 scenes, 55-75 words).
    """
    log.info("Generating Fast-Hook (%d scenes, < 30s) script | thesis: '%s'", target_scenes, thesis)

    seed_context = ""
    if story_seed:
        seed_context = f"""
STORY SEED:
Inciting Event (Scene 1): {story_seed.get('inciting_event', '')}
Protagonist's Flaw (Scenes 2-3): {story_seed.get('protagonist_flaw', '')}
Real World Anchor (Scene 4): {story_seed.get('real_world_anchor', '')}
Finance Concept to Reveal (Scene 5): {story_seed.get('concept_name', '')}
Plain Definition: {story_seed.get('concept_one_liner', '')}
Safe Visual Evidence Object: {story_seed.get('visual_evidence', '')}
"""

    finetuning_context = ""
    try:
        from src.agents.feedback_intelligence_agent import FeedbackIntelligenceAgent
        fia = FeedbackIntelligenceAgent()
        finetuning_context = fia.get_video_finetuning_prompt_injection()
    except Exception as fe:
        log.warning("Feedback intelligence injection note: %s", fe)

    user_prompt = f"""Core financial thesis: "{thesis}"
{seed_context}
Now generate the complete {target_scenes}-scene Fast-Hook cinematic short-story script (< 30s runtime, 55-75 words total) as JSON.
Remember: Exactly {target_scenes} scenes.

Before answering, internally check that:
- the title has no #Shorts tag and is max 50 chars;
- scene 1 has an urgent, scroll-stopping viral hook (0-3s) that speaks directly to the viewer;
- the narrations tell a single, continuous, suspenseful spoken story with natural connective flow ("and", "so", "until", "because", "that's when"), NEVER a list of facts;
- scene 1 visual_prompt opens cold on dramatic evidence (crashing red candlestick chart, trading screen, bank alert);
- scenes 2-{target_scenes-1} describe contextual B-roll objects, screens, or documents with broll_keyword (NO people);
- scene {target_scenes} delivers the sharp takeaway rule and spoken CTA;
- the total narration across all {target_scenes} scenes is 55-75 words (target 22-26 seconds runtime)."""

    for model in _MODELS_PRIORITY:
        log.info("Trying model (Gemma/Gemini API): %s", model)
        try:
            raw = _call_model(user_prompt, model)
            log.debug("Raw response: %d chars", len(raw))

            data = None
            try:
                data = _extract_json(raw)
            except (json.JSONDecodeError, ValueError) as parse_error:
                log.warning("Model returned malformed JSON; requesting repair pass: %s", parse_error)
                try:
                    repaired_raw = _repair_json(raw, parse_error, model, target_scenes=target_scenes)
                    data = _extract_json(repaired_raw)
                except Exception as repair_err:
                    log.warning("JSON repair pass failed: %s", repair_err)
                    continue

            if not data:
                continue

            try:
                script = ScriptPayload(**data)
            except Exception as val_error:
                log.warning("Script failed validation (%s); attempting repair pass", val_error)
                try:
                    repaired_raw = _repair_json(raw, val_error, model, target_scenes=target_scenes)
                    data = _extract_json(repaired_raw)
                    script = ScriptPayload(**data)
                except Exception as val_repair_err:
                    log.warning("Validation repair pass failed: %s", val_repair_err)
                    continue

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
        f"All AI API models ({_MODELS_PRIORITY}) failed to produce a valid 6-scene Fast-Hook script for: '{thesis}'. "
        "Static fallback templates have been permanently deleted per user configuration."
    )

def script_to_dict(script: ScriptPayload) -> dict:
    return script.model_dump()
