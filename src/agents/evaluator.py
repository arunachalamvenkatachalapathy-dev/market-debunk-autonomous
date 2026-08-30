"""
src/agents/evaluator.py

Fuzzy-Match Deduplication Gate

Maintains a rolling 7-day buffer of used topics in data/used_topics.json.
Before any topic enters the pipeline, it is checked against this buffer.
If semantic similarity exceeds 0.75, the topic is blocked as a duplicate.

Uses thefuzz.fuzz.token_sort_ratio for language-agnostic fuzzy matching.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from thefuzz import fuzz

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="dedup_gate")

_TOPICS_PATH = settings.DATA_DIR / "used_topics.json"


# ──────────────────────────────────────────────────────────────────────────────
#  Buffer I/O
# ──────────────────────────────────────────────────────────────────────────────

def _load_buffer() -> dict[str, str]:
    """
    Returns dict of { topic_text → iso_timestamp }.
    """
    if not _TOPICS_PATH.exists():
        return {}
    with open(_TOPICS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Migrate old format (plain list) to new dict format
    if isinstance(data, list):
        return {}
    return data


def _save_buffer(buffer: dict[str, str]) -> None:
    _TOPICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_TOPICS_PATH, "w", encoding="utf-8") as f:
        json.dump(buffer, f, indent=2, ensure_ascii=False)


def _evict_old_entries(buffer: dict[str, str]) -> dict[str, str]:
    """Remove entries older than DEDUP_WINDOW_DAYS days."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.DEDUP_WINDOW_DAYS)
    cleaned = {}
    for topic, ts_str in buffer.items():
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                cleaned[topic] = ts_str
        except (ValueError, TypeError):
            pass  # drop malformed entries
    evicted = len(buffer) - len(cleaned)
    if evicted:
        log.info("Evicted %d expired topics from buffer", evicted)
    return cleaned


# ──────────────────────────────────────────────────────────────────────────────
#  Similarity Check
# ──────────────────────────────────────────────────────────────────────────────

def _max_similarity(new_topic: str, buffer: dict[str, str]) -> tuple[float, str]:
    """
    Returns (max_score, most_similar_topic_in_buffer).
    Score is in range [0.0, 1.0].
    """
    if not buffer:
        return 0.0, ""

    best_score = 0.0
    best_match = ""
    new_norm = new_topic.lower().strip()

    for existing_topic in buffer:
        existing_norm = existing_topic.lower().strip()
        # token_sort_ratio handles word-order variations gracefully
        score = fuzz.token_sort_ratio(new_norm, existing_norm) / 100.0
        if score > best_score:
            best_score = score
            best_match = existing_topic

    return best_score, best_match


# ──────────────────────────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────────────────────────

def is_duplicate(topic: str, threshold: Optional[float] = None) -> tuple[bool, float, str]:
    """
    Check whether `topic` is too similar to a recently used topic.

    Returns:
        (is_dup: bool, similarity_score: float, matched_topic: str)

    Example:
        is_dup, score, match = is_duplicate("Reliance Industries Q4 profit beat")
        if is_dup:
            print(f"Blocked! Matches '{match}' with score {score:.2f}")
    """
    thresh = threshold if threshold is not None else settings.DEDUP_THRESHOLD
    buffer = _load_buffer()
    buffer = _evict_old_entries(buffer)

    score, matched = _max_similarity(topic, buffer)
    is_dup = score >= thresh

    if is_dup:
        log.warning(
            "DUPLICATE BLOCKED — topic: '%s' | matched: '%s' | score: %.2f",
            topic, matched, score
        )
    else:
        log.info(
            "Topic CLEARED — '%s' | best_match_score: %.2f (threshold: %.2f)",
            topic, score, thresh
        )

    # Persist the evicted buffer (even if this topic is rejected)
    _save_buffer(buffer)

    return is_dup, score, matched


def record_topic(topic: str) -> None:
    """
    Add an approved topic to the used-topics buffer with the current timestamp.
    Call this AFTER the topic has been used for production (not just tested).
    """
    buffer = _load_buffer()
    buffer = _evict_old_entries(buffer)
    buffer[topic] = datetime.now(timezone.utc).isoformat()
    _save_buffer(buffer)
    log.info("Recorded topic to buffer: '%s' (%d in buffer)", topic, len(buffer))


def get_buffer_summary() -> dict:
    """Returns a human-readable summary of the current buffer state."""
    buffer = _load_buffer()
    buffer = _evict_old_entries(buffer)
    return {
        "total_topics": len(buffer),
        "window_days": settings.DEDUP_WINDOW_DAYS,
        "threshold": settings.DEDUP_THRESHOLD,
        "topics": list(buffer.keys()),
    }
