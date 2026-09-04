import os
import hashlib
import shutil
import time
import urllib.parse
from pathlib import Path
import requests

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
    "no gold chain. Photoreal cinematic, not 3D cartoon, not Pixar, not illustration, "
    "not plastic skin, not a smiling presenter."
)

_OBJECT_STYLE_TAG = (
    "photoreal cinematic macro still, 50mm lens, shallow depth of field, visible film grain, "
    "full-bleed 1080x1920 vertical 9:16 composition, edge-to-edge filled frame, "
    "no letterbox bars, no pillarbox bars, no unused black canvas. "
    "LIGHTING: dramatic split lighting, warm amber key (#E8A855) and deep teal shadow (#0D2A32). "
    "Subject is a detailed physical finance object, contract document, electronic terminal, or urban market scene. "
    "NO PEOPLE, NO FACES, NO HUMAN BEINGS, NO BODY PARTS."
)

_NEGATIVE_PROMPT_PORTRAIT = (
    "NEGATIVE PROMPT: 3D cartoon, Pixar, Disney, Unreal Engine character, plastic "
    "skin, smooth doll face, toothy smile, customer-service smile, raised friendly "
    "eyebrows, powder-blue shirt, white office shirt, suit and tie, world map, "
    "globe, studio cyclorama, even lighting, ring light, beauty lighting, flat "
    "illustration, anime, comic, readable text, words, numbers, logos, watermarks, "
    "brand names, newspaper masthead, phone UI text, labelled charts, black "
    "letterbox bars, empty black canvas, stock photo, celebrity likeness, different "
    "face, different hair, glasses on Arjun, gold chain on Arjun, waving, presenter hands"
)

_NEGATIVE_PROMPT_OBJECT = (
    "NEGATIVE PROMPT: human, person, man, woman, face, portrait, people, crowd of faces, "
    "hands, body, 3D cartoon, Pixar, Disney, plastic skin, readable text, legible typography, "
    "watermarks, brand logos, newspaper masthead, black letterbox bars, empty canvas, "
    "colourful infographic, flat illustration"
)


def _build_enhanced_prompt(raw_prompt: str, scene_id: int) -> str:
    """
    Enforces the visual bible on every scene prompt:
    - Scenes 1-11: 100% Contextual B-Roll Macro Object/Financial Evidence (NO PEOPLE)
    - Scene 12: Actionable Closer Takeaway
    """
    prompt = raw_prompt.strip()
    if not prompt:
        raise ValueError(f"Scene {scene_id} visual prompt is empty.")

    if scene_id == 12:
        character_rule = "This scene delivers the final warning directly and authoritatively."
        enhanced = (
            f"Scene {scene_id} of a 12-scene Market Debunk Short. "
            f"Create a premium cinematic thriller takeaway still. "
            f"{character_rule} Character bible: {_ARJUN_BIBLE} "
            f"Scene direction: {prompt} Style: {_STYLE_TAG} {_NEGATIVE_PROMPT_PORTRAIT}"
        )
    else:
        # Contextual B-roll scenes 1-11: strictly objects, charts, screens, documents, or environments (no human faces)
        enhanced = (
            f"Scene {scene_id} of a 12-scene Market Debunk Short. "
            f"Create a photorealistic cinematic macro B-roll still of finance evidence. "
            f"No human faces or people. Scene direction: {prompt} "
            f"Style: {_OBJECT_STYLE_TAG} {_NEGATIVE_PROMPT_OBJECT}"
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


def fetch_pexels_broll(query: str, pexels_key: str, output_path: Path, used_ids: set[int] | None = None) -> bool:
    """
    Search Pexels Video API for high-retention 1080x1920 vertical finance B-roll footage.
    Skips any videos already used by earlier scenes in the same video.
    """
    if not pexels_key or not query:
        return False
    try:
        headers = {"Authorization": pexels_key}
        clean_q = urllib.parse.quote(query.strip())
        url = f"https://api.pexels.com/videos/search?query={clean_q}&per_page=8&orientation=portrait"
        res = requests.get(url, headers=headers, timeout=12)
        if res.status_code == 200:
            videos = res.json().get("videos", [])
            for v in videos:
                vid_id = v.get("id")
                # Prevent reusing the same video asset across different scenes
                if used_ids is not None and vid_id in used_ids:
                    continue
                for vf in v.get("video_files", []):
                    w = vf.get("width", 0)
                    h = vf.get("height", 0)
                    link = vf.get("link")
                    # Must be portrait/vertical orientation
                    if h > w and link:
                        r = requests.get(link, stream=True, timeout=25)
                        if r.status_code == 200:
                            output_path.parent.mkdir(parents=True, exist_ok=True)
                            with open(output_path, "wb") as f:
                                for chunk in r.iter_content(chunk_size=1024 * 1024):
                                    if chunk:
                                        f.write(chunk)
                            if output_path.exists() and output_path.stat().st_size > 50000:
                                log.info(" ✓ Pexels vertical video downloaded for '%s' (ID %s, %d KB)", query, vid_id, output_path.stat().st_size // 1024)
                                if used_ids is not None and vid_id:
                                    used_ids.add(vid_id)
                                return True
    except Exception as e:
        log.warning("Pexels video fetch failed for '%s': %s", query, e)
    return False


def source_all_visuals(scenes: list, output_dir: Path) -> list:
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    visual_paths = []
    pexels_key = settings.PEXELS_API_KEY
    used_video_ids: set[int] = set()

    for scene in scenes:
        scene_id = scene["scene_id"]
        raw_prompt = scene.get("visual_prompt", "")
        broll_keyword = scene.get("broll_keyword", "").strip()

        # Strategy:
        # Scenes 1-11: Try Pexels vertical stock video first (cold proof hook for scene 1, contextual B-roll for 2-11);
        #              fallback to Imagen Macro Object Still
        # Scene 12: Actionable closer -> Imagen or Pexels
        sourced = False

        if 1 <= scene_id <= 11 and pexels_key and broll_keyword:
            video_filename = f"scene_{scene_id}.mp4"
            video_filepath = output_dir / video_filename
            log.info("Searching Pexels video for scene %d | keyword: '%s'...", scene_id, broll_keyword)
            if fetch_pexels_broll(broll_keyword, pexels_key, video_filepath, used_ids=used_video_ids):
                visual_paths.append({
                    "scene_id": scene_id,
                    "asset_type": "video",
                    "asset_path": str(video_filepath.resolve()),
                    "source": "pexels"
                })
                log.info(" ✓ Scene %d visual sourced | type: video (Pexels)", scene_id)
                sourced = True

        if not sourced:
            # Sourced via Vertex AI Imagen (Portraits for 1 & 12, Macro Objects for 2-11)
            img_filename = f"scene_{scene_id}.jpg"
            img_filepath = output_dir / img_filename
            success = generate_image(raw_prompt, img_filepath, scene_id)
            if success:
                visual_paths.append({
                    "scene_id": scene_id,
                    "asset_type": "image",
                    "asset_path": str(img_filepath.resolve()),
                    "source": "vertex_ai"
                })
                log.info(" ✓ Scene %d visual sourced | type: image (Vertex AI)", scene_id)
                delay = settings.VISUAL_GENERATION_DELAY_SECONDS
                if delay > 0:
                    time.sleep(delay)
            else:
                raise RuntimeError(f"Failed to generate visual for scene {scene_id}.")

    return visual_paths
