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
#  Visual Bible — Netflix India Premium Drama (consistent across ALL scenes)
# ──────────────────────────────────────────────────────────────────────────────

_STYLE_PREFIX = (
    "Cinematic 9:16 vertical frame, shot on RED camera, shallow depth of field bokeh, "
    "warm teal-orange color grade (teal shadows, warm amber skin tones), "
    "premium Indian corporate setting (Chennai — glass office / modern home office / "
    "upscale apartment living room), photorealistic, film still quality, "
    "no text, no watermarks, no logos, no captions, "
)

# Arjun — fixed character bible (same man in every scene)
_ARJUN_BIBLE = (
    "Arjun: Indian male protagonist, 35 years old, sharp angular features, "
    "neatly combed dark black hair, warm medium-brown skin, "
    "wearing a crisp light blue formal shirt, slim medium build, "
    "photorealistic, same man in every scene, "
)

# Priya — fixed character bible (same woman in every scene)
_PRIYA_BIBLE = (
    "Priya: Indian female, 33 years old, calm and confident, "
    "professional navy-blue kurta or formal attire, dark hair tied back, "
    "slight knowing smile, warm intelligent eyes, same woman in every scene, "
    "photorealistic, "
)


def _build_enhanced_prompt(raw_prompt: str, scene_id: int) -> str:
    """
    Enforces the consistent visual bible on every scene prompt.
    - Scenes 1-4: Arjun only
    - Scene 5+: Both Arjun and Priya may appear
    - Scene 8: Priya facing camera (4th wall)
    """
    prompt = raw_prompt.strip()

    # Check which characters are needed
    priya_keywords = ["priya", "wife", "her ", "she ", "woman", "camera", "viewer"]
    arjun_keywords = ["arjun", "man", "businessman", "investor", "he ", "him ", "his "]

    needs_priya = any(kw in prompt.lower() for kw in priya_keywords) or scene_id >= 5
    needs_arjun = any(kw in prompt.lower() for kw in arjun_keywords) or scene_id <= 7

    # Build character context
    char_context = ""
    if needs_arjun and needs_priya:
        char_context = _ARJUN_BIBLE + _PRIYA_BIBLE
    elif needs_priya:
        char_context = _PRIYA_BIBLE
    elif needs_arjun:
        char_context = _ARJUN_BIBLE

    # Special handling: scene 8 is always Priya facing camera
    if scene_id == 8:
        enhanced = (
            _STYLE_PREFIX
            + _PRIYA_BIBLE
            + "Priya standing in a warm-lit home office, facing directly into camera with a calm confident smile, "
            "slight over-the-shoulder composition, soft bokeh background showing Arjun out of focus, "
            "direct eye contact with camera, empowering moment, "
            "9:16 vertical, Netflix India color grade, cinematic, no text"
        )
    else:
        enhanced = _STYLE_PREFIX + char_context + prompt
        # Enforce no text and ensure correct ratio
        if "9:16" not in enhanced:
            enhanced += ", 9:16 vertical, Netflix India color grade, cinematic, no text"

    log.info("Scene %d enhanced prompt: '%s...'", scene_id, enhanced[:120])
    return enhanced


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=60))
def _call_imagen(prompt: str, output_path: Path):
    r = client.models.generate_content(
        model='gemini-2.5-flash-image',
        contents=prompt,
        config=types.GenerateContentConfig(response_modalities=['IMAGE'])
    )
    image_bytes = r.candidates[0].content.parts[0].inline_data.data
    with open(output_path, 'wb') as f:
        f.write(image_bytes)
    return True


def generate_image(prompt: str, output_path: Path, scene_id: int = 0) -> bool:
    try:
        enhanced_prompt = _build_enhanced_prompt(prompt, scene_id)
        log.info("Generating image for scene %d via Vertex AI (gemini-2.5-flash-image)...", scene_id)
        _call_imagen(enhanced_prompt, output_path)
        log.info("Scene %d image saved successfully (Vertex AI).", scene_id)
        return True
    except Exception as exc:
        log.warning(
            "Vertex AI Image generation failed for scene %d: %s. Trying safe fallback...",
            scene_id, exc
        )
        try:
            # Safe fallback: generic corporate finance visual, still on-brand
            safe_prompt = (
                _STYLE_PREFIX
                + "Abstract cinematic shot of a glass-walled Chennai office at dusk, "
                "stock market data visible on a monitor in soft bokeh, "
                "teal-orange color grade, no people, atmospheric, "
                "9:16 vertical, Netflix India color grade, cinematic, no text"
            )
            _call_imagen(safe_prompt, output_path)
            log.info("Scene %d safe fallback image saved successfully.", scene_id)
            return True
        except Exception as exc2:
            log.error("Safe fallback also failed for scene %d: %s. Copying placeholder.", scene_id, exc2)
            import shutil
            placeholder_path = Path("assets") / "host_original.png"
            if placeholder_path.exists():
                shutil.copy(placeholder_path, output_path)
                return True
            return False


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
            log.info(" o  Scene %d visual sourced | type: image | source: vertex_ai", scene_id)
        else:
            raise RuntimeError(f"Failed to generate visual for scene {scene_id}.")

    return visual_paths
