"""
src/timing/timing_guard.py

Timing Guard & Cooldown Engine for Market Debunk Pipeline.
Enforces the anti-bot directive:
1. Randomized Jitter: Injects a dynamic sleep (±14 to 28 minutes) so publication
   timestamps vary organically instead of posting at fixed clockwork intervals.
2. Mandatory Cooldown: Enforces a minimum 4 to 6-hour spacing between consecutive
   uploads to prevent feed self-cannibalization and spam-filter suppression.
"""
from __future__ import annotations

import json
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.utils.logger import get_logger

log = get_logger(__name__, phase="timing_guard")


class TimingGuard:
    """Manages upload timing, cooldown intervals, and anti-bot jitter."""

    def __init__(self, ledger_path: Optional[Path] = None):
        if ledger_path is None:
            from src.utils.config import settings
            self.ledger_path = settings.DATA_DIR / "publish_ledger.json"
        else:
            self.ledger_path = Path(ledger_path)

        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def load_ledger(self) -> list[dict]:
        """Load the publish history ledger."""
        if not self.ledger_path.is_file():
            return []
        try:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as exc:
            log.warning("Failed to read publish ledger: %s — starting fresh", exc)
            return []

    def record_publish(
        self,
        title: str,
        topic: str,
        platform_urls: dict[str, Optional[str]],
        platform_ids: dict[str, Optional[str]],
        hashtags: list[str],
        hook: str,
        duration_seconds: float = 0.0,
    ) -> None:
        """Record a successful video publication in the persistent ledger."""
        ledger = self.load_ledger()
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "topic": topic,
            "hook": hook,
            "hashtags": hashtags,
            "duration_seconds": duration_seconds,
            "urls": platform_urls,
            "ids": platform_ids,
            "audited": False,
        }
        ledger.append(entry)
        # Keep last 100 entries
        if len(ledger) > 100:
            ledger = ledger[-100:]

        try:
            with open(self.ledger_path, "w", encoding="utf-8") as f:
                json.dump(ledger, f, indent=2, ensure_ascii=False)
            log.info("✓ Recorded new publication to ledger (%s)", title[:50])
        except Exception as exc:
            log.error("Failed to update publish ledger: %s", exc)

    def check_cooldown(self, min_hours: float = 4.0) -> tuple[bool, float]:
        """
        Check if the mandatory cooldown window has passed since the last upload.
        Returns (can_proceed, hours_since_last_upload).
        """
        # Allow bypass via environment variable or manual workflow dispatch for testing
        if os.environ.get("IGNORE_COOLDOWN", "").lower() in ("true", "1", "yes") or os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
            log.info("Cooldown check bypassed (manual run or IGNORE_COOLDOWN=true)")
            return True, 999.0

        ledger = self.load_ledger()
        if not ledger:
            log.info("No prior uploads found in ledger — cooldown passed.")
            return True, 999.0

        last_entry = ledger[-1]
        last_ts_str = last_entry.get("timestamp")
        if not last_ts_str:
            return True, 999.0

        try:
            last_dt = datetime.fromisoformat(last_ts_str)
            now_dt = datetime.now(timezone.utc)
            hours_elapsed = (now_dt - last_dt).total_seconds() / 3600.0

            if hours_elapsed < min_hours:
                log.warning(
                    "⚠️ COOLDOWN VIOLATION: Last upload was only %.1f hours ago (minimum is %.1f hours). "
                    "Skipping upload to protect feed reach and avoid platform rate suppression.",
                    hours_elapsed,
                    min_hours,
                )
                return False, hours_elapsed

            log.info("✓ Cooldown satisfied: %.1f hours elapsed since last upload.", hours_elapsed)
            return True, hours_elapsed
        except Exception as exc:
            log.warning("Could not parse last timestamp '%s': %s — allowing run", last_ts_str, exc)
            return True, 999.0

    def apply_jitter(
        self,
        min_seconds: int = 5,
        max_seconds: int = 30,
        min_minutes: Optional[int] = None,
        max_minutes: Optional[int] = None,
    ) -> int:
        """
        Inject a minor randomized organic delay (5-30 seconds).
        Bypassed if RUN_WITHOUT_JITTER=true, workflow_dispatch (manual run), or local dev.
        Long waits (minutes) are strictly eliminated to prevent hung CI runs.
        """
        if os.environ.get("RUN_WITHOUT_JITTER", "").lower() in ("true", "1", "yes"):
            log.info("Jitter bypassed via RUN_WITHOUT_JITTER=true")
            return 0

        # Never wait on manual workflow runs
        if os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
            log.info("Manual workflow_dispatch detected — skipping jitter delay completely.")
            return 0

        # Don't jitter in local dev unless forced
        if not os.environ.get("GITHUB_ACTIONS"):
            log.info("Local environment detected — skipping jitter delay.")
            return 0

        # If legacy min_minutes/max_minutes were supplied, clamp to safe seconds (< 30s)
        if min_minutes is not None or max_minutes is not None:
            log.info("Legacy minute-based jitter clamped to safe seconds (5-30s max).")

        low = min(min_seconds, 15)
        high = min(max_seconds, 30)
        jitter_sec = random.randint(low, high)
        log.info(
            "⏳ Anti-Bot Jitter: sleeping for %d seconds to randomize post timestamp...",
            jitter_sec,
        )
        time.sleep(jitter_sec)
        log.info("✓ Jitter sleep completed. Resuming pipeline execution.")
        return jitter_sec
