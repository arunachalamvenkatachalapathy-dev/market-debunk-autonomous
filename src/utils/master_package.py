"""Create a reusable English master package for the Tamil companion channel."""
from __future__ import annotations

import json
import shutil
from pathlib import Path


def export_master_package(run_dir: Path, thesis: str, script: dict, visuals: list[dict]) -> Path:
    """Copy scene assets plus the scene-aligned English script into one package."""
    package_dir = run_dir / "master_visual_package"
    assets_dir = package_dir / "visuals"
    assets_dir.mkdir(parents=True, exist_ok=True)

    manifest_scenes = []
    for visual in sorted(visuals, key=lambda item: item["scene_id"]):
        source = Path(visual["asset_path"])
        if not source.is_file():
            raise RuntimeError(f"Cannot export missing master visual: {source}")
        filename = f"scene_{visual['scene_id']}{source.suffix.lower() or '.jpg'}"
        shutil.copy2(source, assets_dir / filename)
        manifest_scenes.append({"scene_id": visual["scene_id"], "asset": f"visuals/{filename}"})

    manifest = {
        "schema_version": 1,
        "thesis": thesis,
        "script": script,
        "scenes": manifest_scenes,
    }
    (package_dir / "master_package.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return package_dir
