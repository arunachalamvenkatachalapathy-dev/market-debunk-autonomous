"""
Feedback Intelligence & Algorithmic Finetuning Agent for Market Debunk Autonomous Video
Ingests 48-hour analytics and closed-loop directives from the analytics ledger
to continuously improve hook retention, mathematical pacing, and algorithmic distribution in subsequent video scripts.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="feedback_intelligence")


class FeedbackIntelligenceAgent:
    """
    Dedicated agent to enforce closed-loop algorithmic finetuning on video scripts.
    Pulls 48h analytics findings and injects proven winning hook structures into ScriptAgent.
    """

    def __init__(self, state_dir: Optional[Path] = None):
        self.state_dir = state_dir or (Path(__file__).resolve().parent.parent.parent / "state")
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.directive_file = self.state_dir / "loop_finetuning_directive.json"

    def get_video_finetuning_prompt_injection(self) -> str:
        """
        Returns dynamic prompt injection instructions synthesized from 48h analytics.
        Enforces:
        1. Winning hook angle in Scene 1 (0:00 - 0:03).
        2. Mathematical/numerical friction in Scene 2-4 (0:04 - 0:12) to force replay dwell.
        3. Deprecation of generic explanatory news summaries.
        """
        directive = self._load_directive()
        if directive:
            v_dir = directive.get("video_finetuning_directive", {})
            hook_mandate = v_dir.get("opening_3s_hook", "Direct contrarian statement with numerical anchor.")
            pacing = v_dir.get("pacing_calibration", "Introduce hard mathematical friction between seconds 4 and 10.")
            cta = v_dir.get("retention_cta", "Direct viewers to save this checklist for their next trade.")
            avg_save = directive.get("historical_avg_save_rate_pct", 2.5)

            return (
                f"\n\n═══════════════════════════════════════════════════════════════════════════\n"
                f"🎯 CLOSED-LOOP ALGORITHMIC FINETUNING DIRECTIVE (48H REINFORCEMENT - SAVE RATE {avg_save}%):\n"
                f"1. SCENE 1 (0-3 SEC HOOK MANDATE): {hook_mandate}\n"
                f"2. SCENE 2-4 (RETENTION PACING): {pacing}\n"
                f"3. FINAL SCENE (RETENTION CTA): {cta}\n"
                f"4. BANNED: Do NOT give generic textbook summaries. Only focus on what smart money / institutions do vs retail traps.\n"
                f"═══════════════════════════════════════════════════════════════════════════\n"
            )

        return (
            "\n\n═══════════════════════════════════════════════════════════════════════════\n"
            "🎯 CLOSED-LOOP ALGORITHMIC FINETUNING DIRECTIVE:\n"
            "1. SCENE 1 HOOK: Open with an immediate contrarian contrast with a specific number. Avoid greetings.\n"
            "2. RETENTION PACING: Inject mathematical friction in seconds 4-10 to force replay dwell.\n"
            "3. FINAL SCENE: Mandate saving the video as a checklist before trading.\n"
            "═══════════════════════════════════════════════════════════════════════════\n"
        )

    def _load_directive(self) -> Optional[Dict[str, Any]]:
        if self.directive_file.exists():
            try:
                with open(self.directive_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                log.warning("Could not read loop finetuning directive: %s", e)
        return None
