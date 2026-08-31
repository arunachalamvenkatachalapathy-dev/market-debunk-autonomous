import os
import time
from pathlib import Path
from src.utils.logger import get_logger
from tenacity import retry, stop_after_attempt, wait_exponential

from google import genai
from google.genai import types

client = genai.Client(vertexai=True, project="exalted-shape-502013-q5", location="us-central1")

log = get_logger(__name__, phase="video_assembly")

_STYLE_PREFIX = (
    "Oil painting and cinematic photorealism hybrid, 9:16 vertical format, "
    "dark charcoal near-black background, rich amber and gold accent lighting from a single warm lamp, "
    "Indian setting (Mumbai / South India), painterly brushstroke texture visible in backgrounds, "
    "dramatic chiaroscuro lighting with deep shadows, depth of field bokeh on background, "
    "film still from a premium Indian drama, no text no watermarks no logos, "
)

_CHARACTER_BIBLE = (
    "Indian male protagonist, late 40s, dark hair with slight grey at temples, "
    "warm brown skin, medium build, formal white shirt, thoughtful intense expression, "
)

def _build_enhanced_prompt(raw_prompt: str, scene_id: int, character_name: str = None) -> str:
    prompt = raw_prompt.strip()
    if prompt.lower().startswith("pexels:"):
        prompt = prompt[len("pexels:"):].strip()

    protagonist_keywords = ["man", "businessman", "investor", "protagonist", "character",
                            "ramesh", "vijay", "suresh", "rohan", "he ", "him ", "his "]
    needs_character = any(kw in prompt.lower() for kw in protagonist_keywords)

    if needs_character:
        enhanced = _STYLE_PREFIX + _CHARACTER_BIBLE + prompt
    else:
        enhanced = _STYLE_PREFIX + prompt

    enhanced = enhanced.replace("stock photo", "oil painting")
    enhanced = enhanced.replace("realistic photo", "cinematic oil painting")

    log.info("Scene %d enhanced prompt: '%s...'", scene_id, enhanced[:120])
    return enhanced

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=60))
def _call_imagen(prompt: str, output_path: Path):
    # Use Gemini Flash Image (2026 Vertex AI standard) instead of legacy Imagen
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
        scene_specific = prompt.replace(_STYLE_PREFIX, "").replace(_CHARACTER_BIBLE, "").strip()
        enhanced_prompt = f"{_STYLE_PREFIX} {_CHARACTER_BIBLE} {scene_specific}"
        
        log.info("Generating image for scene %d via Vertex AI (gemini-2.5-flash-image)...", scene_id)
        _call_imagen(enhanced_prompt, output_path)
        log.info("Scene %d image saved successfully (Vertex AI).", scene_id)
        return True
    except Exception as exc:
        log.error("Vertex AI Image generation failed for scene %d: %s", scene_id, exc)
        return False

def source_all_visuals(scenes: list, output_dir: Path) -> list:
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    visual_paths = []

    for scene in scenes:
        scene_id = scene["scene_id"]
        raw_prompt = scene.get("visual_prompt", "")

        enhanced_prompt = _build_enhanced_prompt(raw_prompt, scene_id)

        filename = f"scene_{scene_id}.jpg"
        filepath = output_dir / filename

        success = generate_image(enhanced_prompt, filepath, scene_id)

        if success:
            visual_paths.append({
                "scene_id": scene_id,
                "asset_type": "image",
                "asset_path": str(filepath.resolve()),
            })
            log.info(" o  Scene %d visual sourced | type: image | source: vertex_ai", scene_id)
        else:
            raise RuntimeError(f"Failed to generate visual for scene {scene_id}.")

    return visual_paths
