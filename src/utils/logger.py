"""
src/utils/logger.py
Structured JSON logger optimised for GitHub Actions output.
Each log line is a self-contained JSON object for easy log parsing.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "phase": getattr(record, "phase", "pipeline"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def get_logger(name: str, phase: str = "pipeline") -> logging.Logger:
    """
    Return a logger with JSON formatting wired to stdout.

    Usage:
        log = get_logger(__name__, phase="topic_discovery")
        log.info("Found topic: %s", topic)
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # Inject phase into every record
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):
        record = old_factory(*args, **kwargs)
        record.phase = phase
        return record

    logging.setLogRecordFactory(record_factory)
    return logger


class PhaseTimer:
    """Context manager that logs the wall-clock time of a pipeline phase."""

    def __init__(self, phase_name: str, logger: logging.Logger) -> None:
        self.phase_name = phase_name
        self.logger = logger
        self._start: float = 0.0

    def __enter__(self) -> "PhaseTimer":
        self._start = time.perf_counter()
        self.logger.info("▶ Starting phase: %s", self.phase_name)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        elapsed = time.perf_counter() - self._start
        if exc_type:
            self.logger.error(
                "✗ Phase FAILED: %s  (%.1fs)", self.phase_name, elapsed
            )
        else:
            self.logger.info(
                "✓ Phase complete: %s  (%.1fs)", self.phase_name, elapsed
            )
        return False  # don't suppress exceptions
