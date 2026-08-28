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
            
        def safe_get(key):
            try:
                return os.environ.get(key) or get_secret(key)
            except ValueError:
                return None
                
        groq_key = safe_get("GROQ_API_KEY")
        openrouter_key = safe_get("OPENROUTER_API_KEY")
        nvidia_key = safe_get("NVIDIA_API_KEY")
            
        self.gemini_clients = [genai.Client(api_key=k) for k in api_keys]
        self.prompt_engineer = PromptEngineerAgent(api_keys, openrouter_key, nvidia_key, groq_key)
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
        logger.info("MANAGER AGENT: Starting daily generation workflow (UNIFIED MODE).")
        self.report = EvaluatorReport()

        topic, passed = self._run_phase(
            phase_name="topic",
            generate_fn=lambda: override_topic if override_topic else self.prompt_engineer.fetch_fresh_topic(),
            gate_fn=lambda t: self.evaluator.gate_topic(t)
        )
        if not passed:
            self._abort("Topic Discovery")
            return False

        self.report.topic = topic
        logger.info(f"Topic: {topic[:80]}...")

        unified_json, passed = self._run_phase(
            phase_name="unified_engineering",
            generate_fn=lambda: self.prompt_engineer.generate_all(topic),
            gate_fn=lambda j: (True, "Passed JSON structure check", j) if isinstance(j, dict) and "script" in j else (False, "Missing script", None)
        )
        if not passed:
            self._abort("Unified LLM Engineering")
            return False
            
        script = unified_json.get("script", {})
        
        # Ensure voice_config and visual_config are lists
        v_conf = unified_json.get("voice_config", [])
        if isinstance(v_conf, dict):
            # If it returned a dict like {"scenes": [...]}, unwrap it
            if "scenes" in v_conf:
                v_conf = v_conf["scenes"]
            else:
                v_conf = [v_conf] * 8
        if not v_conf:
            v_conf = [{"type": "male"}] * 8
            
        vis_conf = unified_json.get("visual_config", [])
        if isinstance(vis_conf, dict):
            if "scenes" in vis_conf:
                vis_conf = vis_conf["scenes"]
            else:
                vis_conf = [vis_conf] * 8
        if not vis_conf:
            vis_conf = [{"prompt": "default"}] * 8
            
        subtitle_style = unified_json.get("subtitle_style", {})
        publish_metadata = unified_json.get("metadata", {})
        
        # Ensure at least one scene exists
        scenes = script.get("scenes", [])
        if not scenes:
            scenes = [{"scene_number": 0, "narration": "Fallback narration"}]
            script["scenes"] = scenes
            
        for i, s in enumerate(scenes):
            s["scene_number"] = i

        assets, passed = self._run_phase(
            phase_name="synthesis",
            generate_fn=lambda: run_synthesis_pipeline(script, vis_conf, v_conf),
            gate_fn=lambda a: (True, "Assets generated", a) if a else (False, "No assets", None)
        )
        if not passed:
            self._abort("Synthesis")
            return False

        logger.info("Assembling Final Video...")
        try:
            from src.video_processor import assemble_final_video
            final_video_path = assemble_final_video(assets, subtitle_style, None)
            self.report.record_gate("assembly", True, "Successfully assembled video", {"path": final_video_path})
            logger.info(f"Final video saved to: {final_video_path}")
        except Exception as e:
            logger.error(f"Assembly CRASHED - {e}")
            self._abort("Assembly")
            return False

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
        if margin_v < 100 or margin_v > 1500:
            return False, f"MarginV {margin_v} outside full-bleed safe zone (100-1500)", {"margin_v": margin_v}
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
