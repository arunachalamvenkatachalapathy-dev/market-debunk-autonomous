from pathlib import Path

import pytest

from src.agents.quality_gate import validate_duration, validate_visual_assets
from src.agents.script_agent import ScriptPayload
from src.agents import evaluator
from src.utils.youtube_titles import normalize_youtube_title


def test_title_has_exactly_one_shorts_tag():
    assert normalize_youtube_title("Is Gold A Trap? #Shorts #SHORTS") == "Is Gold A Trap? #Shorts"


def test_dedup_catches_case_and_hashtag_variants(tmp_path: Path, monkeypatch):
    used_topics = tmp_path / "used_topics.json"
    monkeypatch.setattr(evaluator, "_TOPICS_PATH", used_topics)

    evaluator.record_title("Is Gold a Trap? Stop Losing Money! #Shorts")

    is_dup, score, match = evaluator.is_duplicate(
        "Is Gold A Trap? Stop Losing Money! #Shorts #Shorts",
        threshold=0.90,
    )

    assert is_dup is True
    assert score >= 0.90
    assert match == "Is Gold a Trap? Stop Losing Money! #Shorts"


def test_duration_gate_rejects_under_spec_video():
    with pytest.raises(RuntimeError, match="outside the required"):
        validate_duration(26)


def test_visual_gate_rejects_identical_assets(tmp_path: Path, monkeypatch):
    first = tmp_path / "scene_1.jpg"
    second = tmp_path / "scene_2.jpg"
    first.write_bytes(b"same image bytes")
    second.write_bytes(b"same image bytes")
    monkeypatch.setattr("src.agents.quality_gate._mean_luma", lambda _path: 50)

    with pytest.raises(RuntimeError, match="identical visual assets"):
        validate_visual_assets(
            [
                {"scene_id": 1, "asset_path": str(first)},
                {"scene_id": 2, "asset_path": str(second)},
            ],
            {1, 2},
        )


def test_script_gate_rejects_missing_priya_in_closing_scenes():
    scenes = []
    for scene_id in range(1, 13):
        character = "Arjun"
        scenes.append(
            {
                "scene_id": scene_id,
                "narration": f"{character} studies the confusing portfolio move and slowly realizes the simple money lesson hidden inside today.",
                "visual_prompt": (
                    f"{character} reviews a blurred red portfolio chart on a phone at a compact desk, "
                    "amber lamp against teal wall, over-shoulder full-bleed vertical frame"
                ),
                "duration_hint": 6.0,
            }
        )

    with pytest.raises(ValueError, match="Scene 11 visual_prompt must mention Priya"):
        ScriptPayload(
            title="Why Smart Investors Still Lose",
            description="A cinematic Market Debunk short explaining why a common investing habit quietly hurts returns.",
            hashtags=["StockMarket", "InvestingIndia", "MarketDebunk"],
            scenes=scenes,
        )
