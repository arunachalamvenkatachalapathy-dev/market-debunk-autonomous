import os
import shutil
import time
from pathlib import Path
from typing import Optional

from src.utils.logger import get_logger
from src.utils.config import settings
from src.agents import broll_agent

log = get_logger(__name__, phase="visual_sourcing")

# Fixed presenter avatar asset path
PRESENTER_AVATAR_PATH = Path("assets") / "presenter_avatar.png"


def source_all_visuals(scenes: list, output_dir: Path, story_seed: Optional[dict] = None) -> list:
    """
    Sources visual assets for each scene:
    - Scene 1 (The Hook): User's real face/portrait (assets/presenter_avatar.png) to anchor authority.
    - Scenes 2 to (N-1): Contextual dynamic Pexels B-roll (documents, charts, money, screens).
    - Scene N (The Closer / CTA): User's real face/portrait (assets/presenter_avatar.png).
    - Fallback: If Pexels fails on intermediate scenes, fallback to presenter portrait or available loop.
    - Zero GCP / Zero Vertex AI: No external paid cloud image gen dependencies.
    """
    if isinstance(output_dir, str):
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    visual_paths = []
    pexels_key = settings.PEXELS_API_KEY
    used_video_ids: set[int] = set()

    total_scenes = len(scenes)

    for idx, scene in enumerate(scenes):
        scene_id = scene["scene_id"]
        is_first_scene = (idx == 0 or scene_id == 1)
        is_last_scene = (idx == total_scenes - 1 or scene_id == total_scenes)

        # ── Mandatory Presenter Avatar for Scene 1 & Outro Scene ──
        if is_first_scene or is_last_scene:
            scene_img_path = output_dir / f"scene_{scene_id}.png"
            if PRESENTER_AVATAR_PATH.exists() and PRESENTER_AVATAR_PATH.stat().st_size > 0:
                shutil.copy2(PRESENTER_AVATAR_PATH, scene_img_path)
                visual_paths.append({
                    "scene_id": scene_id,
                    "asset_type": "image",
                    "asset_path": str(scene_img_path.resolve()),
                    "source": "presenter_avatar"
                })
                role = "Hook Anchor" if is_first_scene else "Closer CTA"
                log.info(" ✓ Scene %d visual sourced | type: image (Presenter Avatar - %s)", scene_id, role)
                continue
            else:
                log.warning("Presenter avatar (%s) not found; falling back to B-roll.", PRESENTER_AVATAR_PATH)

        # ── Contextual B-Roll for Intermediate Scenes (or fallback if avatar missing) ──
        sourced = False
        if pexels_key:
            video_filename = f"scene_{scene_id}.mp4"
            video_filepath = output_dir / video_filename
            queries = broll_agent.generate_scene_queries(scene, story_seed=story_seed)
            log.info("Scene %d dynamic B-roll query options: %s", scene_id, queries)

            broll_result = broll_agent.fetch_fresh_pexels_broll(
                queries=queries,
                pexels_key=pexels_key,
                output_path=video_filepath,
                session_used_ids=used_video_ids,
            )
            if broll_result:
                visual_paths.append({
                    "scene_id": scene_id,
                    "asset_type": "video",
                    "asset_path": str(video_filepath.resolve()),
                    "source": "pexels",
                    "video_id": broll_result.get("video_id"),
                    "query": broll_result.get("query"),
                })
                log.info(" ✓ Scene %d fresh B-roll sourced (Pexels ID %s)", scene_id, broll_result.get("video_id"))
                sourced = True

        if not sourced:
            # Fallback: Use presenter portrait still with cinematic ken-burns pan-zoom
            scene_img_path = output_dir / f"scene_{scene_id}.png"
            if PRESENTER_AVATAR_PATH.exists() and PRESENTER_AVATAR_PATH.stat().st_size > 0:
                shutil.copy2(PRESENTER_AVATAR_PATH, scene_img_path)
                visual_paths.append({
                    "scene_id": scene_id,
                    "asset_type": "image",
                    "asset_path": str(scene_img_path.resolve()),
                    "source": "presenter_avatar"
                })
                log.info(" ✓ Scene %d visual fallback to presenter avatar", scene_id)
            else:
                raise RuntimeError(f"Could not source visual for scene {scene_id} and presenter avatar missing.")

    return visual_paths
