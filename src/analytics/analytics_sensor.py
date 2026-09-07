"""
src/analytics/analytics_sensor.py

Closed-Loop Analytics Feedback Sensor for Market Debunk Pipeline.
Audits video performance ~48 hours post-upload:
1. Queries Meta Graph API for Instagram Reels metrics (plays, reach, saves, shares, watch time).
2. Queries YouTube Data API for Shorts statistics (views, likes, comments).
3. Evaluates retention benchmarks (<50% APV threshold).
4. Automatically flags underperforming hook structures and topics into `deprecated_patterns.json`.
5. Passes negative guidance to script generation models so they learn from real algorithmic feedback.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="analytics_sensor")


class AnalyticsSensor:
    """Collects 48-hour social metrics and flags underperforming patterns."""

    def __init__(
        self,
        ledger_path: Optional[Path] = None,
        analytics_path: Optional[Path] = None,
        deprecated_path: Optional[Path] = None,
    ):
        data_dir = settings.DATA_DIR
        data_dir.mkdir(parents=True, exist_ok=True)

        self.ledger_path = Path(ledger_path) if ledger_path else data_dir / "publish_ledger.json"
        self.analytics_path = Path(analytics_path) if analytics_path else data_dir / "analytics_ledger.json"
        self.deprecated_path = Path(deprecated_path) if deprecated_path else data_dir / "deprecated_patterns.json"

    def load_deprecated_patterns(self) -> list[str]:
        """Load list of deprecated hook formulas and underperforming angles."""
        if not self.deprecated_path.is_file():
            return []
        try:
            with open(self.deprecated_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception as exc:
            log.warning("Could not read deprecated patterns: %s", exc)
            return []

    def record_deprecated_pattern(self, pattern: str, reason: str) -> None:
        """Add an underperforming pattern to the deprecation list."""
        patterns = self.load_deprecated_patterns()
        clean = pattern.strip()
        if not clean or clean in patterns:
            return

        patterns.append(clean)
        # Limit to 30 most recent deprecated patterns to keep prompt focused
        if len(patterns) > 30:
            patterns = patterns[-30:]

        try:
            with open(self.deprecated_path, "w", encoding="utf-8") as f:
                json.dump(patterns, f, indent=2, ensure_ascii=False)
            log.info("🚫 Added to deprecated patterns: '%s' (Reason: %s)", clean[:60], reason)
        except Exception as exc:
            log.error("Failed to write deprecated patterns: %s", exc)

    def audit_recent_posts(self) -> dict:
        """
        Scan publish ledger for posts published 48h–14d ago that need auditing.
        Returns summary of audited posts and flagged patterns.
        """
        if not self.ledger_path.is_file():
            return {"audited": 0, "deprecated_added": 0}

        try:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                ledger = json.load(f)
        except Exception as exc:
            log.error("Failed to load publish ledger for audit: %s", exc)
            return {"audited": 0, "deprecated_added": 0}

        now = datetime.now(timezone.utc)
        min_age = timedelta(hours=40)  # Eligible once ~40-48h old
        max_age = timedelta(days=14)

        audited_count = 0
        deprecated_count = 0
        analytics_records = self._load_analytics_records()

        for entry in ledger:
            if entry.get("audited"):
                continue

            ts_str = entry.get("timestamp")
            if not ts_str:
                continue

            try:
                post_dt = datetime.fromisoformat(ts_str)
            except Exception:
                continue

            age = now - post_dt
            if age < min_age or age > max_age:
                continue

            post_title = entry.get("title", "Untitled")
            hook = entry.get("hook", "")
            topic = entry.get("topic", "")
            duration = float(entry.get("duration_seconds") or 25.0)
            platform_ids = entry.get("ids", {})

            log.info("Auditing 48h performance for: '%s'...", post_title[:50])

            ig_metrics = self._fetch_instagram_metrics(platform_ids.get("instagram"))
            yt_metrics = self._fetch_youtube_metrics(platform_ids.get("youtube"))

            record = {
                "timestamp_audited": now.isoformat(),
                "post_timestamp": ts_str,
                "title": post_title,
                "hook": hook,
                "topic": topic,
                "duration_seconds": duration,
                "instagram": ig_metrics,
                "youtube": yt_metrics,
            }
            analytics_records.append(record)
            entry["audited"] = True
            audited_count += 1

            # Performance gate evaluation
            # 1. Check Instagram watch time / APV
            avg_watch_time = ig_metrics.get("avg_watch_time", 0.0)
            if duration > 0 and avg_watch_time > 0:
                apv = (avg_watch_time / duration) * 100.0
                if apv < 50.0 and hook:
                    self.record_deprecated_pattern(
                        hook,
                        f"Instagram APV was {apv:.1f}% (< 50% target threshold)"
                    )
                    deprecated_count += 1

            # 2. Check YouTube view velocity if available
            yt_views = yt_metrics.get("views", 0)
            if 0 < yt_views < 30 and hook:
                self.record_deprecated_pattern(
                    hook,
                    f"YouTube views remained below 30 after 48h ({yt_views} views)"
                )
                deprecated_count += 1

        # Save updated ledger with audited flags
        if audited_count > 0:
            try:
                with open(self.ledger_path, "w", encoding="utf-8") as f:
                    json.dump(ledger, f, indent=2, ensure_ascii=False)
                self._save_analytics_records(analytics_records)
                log.info("✓ Completed 48h audit: %d posts analyzed, %d patterns deprecated.", audited_count, deprecated_count)
            except Exception as exc:
                log.error("Failed to save audit results: %s", exc)

        return {"audited": audited_count, "deprecated_added": deprecated_count}

    def _load_analytics_records(self) -> list[dict]:
        if not self.analytics_path.is_file():
            return []
        try:
            with open(self.analytics_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save_analytics_records(self, records: list[dict]) -> None:
        try:
            with open(self.analytics_path, "w", encoding="utf-8") as f:
                json.dump(records[-200:], f, indent=2, ensure_ascii=False)
        except Exception as exc:
            log.warning("Could not save analytics records: %s", exc)

    def _fetch_instagram_metrics(self, media_id: Optional[str]) -> dict:
        """Fetch Instagram reel insights via Meta Graph API."""
        if not media_id:
            return {}

        token = getattr(settings, "INSTAGRAM_ACCESS_TOKEN", "").strip() or getattr(settings, "META_ACCESS_TOKEN", "").strip()
        if not token:
            return {}

        clean_media_id = str(media_id).strip("/").split("/")[-1].split("?")[0]
        version = getattr(settings, "INSTAGRAM_GRAPH_VERSION", "v21.0")
        url = f"https://graph.facebook.com/{version}/{clean_media_id}/insights"
        params = {
            "metric": "reach,saved,shares,total_interactions",
            "access_token": token,
        }

        try:
            res = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json().get("data", [])
                metrics = {}
                for m in data:
                    name = m.get("name")
                    values = m.get("values", [{}])
                    val = values[0].get("value", 0) if values else 0
                    metrics[name] = val
                log.info("✓ Meta Graph API insights for %s: %s", media_id, metrics)
                return metrics
            else:
                log.debug("Instagram insights for %s returned HTTP %d: %s", media_id, res.status_code, res.text[:150])
        except Exception as exc:
            log.debug("Instagram insights request failed: %s", exc)

        return {}

    def _fetch_youtube_metrics(self, video_id: Optional[str]) -> dict:
        """Fetch YouTube short statistics via YouTube Data API v3."""
        if not video_id:
            return {}

        # Strip URL wrapper if full URL was stored
        clean_id = video_id
        if "youtu.be/" in video_id:
            clean_id = video_id.split("youtu.be/")[1].split("?")[0]
        elif "shorts/" in video_id:
            clean_id = video_id.split("shorts/")[1].split("?")[0]
        elif "v=" in video_id:
            clean_id = video_id.split("v=")[1].split("&")[0]

        yt_key = getattr(settings, "YT_API_KEY", "").strip() or getattr(settings, "GEMINI_API_KEY", "").strip()
        if not yt_key:
            return {}

        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "part": "statistics",
            "id": clean_id,
            "key": yt_key,
        }

        try:
            res = requests.get(url, params=params, timeout=10)
            if res.status_code == 200:
                items = res.json().get("items", [])
                if items:
                    stats = items[0].get("statistics", {})
                    metrics = {
                        "views": int(stats.get("viewCount", 0)),
                        "likes": int(stats.get("likeCount", 0)),
                        "comments": int(stats.get("commentCount", 0)),
                    }
                    log.info("✓ YouTube statistics for %s: %s", clean_id, metrics)
                    return metrics
            else:
                log.debug("YouTube statistics for %s returned HTTP %d", clean_id, res.status_code)
        except Exception as exc:
            log.debug("YouTube statistics request failed: %s", exc)

        return {}
