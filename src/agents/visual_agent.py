import os
import time
from pathlib import Path
from src.utils.logger import get_logger
from tenacity import retry, stop_after_attempt, wait_exponential

from google import genai
from google.genai import types

client = genai.Client(vertexai=True, project="exalted-shape-502013-q5", location="us-central1")

log = get_logger(__name__, phase="video_assembly")

# ──────────────────────────────────────────────────────────────────────────────
#  Visual Bible — Fixed Aesthetics & Character Consistency
# ──────────────────────────────────────────────────────────────────────────────

_STYLE_TAG = (
    "semi-stylized 3D-cartoon render with photoreal skin and cinematic lighting, "
    "full-bleed 1080x1920 vertical 9:16 composition, edge-to-edge filled frame, "
    "no letterbox bars, no pillarbox bars, no unused black canvas, highly detailed. "
    "Color palette: deep teal-navy background (#1B3540), warm amber practical light "
    "(#E8A855), powder-blue shirt (#AECBDA). Include a distinct foreground element "
    "(glass reflection, out-of-focus plant, doorway edge, desk edge, phone edge) "
    "to create depth and stop the image from feeling generic."
)

_ARJUN_BIBLE = (
    "Indian man, early-to-mid 30s, dark brown hair with natural wave, side "
    "part to his left, a few loose strands in casual settings, thick "
    "naturally-shaped dark eyebrows, warm wheatish-brown skin, clean-shaven "
    "with a defined jawline, soft smile lines, medium-lean build. Wearing a "
    "light powder-blue button-down shirt, top button undone, sleeves rolled "
    "to two folds above the wrist, thin stainless-steel analog watch on his "
    "left wrist. Semi-stylized 3D-cartoon render, photoreal skin/lighting "
    "texture, not flat-shaded, not fully photorealistic."
)

_PRIYA_BIBLE = (
    "Indian woman, early-to-mid 30s, dark hair pulled back into a low bun "
    "with a center part, small red bindi on the forehead, warm brown eyes, "
    "calm gentle default expression, slim build, relaxed upright posture. "
    "Wearing a deep navy mandarin-collar blouse with three-quarter sleeves, "
    "a single thin gold pendant necklace at the collar. Semi-stylized "
    "3D-cartoon render, photoreal skin/lighting texture, not flat-shaded, "
    "not fully photorealistic."
)

_NEGATIVE_PROMPT = (
    "NEGATIVE PROMPT: different character design, inconsistent face, morphed features, "
    "changed outfit, different hair, flat illustration, anime style, ugly, bad anatomy, "
    "text, readable words, logo, watermark, blurry, cropped composition, empty black space, "
    "dark blank frame, black background, letterboxing, pillarboxing, centered vignette, "
    "unused canvas edges, generic stock photo, photoreal photography, duplicate pose, "
    "duplicate background"
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
        "Create a premium finance-edutainment still, not a poster and not a slide. "
        "No readable text anywhere; financial information must appear as abstract charts, "
        "blurred dashboards, arrows, colored bars, or document shapes."
    )

    enhanced = (
        f"{scene_directive} {character_rule} Character bible: {char_context} "
        f"Scene direction: {prompt} Style: {_STYLE_TAG} {_NEGATIVE_PROMPT}"
    )

    log.info("Scene %d enhanced prompt: '%s...'", scene_id, enhanced[:120])
    return enhanced


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=60))
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


def generate_image(prompt: str, output_path: Path, scene_id: int = 0) -> bool:
    enhanced_prompt = _build_enhanced_prompt(prompt, scene_id)
    log.info("Generating image for scene %d via Vertex AI...", scene_id)
    try:
        _call_imagen(enhanced_prompt, output_path)
        log.info("Scene %d image saved successfully.", scene_id)
        return True
    except Exception as exc:
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
        else:
            raise RuntimeError(f"Failed to generate visual for scene {scene_id}.")

    return visual_paths
