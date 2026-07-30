"""
Manager Agent — 8-phase pipeline orchestrator.
Every phase follows: PE generates → Evaluator gates → retry or advance.
"""
import logging
import hashlib
import os
from google import genai

from src.agents.prompt_engineer import PromptEngineerAgent
from src.agents.evaluator import EvaluatorAgent
from src.agents.evaluator_report import EvaluatorReport
from src.agents.inspector import InspectorAgent
from src.generator import get_secret, run_synthesis_pipeline
from src.video_processor import assemble_final_video
from src.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

MAX_RETRIES = 3


class ManagerAgent:
    """
    The central orchestrator — runs an 8-phase pipeline where every phase
    has Prompt Engineer AI generation followed by Evaluator quality gates.
    """

    def __init__(self):
        # Support a comma-separated list of keys for rate-limit rotation
        api_keys_str = os.environ.get("LLM_API_KEYS") or get_secret("LLM_API_KEYS")
        
        if api_keys_str:
            api_keys = [k.strip() for k in api_keys_str.split(",") if k.strip()]
        else:
            api_key = os.environ.get("LLM_API_KEY") or get_secret("LLM_API_KEY")
            api_keys = [api_key] if api_key else []

        if not api_keys:
            logger.warning("No LLM_API_KEYS or LLM_API_KEY found.")
            
        self.gemini_clients = [genai.Client(api_key=k) for k in api_keys]
        self.prompt_engineer = PromptEngineerAgent(self.gemini_clients)
        self.evaluator = EvaluatorAgent()
        self.inspector = InspectorAgent(self.gemini_clients[0] if self.gemini_clients else None)
        self.report = None

    def _run_phase(self, phase_name, generate_fn, gate_fn, max_retries=MAX_RETRIES):
        """
        Generic phase runner:
        1. Call generate_fn() to produce output
        2. Call gate_fn(output) to validate
        3. Retry on failure, abort after max_retries
        Returns (output, passed) tuple.
        """
        for attempt in range(1, max_retries + 1):
            logger.info(f"{'='*60}")
            logger.info(f"  PHASE: {phase_name} — Attempt {attempt}/{max_retries}")
            logger.info(f"{'='*60}")

            try:
                output = generate_fn()
                passed, reason, details = gate_fn(output)

                self.report.record_gate(phase_name, passed, reason, details)

                if passed:
                    logger.info(f"✅ {phase_name} PASSED — {reason}")
                    return output, True
                else:
                    logger.warning(f"❌ {phase_name} FAILED — {reason}. Retrying...")
            except Exception as e:
                logger.error(f"💥 {phase_name} CRASHED — {e}")
                self.report.record_gate(phase_name, False, f"Exception: {e}", {})

        logger.error(f"🚫 {phase_name} exhausted all {max_retries} retries. ABORTING.")
        return None, False

    def execute_workflow(self, publish_youtube=True, publish_telegram=True, override_topic=None):
        """
        The main 8-phase orchestration pipeline.
        Every section has PE generation + Evaluator gate.
        """
        logger.info("🚀 MANAGER AGENT: Starting daily generation workflow.")
        logger.info("=" * 60)
        self.report = EvaluatorReport()

        # ─────────────────────────────────────────
        #  PHASE 1: TOPIC DISCOVERY
        # ─────────────────────────────────────────
        topic, passed = self._run_phase(
            phase_name="topic",
            generate_fn=lambda: override_topic if override_topic else self.prompt_engineer.fetch_fresh_topic(),
            gate_fn=lambda t: self.evaluator.gate_topic(t)
        )
        if not passed:
            self._abort("Topic Discovery")
            return False

        self.report.topic = topic
        logger.info(f"📌 Topic: {topic[:80]}...")

        # ─────────────────────────────────────────
        #  PHASE 2: SCRIPT GENERATION
        # ─────────────────────────────────────────
        script, passed = self._run_phase(
            phase_name="script",
            generate_fn=lambda: self.prompt_engineer.generate_script(topic),
            gate_fn=lambda s: self.evaluator.gate_script(s)
        )
        if not passed:
            self._abort("Script Generation")
            return False

        logger.info(f"📝 Script: '{script.get('title', 'untitled')}'")

        # ─────────────────────────────────────────
        #  PHASE 3: VOICE ENGINEERING
        # ─────────────────────────────────────────
        voice_config, passed = self._run_phase(
            phase_name="voice_engineering",
            generate_fn=lambda: self.prompt_engineer.engineer_voice_config(script),
            gate_fn=lambda vc: self._gate_voice_config(vc, len(script.get('scenes', [])))
        )
        if not passed:
            logger.warning("⚠️ Voice engineering failed — using default voice config")
            voice_config = None
            self.report.record_gate("voice_engineering", True, "Falling back to defaults", {"fallback": True})

        # ─────────────────────────────────────────
        #  PHASE 4: VISUAL ENGINEERING
        # ─────────────────────────────────────────
        visual_config, passed = self._run_phase(
            phase_name="visual_engineering",
            generate_fn=lambda: self.prompt_engineer.engineer_visual_prompts(script),
            gate_fn=lambda vc: self._gate_visual_config(vc, len(script.get('scenes', [])))
        )
        if not passed:
            logger.warning("⚠️ Visual engineering failed — using default visual prompts")
            visual_config = None
            self.report.record_gate("visual_engineering", True, "Falling back to defaults", {"fallback": True})

        # ─────────────────────────────────────────
        #  PHASE 5: SYNTHESIS (Voice + Visuals Generation)
        # ─────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("  PHASE: SYNTHESIS — Generating voice + visual assets")
        logger.info("=" * 60)

        try:
            processed_scenes = run_synthesis_pipeline(
                script_data=script,
                voice_config=voice_config,
                visual_config=visual_config
            )
        except Exception as e:
            logger.error(f"💥 Synthesis crashed: {e}")
            self.report.record_gate("synthesis", False, f"Crashed: {e}", {})
            self._abort("Synthesis")
            return False

        # Gate: Voice output
        audio_paths = [s["audio_path"] for s in processed_scenes]
        word_timings_list = [s["word_timings"] for s in processed_scenes]
        v_passed, v_reason, v_details = self.evaluator.gate_voice(
            audio_paths, word_timings_list, voice_config
        )
        self.report.record_gate("voice", v_passed, v_reason, v_details)
        if not v_passed:
            self._abort("Voice Quality Gate")
            return False

        # Gate: Visual output
        image_paths = [
            s["visual_asset"]["path"] for s in processed_scenes
            if s["visual_asset"]["type"] in ("image", "video")
        ]
        vis_passed, vis_reason, vis_details = self.evaluator.gate_visuals(
            image_paths, visual_config
        )
        self.report.record_gate("visuals", vis_passed, vis_reason, vis_details)
        if not vis_passed:
            self._abort("Visual Quality Gate")
            return False

        # ─────────────────────────────────────────
        #  PHASE 6: MASCOT TIMELINE ENGINEERING
        # ─────────────────────────────────────────
        mascot_timeline, passed = self._run_phase(
            phase_name="mascot",
            generate_fn=lambda: self.prompt_engineer.engineer_mascot_timeline(script),
            gate_fn=lambda mt: self.evaluator.gate_mascot(mt, script)
        )
        if not passed:
            logger.warning("⚠️ Mascot engineering failed — using script arrow_states directly")
            mascot_timeline = None
            self.report.record_gate("mascot", True, "Falling back to script states", {"fallback": True})

        # ─────────────────────────────────────────
        #  PHASE 7: SUBTITLE + ASSEMBLY ENGINEERING
        # ─────────────────────────────────────────
        subtitle_style, _ = self._run_phase(
            phase_name="subtitle_style",
            generate_fn=lambda: self.prompt_engineer.engineer_subtitle_style(script),
            gate_fn=lambda ss: self._gate_subtitle_style(ss),
            max_retries=2
        )
        if subtitle_style is None:
            subtitle_style = None  # Will use defaults in video_processor

        assembly_config, _ = self._run_phase(
            phase_name="assembly_config",
            generate_fn=lambda: self.prompt_engineer.engineer_assembly_config(script, processed_scenes),
            gate_fn=lambda ac: self._gate_assembly_config(ac),
            max_retries=2
        )
        if assembly_config is None:
            assembly_config = None  # Will use defaults

        # ─────────────────────────────────────────
        #  PHASE 8: FINAL ASSEMBLY
        # ─────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("  PHASE: FINAL ASSEMBLY — FFmpeg render")
        logger.info("=" * 60)

        try:
            final_video_path, total_audio_dur = assemble_final_video(
                processed_scenes,
                subtitle_style=subtitle_style,
                assembly_config=assembly_config,
                mascot_timeline=mascot_timeline
            )
        except Exception as e:
            logger.error(f"💥 Assembly crashed: {e}")
            self.report.record_gate("assembly", False, f"Crashed: {e}", {})
            self._abort("Assembly")
            return False

        # Gate: Assembly output
        asm_passed, asm_reason, asm_details = self.evaluator.gate_assembly(
            final_video_path, expected_audio_duration=total_audio_dur
        )
        self.report.record_gate("assembly", asm_passed, asm_reason, asm_details)
        if not asm_passed:
            self._abort("Assembly Quality Gate")
            return False

        # Gate: Subtitles (soft gate — check the ASS file)
        sub_passed, sub_reason, sub_details = self.evaluator.gate_subtitles(
            os.path.join(OUTPUT_DIR, "subs.ass"), total_audio_dur, subtitle_style
        )
        self.report.record_gate("subtitles", sub_passed, sub_reason, sub_details)
        # Soft gate — don't abort on failure

        # ─────────────────────────────────────────
        #  PHASE 8b: VISUAL INSPECTION
        # ─────────────────────────────────────────
        logger.info("=" * 60)
        logger.info("  PHASE: VISUAL INSPECTION — Verifying layout orientation")
        logger.info("=" * 60)
        
        inspection_result = self.inspector.inspect_layout(final_video_path)
        insp_passed, insp_reason, insp_details = self.evaluator.gate_inspector(inspection_result)
        self.report.record_gate("inspector", insp_passed, insp_reason, insp_details)
        if not insp_passed:
            self._abort("Visual Inspection Gate")
            return False

        # ─────────────────────────────────────────
        #  PHASE 9: PUBLISH METADATA + DISTRIBUTION
        # ─────────────────────────────────────────
        publish_metadata, passed = self._run_phase(
            phase_name="publish_metadata",
            generate_fn=lambda: self.prompt_engineer.engineer_publish_metadata(script, topic),
            gate_fn=lambda pm: self.evaluator.gate_publish_metadata(pm),
            max_retries=2
        )

        if not publish_metadata:
            # Fallback metadata
            publish_metadata = {
                "youtube_titles": [f"{script.get('title', topic)[:47]} #Shorts"],
                "youtube_description": script.get("description", topic),
                "youtube_tags": ["shorts", "finance", "market", "myth", "India"],
                "telegram_caption": f"🔥 {script.get('title', topic)} #MarketDebunk",
                "instagram_description": script.get("description", topic),
                "category_id": "27"
            }

        # Publish
        if publish_youtube or publish_telegram:
            logger.info("📢 PUBLISHING...")
            try:
                from src.publisher import publish_video
                title = publish_metadata.get("youtube_titles", [topic])[0]
                youtube_description = publish_metadata.get("youtube_description", "")
                youtube_tags = publish_metadata.get("youtube_tags", [])
                telegram_caption = publish_metadata.get("telegram_caption", "")
                category_id = publish_metadata.get("category_id", "27")
                
                publish_results = publish_video(
                    video_path=final_video_path,
                    title=title,
                    youtube_description=youtube_description,
                    youtube_tags=youtube_tags,
                    telegram_caption=telegram_caption,
                    category_id=category_id,
                    publish_youtube=publish_youtube,
                    publish_telegram=publish_telegram
                )
                logger.info(f"📢 Publish results: {publish_results}")
                yt_res = publish_results.get("youtube", {})
                tg_res = publish_results.get("telegram", {})
                self.report.record_gate("publish_youtube", yt_res.get("success", False), f"YouTube: {yt_res}", yt_res)
                self.report.record_gate("publish_telegram", tg_res.get("success", False), f"Telegram: {tg_res}", tg_res)
            except Exception as e:
                logger.error(f"📢 Publishing failed: {e}")
                self.report.record_gate("publishing", False, f"Exception: {e}", {})

        # ─────────────────────────────────────────
        #  FINAL REPORT
        # ─────────────────────────────────────────
        self.report.print_summary()
        self.report.write_to_file()

        logger.info("🏁 MANAGER AGENT: Workflow complete!")
        return True

    def _abort(self, phase_name):
        """Abort pipeline and write partial report."""
        logger.error(f"🛑 PIPELINE ABORTED at phase: {phase_name}")
        if self.report:
            self.report.print_summary()
            self.report.write_to_file()

    # ─────────────────────────────────────────
    #  INLINE CONFIG GATES (light validation for PE config outputs)
    # ─────────────────────────────────────────

    def _gate_voice_config(self, voice_config, expected_count):
        """Light gate for voice engineering output."""
        if not voice_config:
            return False, "Voice config is None", {}
        scenes = voice_config.get("scenes", [])
        if len(scenes) != expected_count:
            return False, f"Expected {expected_count} scene voice configs, got {len(scenes)}", {"count": len(scenes)}
        for s in scenes:
            if not s.get("ssml_text"):
                return False, f"Scene {s.get('scene_number')} missing SSML text", {}
        return True, "Voice config valid", {"scene_count": len(scenes)}

    def _gate_visual_config(self, visual_config, expected_count):
        """Light gate for visual engineering output."""
        if not visual_config:
            return False, "Visual config is None", {}
        scenes = visual_config.get("scenes", [])
        if len(scenes) != expected_count:
            return False, f"Expected {expected_count} scene visual configs, got {len(scenes)}", {"count": len(scenes)}
        for s in scenes:
            if not s.get("enhanced_prompt"):
                return False, f"Scene {s.get('scene_number')} missing enhanced prompt", {}
        # Check category rotation
        categories = [s.get("category_tag", "") for s in scenes]
        for i in range(1, len(categories)):
            if categories[i] == categories[i-1]:
                return False, f"Adjacent category repeat: {categories[i]}", {"categories": categories}
        return True, "Visual config valid", {"categories": categories}

    def _gate_subtitle_style(self, subtitle_style):
        """Light gate for subtitle style output."""
        if not subtitle_style:
            return False, "Subtitle style is None", {}
        margin_v = subtitle_style.get("margin_v", 0)
        if margin_v < 350 or margin_v > 600:
            return False, f"MarginV {margin_v} outside safe zone (350-600)", {"margin_v": margin_v}
        font_size = subtitle_style.get("font_size", 0)
        if font_size < 60 or font_size > 120:
            return False, f"Font size {font_size} out of range (60-120)", {"font_size": font_size}
        return True, "Subtitle style valid", {"margin_v": margin_v, "font_size": font_size}

    def _gate_assembly_config(self, assembly_config):
        """Light gate for assembly config output."""
        if not assembly_config:
            return False, "Assembly config is None", {}
        lufs = assembly_config.get("loudness_target_i", 0)
        if lufs != -14:
            return False, f"Loudness target must be -14, got {lufs}", {"lufs": lufs}
        zoom = assembly_config.get("ken_burns_zoom_rate", 0)
        if zoom < 0.0001 or zoom > 0.002:
            return False, f"Zoom rate {zoom} out of range (0.0001-0.002)", {"zoom": zoom}
        return True, "Assembly config valid", {
            "lufs": lufs,
            "zoom": zoom,
            "fps": assembly_config.get("output_fps"),
            "logo_width": assembly_config.get("logo_scale_width")
        }
