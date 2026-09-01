"""Small, deterministic rules for the public YouTube title."""
from __future__ import annotations

import re


_SHORTS_TAG = re.compile(r"(?i)(?:^|\s)#shorts\b")


def normalize_youtube_title(title: str, max_length: int = 100) -> str:
    """Return a clean title with exactly one trailing ``#Shorts`` tag.

    The script model occasionally emits the tag itself and sometimes repeats it.
    Normalising at generation time *and* again at upload time makes the public
    title deterministic instead of trusting either caller.
    """
    suffix = " #Shorts"
    if max_length <= len(suffix):
        raise ValueError("max_length must leave room for the #Shorts suffix")

    text = _SHORTS_TAG.sub(" ", title or "")
    text = re.sub(r"\s+", " ", text).strip(" |-\t\n")
    if not text:
        raise ValueError("YouTube title cannot be empty")

    return f"{text[: max_length - len(suffix)].rstrip()}" + suffix
