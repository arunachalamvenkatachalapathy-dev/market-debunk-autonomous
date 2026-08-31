"""
src/agents/manager.py

The main orchestrator for the market-debunk-autonomous pipeline.
Executes the full daily workflow:
  1. Discovery & Thesis
  2. Dedup Gate
  3. Script Generation
  4. Voice Synthesis
  5. Visual Sourcing
  6. FFmpeg Assembly (Subtitles + BGM)
  7. Logging & Notifications
  8. YouTube Upload (optional)
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from src.utils.config import settings
from src.utils.logger import get_logger, PhaseTimer

# Import agents
from src.agents import topic_agent, script_agent, voice_agent, visual_agent, evaluator
from src.rendering import subtitles, assembler
from src.publishing import youtube_uploader, telegram_notifier

log = get_logger(__name__, phase="orchestrator")


def run_pipeline():
    """Execute the full autonomous video generation pipeline."""
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = settings.OUTPUT_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    
    audio_dir = run_dir / "audio"
    visuals_dir = run_dir / "visuals"
    
    log.info("==================================================")
    log.info("🚀 STARTING PIPELINE RUN: %s", run_id)
    log.info("==================================================")
    
    total_start = time.time()
    stats = {}

    try:
        # ── Phase 1: Topic Discovery ──────────────────────────────────────
        with PhaseTimer("Phase 1: Topic Discovery"):
            topic_data = topic_agent.discover_topic()
            channel = topic_data["channel"]
            video_id = topic_data["video_id"]
            thesis = topic_data["thesis"]
            story_seed = topic_data.get("story_seed", {})
            log.info("Chosen channel: %s", channel)
            log.info("Core thesis: %s", thesis)
            log.info("Story seed concept: %s", story_seed.get("concept_name", "N/A"))

        # ── Phase 1.5: Dedup Gate ─────────────────────────────────────────
        with PhaseTimer("Phase 1.5: Dedup Gate"):
            is_dup, score, match = evaluator.is_duplicate(thesis)
            if is_dup:
                log.warning("🛑 Topic is too similar to a recent video. Halting pipeline.")
                sys.exit(0)
            log.info("Topic passed uniqueness check.")

        # ── Phase 2: Script Generation ────────────────────────────────────
        with PhaseTimer("Phase 2: Script Generation"):
            script = script_agent.generate_script(thesis, channel, story_seed=story_seed)
            script_dict = script_agent.script_to_dict(script)
            
            # Save script to output for debugging
            script_path = run_dir / "script.json"
            import json
            script_path.write_text(json.dumps(script_dict, indent=2), encoding="utf-8")


        # ── Phase 3: Voice Synthesis ──────────────────────────────────────
        with PhaseTimer("Phase 3: Voice Synthesis"):
            voice_results = voice_agent.synthesize_all_scenes(script_dict["scenes"], audio_dir)
            stats["total_duration"] = sum(r["duration"] for r in voice_results)

        # ── Phase 4: Visual Sourcing ──────────────────────────────────────
        with PhaseTimer("Phase 4: Visual Sourcing"):
            visual_results = visual_agent.source_all_visuals(script_dict["scenes"], visuals_dir)
            stats["visual_sources"] = ", ".join(set(r["source"] for r in visual_results))

        # ── Phase 5: FFmpeg Assembly ──────────────────────────────────────
        with PhaseTimer("Phase 5: Video Assembly"):
            ass_path = run_dir / "subtitles.ass"
            subtitles.generate_ass_file(voice_results, ass_path)
            
            final_video = assembler.assemble_video(
                voice_results=voice_results,
                visual_results=visual_results,
                ass_path=ass_path,
                run_dir=run_dir,
            )

        # ── Phase 6: Post-Processing & Recording ──────────────────────────
        with PhaseTimer("Phase 6: Logging & Record keeping"):
            evaluator.record_topic(thesis)
            log.info("Recorded topic to prevent future duplicates.")

        # ── Phase 7: Publishing ───────────────────────────────────────────
        with PhaseTimer("Phase 7: Publishing"):
            yt_url = None
            if settings.ENABLE_YT_UPLOAD:
                yt_id = youtube_uploader.upload_video(
                    video_path=final_video,
                    title=script_dict["title"],
                    description=script_dict["description"],
                    hashtags=script_dict["hashtags"],
                )
                if yt_id:
                    yt_url = f"https://www.youtube.com/shorts/{yt_id}"

            if settings.ENABLE_TELEGRAM:
                telegram_notifier.send_completion_notification(
                    title=script_dict["title"],
                    thesis=thesis,
                    youtube_url=yt_url,
                    video_path=final_video,
                    run_stats=stats,
                )

        total_time = time.time() - total_start
        log.info("==================================================")
        log.info("✅ PIPELINE COMPLETED SUCCESSFULLY in %.1fs", total_time)
        log.info("Output Video: %s", final_video.resolve())
        log.info("==================================================")

    except SystemExit:
        log.info("Pipeline halted normally.")
    except Exception as exc:
        log.exception("❌ PIPELINE FAILED FATALLY: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    run_pipeline()
