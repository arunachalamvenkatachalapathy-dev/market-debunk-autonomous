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
from src.utils.master_package import export_master_package

# Import agents
from src.agents import topic_agent, script_agent, voice_agent, visual_agent, evaluator, quality_gate
from src.agents.distribution_seo_agent import DistributionSEOAgent
from src.rendering import subtitles, assembler
from src.publishing import youtube_uploader, telegram_notifier, instagram_publisher, facebook_publisher

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

            is_dup, score, match = evaluator.is_duplicate(script_dict["title"], threshold=0.90)
            if is_dup:
                log.warning("Generated title duplicates '%s' (similarity %.2f). Auto-correcting title angle...", match, score)
                concept = story_seed.get("concept", "") if isinstance(story_seed, dict) else ""
                clean_title = script_dict["title"].replace("#Shorts", "").strip()
                if concept and concept.lower() not in clean_title.lower():
                    script_dict["title"] = f"{clean_title[:36]}: {concept} #Shorts"[:60]
                else:
                    import time as _t
                    script_dict["title"] = f"{clean_title[:32]}: The Brutal Truth #Shorts"[:60]
                log.info("✓ Auto-corrected title to: '%s'", script_dict["title"])

            # Preflight timing before any TTS or visual generation.
            estimated_seconds = sum(
                len(scene.get("narration", "").split())
                for scene in script_dict["scenes"]
            ) / 2.3
            log.info("Timing preflight: %.1fs estimated before voice synthesis", estimated_seconds)
            # The voice agent has two-way automatic atempo clamping (30.5s - 52.0s),
            # so allow a safe window and let voice_agent clamp rather than failing early.
            if not 24 <= estimated_seconds <= 66:
                log.warning("Estimated duration %.1fs outside ideal window; voice agent will apply atempo clamping", estimated_seconds)
            
            # Save script to output for debugging
            script_path = run_dir / "script.json"
            import json
            script_path.write_text(json.dumps(script_dict, indent=2), encoding="utf-8")


        # ── Phase 3: Voice Synthesis ──────────────────────────────────────
        with PhaseTimer("Phase 3: Voice Synthesis"):
            voice_results = voice_agent.synthesize_all_scenes(script_dict["scenes"], audio_dir)
            stats["total_duration"] = sum(r["duration"] for r in voice_results)
            quality_gate.validate_duration(stats["total_duration"])

        # ── Phase 4: Visual Sourcing ──────────────────────────────────────
        with PhaseTimer("Phase 4: Visual Sourcing"):
            visual_results = visual_agent.source_all_visuals(
                script_dict["scenes"], visuals_dir, story_seed=story_seed
            )
            stats["visual_sources"] = ", ".join(set(r["source"] for r in visual_results))
            quality_gate.validate_visual_assets(
                visual_results,
                {scene["scene_id"] for scene in script_dict["scenes"]},
            )
            master_package = export_master_package(
                run_dir,
                thesis,
                script_dict,
                visual_results,
                source_id=topic_data.get("source_id", ""),
            )
            log.info("Exported Tamil companion visual package: %s", master_package)

        # ── Phase 5: FFmpeg Assembly ──────────────────────────────────────
        with PhaseTimer("Phase 5: Video Assembly"):
            import random
            
            ass_path = run_dir / "subtitles.ass"
            subtitles.generate_ass_file(voice_results, ass_path)
            
            # Select random BGM track from the premium folder
            bgm_dir = Path("assets/bgm")
            bgm_path = None
            if bgm_dir.exists():
                tracks = [
                    track for track in bgm_dir.glob("*.mp3")
                    if track.stat().st_size >= settings.BGM_MIN_BYTES
                ]
                if tracks:
                    bgm_path = random.choice(tracks)
                    log.info(f"Selected BGM track: {bgm_path.name}")
            
            final_video = assembler.assemble_video(
                voice_results=voice_results,
                visual_results=visual_results,
                ass_path=ass_path,
                run_dir=run_dir,
                bgm_path=bgm_path,
            )
            quality_gate.validate_rendered_video(final_video)

        # ── Phase 6: Post-Processing & Recording ──────────────────────────
        with PhaseTimer("Phase 6: Logging & Record keeping"):
            evaluator.record_topic(thesis)
            evaluator.record_title(script_dict["title"])
            evaluator.record_source_video(topic_data.get("video_id", ""))
            evaluator.record_source_id(topic_data.get("source_id", ""))
            log.info("Recorded topic to prevent future duplicates.")

        # ── Phase 6.5: SEO & Distribution Engineering ─────────────────────
        with PhaseTimer("Phase 6.5: SEO & Distribution Engineering"):
            from src.agents.distribution_seo_agent import DistributionSEOAgent
            seo_agent = DistributionSEOAgent()
            dist_pkg = seo_agent.generate_package(
                thesis=thesis,
                script_dict=script_dict,
                topic_data=topic_data,
            )
            log.info("✓ Multi-platform SEO Distribution Package generated successfully.")

        # ── Phase 7: Publishing ───────────────────────────────────────────
        with PhaseTimer("Phase 7: Publishing"):
            yt_url = None
            if settings.ENABLE_YT_UPLOAD:
                yt_id = youtube_uploader.upload_video(
                    video_path=final_video,
                    title=dist_pkg.youtube.title,
                    description=dist_pkg.get_youtube_description(),
                    hashtags=dist_pkg.youtube.hashtags,
                )
                if yt_id:
                    yt_url = f"https://www.youtube.com/shorts/{yt_id}"

            ig_url = None
            if settings.ENABLE_INSTAGRAM:
                ig_url = instagram_publisher.publish_reel(
                    video_path=final_video,
                    title=dist_pkg.instagram.first_line_hook,
                    description=f"{dist_pkg.instagram.body_copy}\n\n{dist_pkg.instagram.comment_trigger}\n\n{dist_pkg.instagram.share_save_cta}",
                    hashtags=dist_pkg.instagram.hashtags,
                )

            fb_url = None
            fb_page = getattr(settings, "FACEBOOK_PAGE_ID", "").strip() or getattr(settings, "FB_PAGE_ID", "").strip()
            if fb_page:
                fb_url = facebook_publisher.publish_reel(
                    video_path=final_video,
                    title=dist_pkg.facebook.story_hook,
                    description=f"{dist_pkg.facebook.narrative_body}\n\n{dist_pkg.facebook.discussion_question}",
                    hashtags=dist_pkg.facebook.topic_tags,
                )

        total_time = time.time() - total_start
if settings.ENABLE_TELEGRAM:
                telegram_notifier.send_completion_notification(
                    title=dist_pkg.youtube.title,
                    thesis=thesis,
                    youtube_url=yt_url,
                    instagram_url=ig_url,
                    facebook_url=fb_url,
                    video_path=final_video,
                    run_stats=stats,
                )
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
