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
    def check_12_scenes(cls, v):
        if len(v) != 12:
            raise ValueError(f"Script must have exactly 12 scenes, got {len(v)}")
        scene_ids = [scene.scene_id for scene in v]
        if scene_ids != list(range(1, 13)):
            raise ValueError(f"Scene IDs must be exactly 1 through 12 in order; got {scene_ids}.")
        # Scene 1 must show Arjun (the host face-cam hook)
        if "arjun" not in v[0].visual_prompt.lower():
            raise ValueError("Scene 1 visual_prompt must mention Arjun as the hook host.")
        # Scenes 2 to 11 must be contextual B-roll / objects / environment, NOT Priya
        for scene in v[1:11]:
            if "priya" in scene.visual_prompt.lower():
                raise ValueError(f"Scene {scene.scene_id} mentions Priya. Priya is removed; use contextual B-roll objects.")
        return v

    @model_validator(mode="after")
    def check_narration_pacing(self):
        total_words = sum(len(scene.narration.split()) for scene in self.scenes)
        # Target ~50s Short: 80-140 words ideal. Voice agent auto-clamps duration to 30-52s with atempo.
        if total_words > 155:
            # Auto-trim excess words from long scenes rather than failing fatally
            diff = total_words - 140
            for s in reversed(self.scenes):
                words = s.narration.split()
                if len(words) > 10 and diff > 0:
                    trim = min(len(words) - 9, diff)
                    s.narration = " ".join(words[:-trim]).rstrip(" ,;:") + "."
                    diff -= trim
            total_words = sum(len(scene.narration.split()) for scene in self.scenes)

        if not 65 <= total_words <= 165:
            raise ValueError(
                f"Script must contain 65-165 narration words for a ~50s Short; got {total_words}."
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

SCENE 12 (THE CLOSER & COMMENT ENGAGEMENT TRIGGER):
  • Delivers the single actionable takeaway rule directly to "you".
  • MUST END with an irresistible comment engagement call-to-action (e.g., "Comment 'GUIDE' below and I'll send you the full risk playbook", "Comment 'TRAP' below for the 3-step checklist", "Drop your stock in the comments to see if you're exposed").
  • In vertical video algorithms (YouTube/Instagram), comments and saves trigger viral distribution.

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
  • CLIMAX & ADVICE (Scenes 11-12): Reveal the concept name and deliver the one sharp rule directly to you, ending with the comment trigger.
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
Scene 12 (The Actionable Defense & Comment Trigger): The one practical rule to protect your money right now, ending with a direct trigger to comment (e.g. "Comment 'GUIDE' below for the playbook").

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

_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-1.5-flash",
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
    clean_thesis = " ".join(thesis.split())[:35].strip()
    narrations = [
        f"Wait—you think {clean_thesis} is real, but it is not.",
        "You saw that scary headline, but headlines deceive you.",
        "When prices dip, you might panic and sell immediately.",
        "That exact fear you feel is what institutions expect.",
        "Before you sell your assets, verify if anything broke.",
        "Check your volume charts before you call a crash.",
        "Ask yourself who profits from prices dropping before you.",
        "Big funds quietly accumulate while you run in fear.",
        "What you see is a classic Bear Trap.",
        "Smart money buys the dip your panic just created.",
        "Demand data before you let emotions drive your trade.",
        "Protect your hard-earned money and check facts before investing.",
    ]
    prompts = [
        "Arjun looking directly into the camera with an intense, serious expression, split amber-teal lighting, dark textured background, extreme close-up, full-bleed vertical frame",
        "A sleek smartphone resting on a dark wooden desk displaying an illuminated banking payment notification, amber rim light, macro cinematic shot",
        "A busy urban shopping street at dusk with blurred financial ticker displays and crowds in the background, cinematic depth of field, vertical frame",
        "Macro close-up shot of a modern credit card tapping a POS contactless terminal with an amber indicator light, clean composition",
        "A printed bank statement resting on a dark desk with fee deduction rows highlighted in subtle red ink, warm amber task lighting",
        "A digital ATM screen interface displaying an unexpected fee warning alert, split amber-teal illumination, close-up framing",
        "A financial candlestick chart plummeting sharply downward on an illuminated glass desktop monitor, dark moody ambiance",
        "Institutional trading station with multiple illuminated screens showing fluctuating financial bar graphs, sleek professional setup",
        "Crisp Indian currency notes and metallic coins arranged beside an open analytical ledger on a polished workspace, warm amber glow",
        "An abstract geometric financial risk gauge glowing softly in amber and teal across a dark screen, modern minimalist composition",
        "A clean financial equation and balance sheet graphic glowing on a modern glass display, amber accents, cinematic framing",
        "Arjun looking directly into the camera delivering a calm, authoritative closing takeaway, warm amber spotlight, crisp vertical frame",
    ]
    broll_keywords = [
        "worried investor face",
        "smartphone banking alert",
        "busy shopping street",
        "credit card payment pos",
        "bank statement document",
        "atm machine screen",
        "stock market crash chart",
        "trading desk monitors",
        "counting money cash",
        "financial risk graph",
        "balance sheet equation",
        "confident financial advisor",
    ]
    scenes = [
        {
            "scene_id": i,
            "narration": narrations[i - 1],
            "visual_prompt": prompts[i - 1],
            "broll_keyword": broll_keywords[i - 1],
            "duration_hint": 4.2
        }
        for i in range(1, 13)
    ]
    # Derive a unique, descriptive hook title from the thesis rather than a static duplicate
    clean_thesis = re.sub(r'[^a-zA-Z0-9\s]', '', thesis or "Market Truth")
    words = [w for w in clean_thesis.split() if len(w) > 2]
    hook_phrase = " ".join(words[:4]).title() if words else "Market Secret"
    dynamic_title = f"{hook_phrase}: The Hidden Truth"[:50]

    return ScriptPayload(
        title=dynamic_title,
        description=f"Uncovering the real mechanics behind {hook_phrase}. Concise finance insights that protect your capital.",
        hashtags=["#Finance", "#StockMarket", "#Shorts"],
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
3. Ensure total narration word count across all 12 scenes is 100-115 words (~8-10 words per scene, 6-16 words per scene).
4. Scene 1 visual_prompt MUST mention Arjun (face-cam hook). Scenes 2-11 MUST describe contextual B-roll objects/screens/documents (NO people, NO Priya). Scene 12 MUST show Arjun (closer). Include broll_keyword for all scenes.
5. Address the viewer directly ("you"), with an urgent viral hook in scenes 1-2.
6. CONTINUOUS STORYTELLING: Narrations must read as ONE seamless spoken story with narrative conjunctions ("and", "so", "until", "because", "that's when"), NOT a list of facts or isolated bullets. Use "you" or "your" in at least 8 scenes.

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
- the narrations tell a single, continuous, suspenseful spoken story with natural connective flow ("and", "so", "until", "because", "that's when"), NEVER a list of facts or disconnected bullet points;
- scene 1 mentions Arjun as the hook host;
- scenes 2-11 describe contextual B-roll objects, screens, or documents with broll_keyword (NO people, NO Priya);
- scene 12 mentions Arjun as the closing host;
- the total narration is 100-115 words (target ~50 seconds)."""

    for model in _GEMINI_MODELS:
        log.info("Trying model: %s", model)
        try:
            raw = _call_gemini(user_prompt, model)
            log.debug("Raw response: %d chars", len(raw))

            data = None
            try:
                data = _extract_json(raw)
            except (json.JSONDecodeError, ValueError) as parse_error:
                log.warning("Model returned malformed JSON; requesting repair pass: %s", parse_error)
                try:
                    repaired_raw = _repair_json(raw, parse_error, model)
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
                    repaired_raw = _repair_json(raw, val_error, model)
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
