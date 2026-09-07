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
        if not (6 <= len(v) <= 12):
            raise ValueError(f"Script must have between 6 and 12 scenes, got {len(v)}")
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
            cta_phrase = "Comment 'GUIDE' below for the breakdown."
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
        # Fast-Hook Short (< 30s): 50-85 words ideal. 12-scene format: up to 140 words.
        if total_words > 155:
            diff = total_words - 140
            for s in reversed(self.scenes[:-1]):
                words = s.narration.split()
                if len(words) > 10 and diff > 0:
                    trim = min(len(words) - 9, diff)
                    s.narration = " ".join(words[:-trim]).rstrip(" ,;:") + "."
                    diff -= trim
            total_words = sum(len(scene.narration.split()) for scene in self.scenes)

        if not 45 <= total_words <= 165:
            raise ValueError(
                f"Script must contain 45-165 narration words for high-retention Short; got {total_words}."
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
THE HOOK, B-ROLL & VISUAL ARCHITECTURE
──────────────────────────────────────────────────────────────────────────────
SCENE 1 (THE HOOK — COLD VISUAL PROOF & PATTERN INTERRUPT):
  • In vertical short-form video (Shorts/Reels), 90% of viewers scroll away within 2 seconds if shown static portraits or talking heads.
  • Scene 1 MUST OPEN COLD on dramatic, tangible financial evidence matching the audio hook:
    - Plummeting red candlestick chart dropping off a cliff
    - Mobile trading portfolio screen flashing a sudden loss
    - Electronic market ticker board showing the shock index level or freefall
    - Physical bank statement or deduction alert on a smartphone screen
  • STRICTLY BANNED IN SCENE 1: Static presenter portraits, human faces looking into camera, talking heads, calm smiling people, or self-promotional text.
  • "broll_keyword" for Scene 1 MUST be high-intent action footage: e.g., "stock chart drop", "candlestick chart red", "trading screen crash", "crypto market plunge", "mobile banking alert".

SCENES 2 THROUGH 11: 100% CONTEXTUAL B-ROLL & OBJECTS (NO PEOPLE/PORTRAITS!):
  • In YouTube Shorts, visual monotony kills retention. Never repeat the same portrait!
  • Scenes 2–11 MUST depict macro objects, documents, screens, and environments:
    - Credit card tapping a POS machine with amber alert glow
    - Physical bank statement with highlighted fee rows on a dark wooden desk
    - Stock market candlestick chart plummeting off a cliff
    - Busy shopping mall checkout counter or bustling Indian street market
    - Cash counting machine or stacks of Indian rupee notes next to a ledger
    - ATM screen with an unexpected fee deduction alert
  • For every scene, provide a "broll_keyword": 2-3 English search words for vertical 4K stock video (e.g. "credit card payment", "stock chart drop", "counting money", "shopping mall", "atm machine").

SCENE 12 (THE CLOSER & SPOKEN COMMENT ENGAGEMENT TRIGGER):
  • Delivers the single actionable takeaway rule directly to "you".
  • MUST END WITH THE EXACT SPOKEN PHRASE: "Comment 'GUIDE' below and I'll send you the complete playbook."
  • This voiceover CTA is voiced aloud by TTS and triggers viral comment-section ranking in the 2026 algorithm.

NARRATION STYLE (CRITICAL: CONTINUOUS STORYTELLING — NEVER READ A LIST OF FACTS):
  • You are telling a gripping financial story DIRECTLY TO THE VIEWER ("you").
  • CRITICAL RULE: DO NOT write 12 disconnected bullet points or isolated facts!
    Write a SINGLE continuous spoken story where every scene carries the narrative momentum
    into the next with conversational bridges ("And", "So", "Until", "Because", "That is when",
    "What you didn't see was").
  • Ban textbook academic jargon (do NOT say "retailers classified interest for GST").
    Use relatable conversational English: "While you celebrated zero percent interest, the bank secretly added eighteen percent tax onto every monthly installment."
  • When read together aloud from Scene 1 to Scene 12 without scene numbers, it MUST sound like
    ONE seamless, captivating, suspenseful spoken paragraph told by a master storyteller.
  • The viewer is the protagonist: use "you" and "your" in AT LEAST 8 of the 12 scenes.
  • THE HOOK (Scenes 1-2): Must stop the scroll in under 2 seconds. A vivid, personal event or shocking realization.
  • STORY FLOW (Scenes 3-10): The story unfolds organically — the illusion, the hidden trap, the silent loss, the realization.
  • CLIMAX & ADVICE (Scenes 11-12): Reveal the concept name and deliver the one sharp rule directly to you, ending with the spoken comment trigger.
  • Write 100-115 narration words total across all 12 scenes (6-16 words per scene).
  • Banned: generic disclaimers, "not financial advice", "let's dive in", "subscribe", numbered lists, or robotic bullet points.

──────────────────────────────────────────────────────────────────────────────
THE 12-SCENE CONTINUOUS STORY ARC (~50 seconds total runtime):
──────────────────────────────────────────────────────────────────────────────
The narration MUST read as ONE continuous story told directly to "you":

Scene 1 (The Hook): Cold visual proof. A vivid, relatable financial shock or warning that stops the scroll immediately on screen.
Scene 2 (The Complacency): Contextual B-roll. How you felt confident, believing you were making a smart financial move.
Scene 3 (The Setup): Contextual B-roll. The promise or illusion that made you trust the deal or market signal.
Scene 4 (The First Doubt): Contextual B-roll. The subtle catch or fine print detail that you overlooked.
Scene 5 (The Silent Trigger): Contextual B-roll. The hidden process starting behind the scenes, silently affecting your money.
Scene 6 (The Hidden Cost): Contextual B-roll. The quiet charges or deductions that began slipping past you.
Scene 7 (The Discovery): Contextual B-roll. The moment you noticed the numbers didn't add up on your statement or chart.
Scene 8 (The Contrast): Contextual B-roll. How smart institutional players anticipate this exact trap while you reacted.
Scene 9 (The Real Loss): Contextual B-roll. What this illusion actually costs you when the true math is added up.
Scene 10 (The Reality Check): Contextual B-roll. The sobering realization that what you thought was an advantage was a trap.
Scene 11 (The Concept Name): Contextual B-roll / Motion Graphic. Names the financial concept clearly and authoritatively.
Scene 12 (The Actionable Defense & Spoken Comment Trigger): The one practical rule to protect your money right now, strictly ending with: "Comment 'GUIDE' below and I'll send you the complete playbook."

──────────────────────────────────────────────────────────────────────────────
VISUAL PROMPT GUIDELINES
──────────────────────────────────────────────────────────────────────────────
Scene 1 visual_prompt MUST describe tangible finance evidence: a plummeting chart, trading screen, ticker board, or alert notification (NO HUMAN FACES!).
Scenes 2-11 visual_prompts MUST describe concrete objects, documents, screens, or environments (NO PEOPLE!).
Scene 12 visual_prompt can depict Arjun (host closer) in a dark teal room or a macro financial defense checklist.

Every visual_prompt must:
  • describe a full-bleed 9:16 frame with no black bars or empty background.
  • use split amber-teal lighting (#E8A855 amber key, #0D2A32 teal shadow fill).
  • assume photoreal cinematic realism. Never 3D cartoon.

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
      "narration": "Present-tense cinematic narration addressed to YOU. Max 20 words. Flows seamlessly into scene 2.",
      "visual_prompt": "Extreme macro close-up of a stock market candlestick chart plummeting off a cliff with sharp red drop lines, glowing trading desk monitors blurred in the background, split amber-teal light, photoreal cinematic, full-bleed 9:16",
      "broll_keyword": "stock chart drop",
      "duration_hint": 7.0
    }
  ]
}

CRITICAL: Exactly 12 scenes. Must sound like continuous personal storytelling, NOT a list of facts. Use 'you/your' in at least 8 scenes."""

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
        f"All AI API models ({_MODELS_PRIORITY}) failed to produce a valid 12-scene script for: '{thesis}'. "
        "Static fallback templates have been permanently deleted per user configuration."
    )

def script_to_dict(script: ScriptPayload) -> dict:
    return script.model_dump()
