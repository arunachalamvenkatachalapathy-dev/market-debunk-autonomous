"""High-reach keyword rules and clean title formatting for YouTube Shorts."""
from __future__ import annotations

import re
from typing import Optional

_SHORTS_TAG = re.compile(r"(?i)(?:^|\s)#shorts\b")

# Curated High-Reach Keyword Taxonomy for Indian Finance & Share Market
_HIGH_REACH_KEYWORDS = [
    # Options & Derivatives
    (re.compile(r"\b(option|options|f&o|futures|derivative|call\s*put|trader\s*loss)\b", re.I), "Options Trading Loss"),
    (re.compile(r"\b(intraday|scalping|day\s*trad)\b", re.I), "Intraday Trading"),
    (re.compile(r"\b(stop\s*loss|algo\s*trad|bot\b|hunting)\b", re.I), "Stop Loss Hunting"),
    # Mutual Funds & SIP
    (re.compile(r"\b(direct|regular|expense\s*ratio|commission\s*drag)\b", re.I), "Mutual Fund SIP"),
    (re.compile(r"\b(mutual\s*fund|sip\b|index\s*fund|etf\b)\b", re.I), "Mutual Fund SIP"),
    # Stocks & IPO
    (re.compile(r"\b(ipo|sme\s*ipo|grey\s*market|gmp\b|allotment)\b", re.I), "SME IPO Allotment"),
    (re.compile(r"\b(dividend|yield\s*trap)\b", re.I), "Dividend Stocks Trap"),
    (re.compile(r"\b(penny\s*stock|multibagger|pump\s*and\s*dump|smallcap)\b", re.I), "Penny Stocks Trap"),
    (re.compile(r"\b(nifty|sensex|benchmark|stock\s*market|share\s*market)\b", re.I), "Stock Market Beginners"),
    # Consumer Banking & Loans
    (re.compile(r"\b(emi\b|no\s*cost|zero\s*cost)\b", re.I), "Zero Cost EMI Trap"),
    (re.compile(r"\b(cibil|credit\s*score|credit\s*card|minimum\s*due)\b", re.I), "Credit Card Trap"),
    (re.compile(r"\b(fd\b|fixed\s*deposit|savings\s*account|bank\s*charge|atm\b)\b", re.I), "Fixed Deposit (FD)"),
    (re.compile(r"\b(insurance|room\s*rent|mediclaim|health\s*claim)\b", re.I), "Health Insurance Claim"),
    (re.compile(r"\b(tax\b|ltcg|stcg|itr\b|80c\b)\b", re.I), "Income Tax LTCG"),
    (re.compile(r"\b(personal\s*loan|car\s*loan|guarantor|bnpl)\b", re.I), "Personal Loan Trap"),
    (re.compile(r"\b(gold\s*loan|pawn|jewel\s*loan)\b", re.I), "Gold Loan Trap"),
]


def clean_word_truncate(text: str, max_chars: int) -> str:
    """Truncate text cleanly at word boundaries without cutting words in half."""
    text = re.sub(r"\s+", " ", text).strip(" |-\t\n:;,")
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    if " " in truncated:
        truncated = truncated.rsplit(" ", 1)[0]
    return truncated.strip(" |-\t\n:;,")


def resolve_high_reach_keyword(text: str, default_domain: Optional[str] = None) -> str:
    """Resolve the highest-volume search keyword entity matching the text by earliest position."""
    best_match = None
    earliest_pos = float("inf")

    for pattern, keyword in _HIGH_REACH_KEYWORDS:
        m = pattern.search(text)
        if m and m.start() < earliest_pos:
            earliest_pos = m.start()
            best_match = keyword

    if best_match:
        return best_match

    if default_domain and "CONSUMER" in default_domain.upper():
        return "Personal Finance Trap"
    return "Stock Market Beginners"


def format_high_reach_title(keyword: str, angle: str, max_length: int = 55) -> str:
    """Format a YouTube Shorts title front-loading the keyword with clean length clamping.

    Example: 'Options Trading Loss: SEBI 90% Reality #Shorts'
    """
    suffix = " #Shorts"
    clean_kw = keyword.strip(" :|-")
    clean_ang = angle.strip(" :|-")

    # If angle already starts with the keyword, strip it to avoid duplication
    if clean_ang.lower().startswith(clean_kw.lower()):
        clean_ang = clean_ang[len(clean_kw):].strip(" :|-")

    prefix = f"{clean_kw}: "
    budget = max_length - len(suffix) - len(prefix)

    if budget < 10:
        # Fallback if keyword is very long
        budget = max_length - len(suffix)
        return f"{clean_word_truncate(clean_ang, budget)}{suffix}"

    shortened_angle = clean_word_truncate(clean_ang, budget)
    if not shortened_angle:
        shortened_angle = "The Real Math"

    return f"{prefix}{shortened_angle}{suffix}"


def normalize_youtube_title(title: str, max_length: int = 58) -> str:
    """Return a clean title with word-boundary truncation and exactly one '#Shorts' tag.

    Ensures no words are cut in half (e.g. prevents 'The Hidden Trut').
    """
    suffix = " #Shorts"
    if max_length <= len(suffix):
        raise ValueError("max_length must leave room for the #Shorts suffix")

    text = _SHORTS_TAG.sub(" ", title or "")
    text = re.sub(r"\s+", " ", text).strip(" |-\t\n:;,")
    if not text:
        raise ValueError("YouTube title cannot be empty")

    budget = max_length - len(suffix)
    clean_text = clean_word_truncate(text, budget)
    return f"{clean_text}{suffix}"
