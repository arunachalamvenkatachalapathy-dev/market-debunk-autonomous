"""
src/agents/visual_agent.py

Visual Asset Generator - Gemini Image (gemini-3.1-flash-image via Vertex AI routing)

STYLE STANDARD: "City of Finance" YouTube Shorts aesthetic
  - Oil painting + cinematic photorealism hybrid
  - Dark charcoal background (#0D0D0D-#1A1513) + amber/gold accent (#C8922A)
  - Indian characters and settings
  - Chiaroscuro dramatic lighting (single warm lamp source)
  - 9:16 vertical format always
  - Painterly brushstroke texture
  - NO text, NO watermarks, NO neon, NO stock-photo smiles

CHARACTER BIBLE (injected into every prompt for consistency):
  The protagonist is an Indian male in his 40s, dark hair with slight grey temples,
  medium build, warm brown skin tone, thoughtful intense expression.
  Settings: Mumbai-style offices, old wooden desks, amber lamps, dark rooms.
"""
import os
import requests
import random
import time
import urllib.parse
from pathlib import Path
from src.utils.logger import get_logger

import vertexai
from vertexai.preview.vision_models import ImageGenerationModel
from tenacity import retry, stop_after_attempt, wait_exponential

# Initialize Vertex AI for Imagen 3
vertexai.init(project="exalted-shape-502013-q5", location="us-central1")

log = get_logger(__name__, phase="video_assembly")

GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"

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
    """Call Vertex AI Imagen 3 with exponential backoff via Tenacity."""
    model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")
    images = model.generate_images(
        prompt=prompt,
        number_of_images=1,
        language="en",
        aspect_ratio="9:16"
    )
    images[0].save(str(output_path))
    return True


def generate_image(prompt: str, output_path: Path, scene_id: int = 0) -> bool:
    """
    Generate an image using Vertex AI Imagen 3.
    """
    try:
        scene_specific = prompt.replace(_STYLE_PREFIX, "").replace(_CHARACTER_BIBLE, "").strip()
        enhanced_prompt = f"{_STYLE_PREFIX} {_CHARACTER_BIBLE} {scene_specific}"
        
        log.info(f"Generating image for scene {scene_id} via Vertex AI Imagen 3 (imagen-3.0-generate-002)...")
        _call_imagen(enhanced_prompt, output_path)
        log.info(f"Scene {scene_id} image saved successfully (Vertex AI).")
        return True
    except Exception as exc:
        log.error("Vertex AI Image generation failed for scene %d: %s", scene_id, exc)
        return False


# -----------------------------------------------------------------------------------------
# HUGGING FACE / POLLINATIONS FREE TIER FALLBACK (Commented out per user request for swap)
# -----------------------------------------------------------------------------------------
# def generate_image_hf(prompt: str, output_path: Path, scene_id: int = 0) -> bool:
#     try:
#         scene_specific = prompt.replace(_STYLE_PREFIX, "").replace(_CHARACTER_BIBLE, "").strip()
#         enhanced_prompt = f"{_STYLE_PREFIX} {_CHARACTER_BIBLE} {scene_specific}"
#         
#         hf_token = os.environ.get("HF_TOKEN")
#         
#         if hf_token:
#             log.info(f"Generating image for scene {scene_id} via Hugging Face API...")
#             api_url = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
#             headers = {"Authorization": f"Bearer {hf_token}"}
#             
#             for attempt in range(5):
#                 response = requests.post(api_url, headers=headers, json={"inputs": enhanced_prompt}, timeout=120)
#                 if response.status_code == 200:
#                     output_path.parent.mkdir(parents=True, exist_ok=True)
#                     with open(output_path, 'wb') as f:
#                         f.write(response.content)
#                     log.info(f"Scene {scene_id} image saved successfully (HF API).")
#                     return True
#                 elif "currently loading" in response.text.lower() or response.status_code == 503:
#                     backoff = 2 ** attempt * 5
#                     log.warning(f"Model loading (Attempt {attempt+1}/5). Waiting {backoff} seconds...")
#                     time.sleep(backoff)
#                 else:
#                     log.error(f"HF API returned unexpected status {response.status_code}: {response.text[:100]}")
#                     break
#             return False
#             
#         else:
#             base = bytes.fromhex('68747470733a2f2f696d6167652e706f6c6c696e6174696f6e732e61692f70726f6d70742f').decode('utf-8')
#             seed = random.randint(1, 999999)
#             url = f"{base}{urllib.parse.quote(enhanced_prompt)}?model=flux&width=1024&height=1024&nologo=true&seed={seed}"
#             
#             max_retries = 20
#             for attempt in range(max_retries):
#                 log.info(f"Generating cinematic FLUX image for scene {scene_id} (Attempt {attempt+1}/{max_retries})...")
#                 r = requests.get(url, timeout=60)
#                 
#                 if r.status_code == 200:
#                     output_path.parent.mkdir(parents=True, exist_ok=True)
#                     with open(output_path, 'wb') as f:
#                         f.write(r.content)
#                     log.info(f"Scene {scene_id} image saved successfully.")
#                     return True
#                 elif r.status_code == 429:
#                     backoff = min(60, 2 ** attempt * 5)
#                     log.warning(f"Queue full (429). Retrying in {backoff} seconds...")
#                     time.sleep(backoff)
#                 else:
#                     log.error(f"FLUX returned unexpected status for scene {scene_id}: {r.status_code} - {r.text[:100]}")
#                     return False
#                     
#             log.error(f"Failed to generate image for scene {scene_id} after {max_retries} attempts.")
#             return False
# 
#     except Exception as exc:
#         log.error("FLUX Image generation failed for scene %d: %s", scene_id, exc)
#         return False


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
