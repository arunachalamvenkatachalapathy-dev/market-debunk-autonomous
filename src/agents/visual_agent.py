import os
import hashlib
import shutil
import time
from pathlib import Path

from google import genai
from google.genai import errors, types
from src.utils.logger import get_logger
from src.utils.config import settings
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential


client = genai.Client(vertexai=True, project="exalted-shape-502013-q5", location="us-central1")

log = get_logger(__name__, phase="video_assembly")
_CACHE_DIR = settings.OUTPUT_DIR / "visual_cache"

# ──────────────────────────────────────────────────────────────────────────────
#  Visual Bible — Fixed Aesthetics & Character Consistency
# ──────────────────────────────────────────────────────────────────────────────

_STYLE_TAG = (
    "photoreal cinematic still, 85mm lens, shallow depth of field, visible film grain, "
    "full-bleed 1080x1920 vertical 9:16 composition, edge-to-edge filled frame, "
    "no letterbox bars, no pillarbox bars, no unused black canvas. "
    "LIGHTING: extreme split light, warm amber key camera-left (#E8A855) carving the face, "
    "deep teal shadow fill camera-right (#0D2A32), thin teal rim on the dark-side hair. "
    "Background is a dark teal-navy void with at most one practical (amber lamp, doorway "
    "edge, desk edge, glass reflection). Highly detailed skin texture, not plastic."
)

_ARJUN_BIBLE = (
    "Indian man, 33, wheatish-olive skin with visible pores and faint five-o'clock "
    "shadow, dark brown hair slightly messy with a natural wave and a few strands "
    "falling over the forehead, thick dark eyebrows, warm brown heavy-lidded eyes, "
    "defined jaw, default expression is no smile, intense and slightly tired. "
    "Wearing a charcoal linen shirt, top two buttons open, no tie, no glasses, "
    "no gold chain. Optional thin stainless-steel watch on the left wrist if hands "
    "are visible. Photoreal cinematic, not 3D cartoon, not Pixar, not illustration, "
    "not plastic skin, not a smiling presenter."
)

_PRIYA_BIBLE = (
    "Indian woman, 33, wheatish-brown skin, dark hair in a low slightly messy bun "
    "with a few loose strands, no bindi, sharp dark brows, warm brown eyes, calm "
    "lethal default expression with no polite smile. Wearing a deep charcoal silk "
    "mandarin-collar blouse, one thin gold pendant, small gold hoops. Photoreal "
    "cinematic, not 3D cartoon, not Pixar, not plastic skin."
)

_NEGATIVE_PROMPT = (
    "NEGATIVE PROMPT: 3D cartoon, Pixar, Disney, Unreal Engine character, plastic "
    "skin, smooth doll face, toothy smile, customer-service smile, raised friendly "
    "eyebrows, powder-blue shirt, white office shirt, suit and tie, world map, "
    "globe, studio cyclorama, even lighting, ring light, beauty lighting, flat "
    "illustration, anime, comic, readable text, words, numbers, logos, watermarks, "
    "brand names, newspaper masthead, phone UI text, labelled charts, black "
    "letterbox bars, empty black canvas, stock photo, celebrity likeness, different "
    "face, different hair, different outfit, glasses on Arjun, gold chain on Arjun, "
    "bindi on Priya, waving, presenter hands, pointing at floating text, bright "
    "office, daylight window, colourful infographic"
)


def _build_enhanced_prompt(raw_prompt: str, scene_id: int) -> str:
    """
    Enforces the consistent visual bible on every scene prompt.
    - Scenes 1-10: Arjun only
    - Scenes 11-12: Arjun or Priya (if Priya mentioned)
    """
    prompt = raw_prompt.strip()
    if not prompt:
        raise ValueError(f"Scene {scene_id} visual prompt is empty.")

    priya_keywords = ["priya", "wife", "her ", "she ", "woman"]
    needs_priya = any(kw in prompt.lower() for kw in priya_keywords)
    
    char_context = _ARJUN_BIBLE
    character_rule = "This scene must show Arjun clearly and consistently."
    if needs_priya and scene_id >= 10:
        char_context = _PRIYA_BIBLE
        character_rule = "This scene must show Priya clearly and consistently."

    scene_directive = (
        f"Scene {scene_id} of a 12-scene Market Debunk Short. "
        "Create a premium cinematic thriller still, not a poster, not a slide, not a cartoon. "
        "No readable text anywhere; financial information must appear as abstract charts, "
        "blurred dashboards, arrows, colored bars, or document shapes."
    )

    enhanced = (
        f"{scene_directive} {character_rule} Character bible: {char_context} "
        f"Scene direction: {prompt} Style: {_STYLE_TAG} {_NEGATIVE_PROMPT}"
    )

    log.info("Scene %d enhanced prompt: '%s...'", scene_id, enhanced[:120])
    return enhanced


def _is_quota_error(exc: BaseException) -> bool:
    if isinstance(exc, errors.APIError):
        return getattr(exc, "code", None) == 429 or "RESOURCE_EXHAUSTED" in str(exc)
    return False


def _retryable_image_error(exc: BaseException) -> bool:
    return _is_quota_error(exc) or isinstance(exc, errors.ServerError)


@retry(
    retry=retry_if_exception(_retryable_image_error),
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=8, min=20, max=180),
    reraise=True,
)
def _call_imagen(prompt: str, output_path: Path):
    r = client.models.generate_content(
        model='gemini-2.5-flash-image',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=['IMAGE']
        )
    )
    image_bytes = r.candidates[0].content.parts[0].inline_data.data
    with open(output_path, 'wb') as f:
        f.write(image_bytes)
    return True


def _cache_path_for_prompt(enhanced_prompt: str, scene_id: int) -> Path:
    digest = hashlib.sha256(enhanced_prompt.encode("utf-8")).hexdigest()[:20]
    return _CACHE_DIR / f"scene_{scene_id}_{digest}.jpg"


def _copy_cached_image(cache_path: Path, output_path: Path, scene_id: int) -> bool:
    if not cache_path.exists() or cache_path.stat().st_size == 0:
        return False
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cache_path, output_path)
    log.info("Scene %d image reused from visual cache.", scene_id)
    return True


def generate_image(prompt: str, output_path: Path, scene_id: int = 0) -> bool:
    enhanced_prompt = _build_enhanced_prompt(prompt, scene_id)
    cache_path = _cache_path_for_prompt(enhanced_prompt, scene_id)
    if _copy_cached_image(cache_path, output_path, scene_id):
        return True

    log.info("Generating image for scene %d via Vertex AI...", scene_id)
    try:
        _call_imagen(enhanced_prompt, output_path)
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output_path, cache_path)
        log.info("Scene %d image saved successfully.", scene_id)
        return True
    except Exception as exc:
        if _is_quota_error(exc):
            log.error(
                "Vertex AI quota exhausted while generating scene %d. "
                "Billing can be active while per-minute or regional image quota is still exhausted.",
                scene_id,
            )
        log.error("Vertex AI Image generation FATAL ERROR for scene %d: %s", scene_id, exc)
        # Fail loudly to prevent the entire video from rendering with a single placeholder
        raise exc


def source_all_visuals(scenes: list, output_dir: Path) -> list:
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    visual_paths = []

    for scene in scenes:
        scene_id = scene["scene_id"]
        raw_prompt = scene.get("visual_prompt", "")

        filename = f"scene_{scene_id}.jpg"
        filepath = output_dir / filename

        success = generate_image(raw_prompt, filepath, scene_id)

        if success:
            visual_paths.append({
                "scene_id": scene_id,
                "asset_type": "image",
                "asset_path": str(filepath.resolve()),
                "source": "vertex_ai"
            })
            log.info(" ✓ Scene %d visual sourced | type: image", scene_id)
            delay = settings.VISUAL_GENERATION_DELAY_SECONDS
            if delay > 0:
                time.sleep(delay)
        else:
            raise RuntimeError(f"Failed to generate visual for scene {scene_id}.")

    return visual_paths
