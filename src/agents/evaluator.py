"""
src/agents/evaluator.py

Fuzzy-Match Deduplication Gate

Maintains a rolling buffer of used topics/titles in data/used_topics.json.
Before any topic enters the pipeline, it is checked against this buffer.
If similarity exceeds the configured threshold, the candidate is blocked.

Uses thefuzz.fuzz.token_sort_ratio for language-agnostic fuzzy matching.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from thefuzz import fuzz

from src.utils.config import settings
from src.utils.logger import get_logger
from src.utils.youtube_titles import normalize_youtube_title

log = get_logger(__name__, phase="dedup_gate")

_TOPICS_PATH = settings.DATA_DIR / "used_topics.json"
_SOURCE_PREFIX = "source_video:"
_SOURCE_ID_PREFIX = "source_id:"


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
    new_norm = _normalize_for_similarity(new_topic)

    for existing_topic in buffer:
        if existing_topic.startswith((_SOURCE_PREFIX, _SOURCE_ID_PREFIX)):
            continue
        existing_norm = _normalize_for_similarity(existing_topic)
        scores = [
            fuzz.token_sort_ratio(new_norm, existing_norm),
            fuzz.token_set_ratio(new_norm, existing_norm),
            fuzz.partial_ratio(new_norm, existing_norm),
        ]
        score = max(scores) / 100.0
        if score > best_score:
            best_score = score
            best_match = existing_topic

    return best_score, best_match


def _normalize_for_similarity(topic: str) -> str:
    """Canonicalize public titles/topics before fuzzy matching."""
    text = topic.lower().strip()
    text = re.sub(r"(?i)#shorts\b", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ──────────────────────────────────────────────────────────────────────────────
#  Financial Concept Gate (Semantic Anti-Repetition)
# ──────────────────────────────────────────────────────────────────────────────

_FINANCIAL_CONCEPTS: dict[str, tuple[str, ...]] = {
    "expense_ratio": ("expense ratio", "regular plan", "direct plan", "mutual fund fee", "commission cut", "expense ratios", "fund fee"),
    "no_cost_emi": ("no cost emi", "no-cost emi", "zero cost emi", "subvention", "hidden interest emi"),
    "options_trading": ("f&o", "options trading", "expiry day", "call option", "put option", "sebi options"),
    "health_insurance": ("claim rejection", "waiting period", "room rent capping", "copay", "health insurance claim"),
    "credit_card": ("credit card charge", "minimum due", "revolving credit", "apr charge", "credit card fee", "credit card trap"),
    "fixed_deposit": ("fixed deposit tax", "fd inflation", "tds on fd", "real return fd"),
    "gold_loan": ("gold loan auction", "ltv ratio", "gold auction risk"),
    "cyber_banking_fraud": ("banking fraud", "fake otp", "sim swap", "digital arrest", "aeps fraud"),
    "p2p_lending": ("p2p lending", "peer to peer default", "rbi p2p rules"),
    "reits": ("reit dividend tax", "reit yield trap", "invit tax"),
    "ulip": ("ulip trap", "endowment policy", "insurance investment mix", "surrender value"),
    "epfo": ("epfo rejection", "pf withdrawal rules", "epf interest delay"),
    "personal_loan": ("personal loan trap", "flat interest rate vs reducing", "instant loan app"),
    "car_loan": ("balloon payment car loan", "7 year car loan", "car depreciation loan"),
    "atm_fees": ("atm transaction", "free atm", "atm fee", "atm charges"),
    "loan_guarantor": ("co-signing", "co-guarantor", "co-signer", "loan guarantor", "guarantor liability", "co signer", "co-borrower"),
    "cibil_credit_score": ("cibil", "credit score", "cibil drop", "cibil impact", "cibil score", "credit score drop"),
    "bnpl": ("bnpl", "buy now pay later", "pay later trap", "lazy pay", "simpl"),
    "real_estate_home_loan": ("home loan", "buying a house", "buying a home", "home buying", "builder trap", "property registration"),
    "retirement_pension": ("pension tax", "nps annuity", "retiree tax", "pension scheme tax", "retirement tax"),
}


def extract_concepts(text: str) -> set[str]:
    """Extract known core financial concepts from text."""
    t = text.lower()
    found = set()
    for concept, keywords in _FINANCIAL_CONCEPTS.items():
        if any(kw in t for kw in keywords):
            found.add(concept)
    return found


def is_concept_duplicate(topic: str, max_lookback_days: int = 14) -> tuple[bool, str]:
    """
    Checks if any core financial concept in `topic` was covered within the last max_lookback_days.
    Returns (is_duplicate: bool, matched_concept: str).
    """
    candidate_concepts = extract_concepts(topic)
    if not candidate_concepts:
        return False, ""

    buffer = _load_buffer()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_lookback_days)

    for past_topic, ts_str in buffer.items():
        if past_topic.startswith((_SOURCE_PREFIX, _SOURCE_ID_PREFIX)):
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts < cutoff:
                continue
        except (ValueError, TypeError):
            continue

        past_concepts = extract_concepts(past_topic)
        overlap = candidate_concepts.intersection(past_concepts)
        if overlap:
            matched_concept = sorted(list(overlap))[0]
            log.warning(
                "CONCEPT DUPLICATE BLOCKED — concept '%s' recently covered in '%s'",
                matched_concept, past_topic[:60]
            )
            return True, matched_concept

    return False, ""


# ──────────────────────────────────────────────────────────────────────────────
#  Public API
# ──────────────────────────────────────────────────────────────────────────────

def is_duplicate(topic: str, threshold: Optional[float] = None) -> tuple[bool, float, str]:
    """
    Check whether `topic` is too similar to a recently used topic or covers
    the same core financial concept within the 14-day anti-repetition window.

    Returns:
        (is_dup: bool, similarity_score: float, matched_topic: str)
    """
    # 1. Concept-level deduplication (catches differently-phrased repeats like Axis expense ratio vs general expense ratio)
    concept_dup, concept_name = is_concept_duplicate(topic, max_lookback_days=10)
    if concept_dup:
        return True, 0.99, f"Concept '{concept_name}' already covered within 10 days"

    # 2. Fuzzy text similarity
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


def is_source_video_used(video_id: str) -> bool:
    """Return True when a source YouTube video has already fed a completed run."""
    if not video_id:
        return False
    buffer = _evict_old_entries(_load_buffer())
    marker = f"{_SOURCE_PREFIX}{video_id}"
    used = marker in buffer
    _save_buffer(buffer)
    if used:
        log.info("Source video already used: %s", video_id)
    return used


def is_source_id_used(source_id: str) -> bool:
    """Return True when an exact source identity has already fed a completed run."""
    if not source_id:
        return False
    buffer = _evict_old_entries(_load_buffer())
    marker = f"{_SOURCE_ID_PREFIX}{source_id}"
    used = marker in buffer
    _save_buffer(buffer)
    if used:
        log.info("Source ID already used: %s", source_id)
    return used


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


def record_title(title: str) -> None:
    """Record the final public-facing YouTube title after normalization."""
    record_topic(normalize_youtube_title(title))


def record_source_video(video_id: str) -> None:
    """Record a source YouTube video ID after a completed production run."""
    if video_id:
        record_topic(f"{_SOURCE_PREFIX}{video_id}")


def record_source_id(source_id: str) -> None:
    """Record a canonical source identity after a completed production run."""
    if source_id:
        record_topic(f"{_SOURCE_ID_PREFIX}{source_id}")


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
