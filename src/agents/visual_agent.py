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
#  Visual Bible — Premium Corporate Aesthetic
# ──────────────────────────────────────────────────────────────────────────────

_STYLE_PREFIX = (
    "Cinematic 9:16 vertical frame, premium corporate aesthetic, minimalist, clean lines, "
    "soft warm studio lighting, deep navy and amber color palette, highly consistent, "
    "film still quality, no text, no watermarks, no logos, no captions, "
)

# Priya - fixed character bible (Scenes 1-5)
_PRIYA_BIBLE = (
    "Priya: Indian female corporate professional, 30 years old, sharp features, "
    "wearing a sleek navy-blue blazer over a white blouse, highly consistent, "
    "photorealistic, same woman in every scene, "
)

# News Anchor - 4th-wall revealer (Scenes 7-8)
_NEWS_ANCHOR_BIBLE = (
    "Financial News Anchor: Professional Indian male news broadcaster, late 30s, "
    "sharp tailored charcoal-grey blazer, crisp white dress shirt, neatly groomed hair, "
    "seated at a sleek high-tech glass broadcast news desk, glowing abstract stock market charts "
    "and tickers visible in soft background bokeh, studio key lighting, authoritative broadcast presence, "
    "direct eye contact with the camera lens, photorealistic, "
)


def _build_enhanced_prompt(raw_prompt: str, scene_id: int) -> str:
    """
    Enforces the consistent visual bible on every scene prompt:
    - Scenes 1-5: Priya in corporate / home office setting
    - Scene 6: Real-world market background / data visual
    - Scenes 7-8: News Anchor in broadcast studio breaking the 4th wall
    """
    prompt = raw_prompt.strip()

    if scene_id in (7, 8):
        if scene_id == 8:
            enhanced = (
                _STYLE_PREFIX
                + _NEWS_ANCHOR_BIBLE
                + "News Anchor leaning forward slightly at the glass broadcast desk, looking dead into the camera lens with intense conviction, "
                "speaking directly to the viewer, breaking the fourth wall, broadcast television studio lighting with deep teal and warm amber backlights, "
                "close-up shot, 9:16 vertical, premium corporate aesthetic, cinematic, no text"
            )
        else:
            enhanced = (
                _STYLE_PREFIX
                + _NEWS_ANCHOR_BIBLE
                + prompt
                + ", 9:16 vertical, premium corporate aesthetic, cinematic, no text"
            )
    elif scene_id == 6:
        enhanced = (
            _STYLE_PREFIX
            + "Cinematic shot of Dalal Street / Indian financial district skyscrapers, glass facades reflecting stock market exchange data, "
            + prompt
            + ", 9:16 vertical, premium corporate aesthetic, cinematic, no text"
        )
    else:
        # Scenes 1-5: Priya
        enhanced = _STYLE_PREFIX + _PRIYA_BIBLE + prompt
        if "9:16" not in enhanced:
            enhanced += ", 9:16 vertical, premium corporate aesthetic, cinematic, no text"

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
            if scene_id in (7, 8):
                safe_prompt = (
                    _STYLE_PREFIX
                    + _NEWS_ANCHOR_BIBLE
                    + "News anchor in broadcast studio looking directly into camera, 9:16 vertical, cinematic, no text"
                )
            else:
                safe_prompt = (
                    _STYLE_PREFIX
                    + "Abstract cinematic shot of a glass-walled Chennai corporate office at dusk, "
                    "stock market data visible on a monitor in soft bokeh, "
                    "teal-orange color grade, atmospheric, "
                    "9:16 vertical, premium corporate aesthetic, cinematic, no text"
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
