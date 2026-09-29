"""Visual sourcing for the reviewed, agent-rendered Market Debunk scene pack.

No stock, Pollinations, local B-roll or API image fallback is permitted. Every
scene must be present in the supplied inbox and the run fails closed otherwise.
"""
from pathlib import Path
from typing import Optional

from src.agents import story_image_agent


def source_all_visuals(scenes: list, output_dir: Path, story_seed: Optional[dict] = None) -> list:
    """Return exactly one reviewed story image per scene, or halt the run."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for scene in scenes:
        scene_id = scene["scene_id"]
        image_path = story_image_agent.generate_scene_image(scene, output_dir)
        results.append({
            "scene_id": scene_id,
            "asset_type": "image",
            "asset_path": str(image_path.resolve()),
            "source": "reviewed_agent_image",
        })
    return results
