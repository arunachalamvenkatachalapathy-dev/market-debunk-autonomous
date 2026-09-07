"""
src/agents/seo_subagents.py

3 Independent SEO Super Subagents for Market Debunk (English Channel).
Runs AFTER Gemini generates the base PlatformDistributionPackage.
Each subagent researches live data and enhances one platform's metadata:

  1. YouTubeSEOAgent  — search-intent tags, CTR-optimised title rewrites
  2. InstagramSEOAgent — trending niche hashtags, scroll-stopping first-line hook rewrites
  3. FacebookSEOAgent  — trending topic tags, relatable story-hook rewrites

RapidAPI key is used if subscribed endpoints are available.
Falls back gracefully to a curated 2026 Indian-finance niche hashtag research database.
"""
from __future__ import annotations

import json
import os
import re
import time
import random
import logging
from typing import Optional

import requests

log = logging.getLogger(__name__)

_RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")

# ─────────────────────────────────────────────────────────────────────────────
#  CURATED 2026 INDIAN FINANCE NICHE HASHTAG DATABASE
#  Built from real Instagram & YouTube SEO research for Indian retail investors.
#  Updated quarterly. Used as primary source if no RapidAPI subscription active.
# ─────────────────────────────────────────────────────────────────────────────

_ENGLISH_NICHE_HASHTAGS = {
    "instagram": {
        "core": [
            "#IndianStockMarket", "#NiftyAlert", "#NSEIndia", "#BSEIndia",
            "#FinancialFreedomIndia", "#IndianInvestors", "#RetailInvestor",
            "#SmartMoneyIndia", "#StockMarketIndia", "#WealthCreationIndia",
        ],
        "niche_high_engagement": [
            "#MarketDebunk", "#StockMarketMyths", "#InvestingTruths",
            "#MoneyMistakes", "#FinanceLiteracy", "#IndiaInvests",
            "#MutualFundsSahi", "#SIPInvesting", "#NiftyTrading", "#SensexAlert",
            "#F&O", "#OptionsTrading", "#IntradayTrading", "#SwingTrading",
            "#LongTermInvesting", "#ValueInvesting", "#DividendStocks",
            "#MultibaggerStocks", "#SmallCapStocks", "#MidCapStocks",
        ],
        "emotional_triggers": [
            "#MoneyTips", "#RichMindset", "#FinancialGoals", "#PassiveIncome",
            "#InvestWisely", "#MoneyManagement", "#WealthBuilding", "#RetirementPlanning",
        ],
    },
    "youtube": {
        "search_tags": [
            "stock market india", "nifty 50 analysis today", "sensex crash",
            "indian stock market for beginners", "how to invest in india",
            "mutual funds vs stocks india", "sip investing india", "f&o trading india",
            "stock market myths india", "market debunk", "investing mistakes india",
            "smallcap stocks 2026", "multibagger stocks", "nifty prediction today",
            "bear market india", "bull market strategy india",
            "zerodha trading tips", "groww investing guide", "demat account india",
            "ipo india 2026", "dividend stocks india", "value investing india",
        ],
        "title_power_verbs": [
            "Why", "This", "Is", "Exposes", "The Truth About",
            "Nobody Tells You About", "The Hidden", "Avoid This",
            "Before You Invest", "Warning", "Alert",
        ],
    },
    "facebook": {
        "topic_tags": [
            "#IndianInvestors", "#StockMarketIndia", "#PersonalFinanceIndia",
            "#RetailInvestor", "#SmartInvesting", "#FinancialPlanning",
            "#WealthManagement", "#NSEIndia", "#SIPInvesting", "#MutualFunds",
        ],
        "story_openers": [
            "My colleague asked me last week...",
            "A friend lost ₹50,000 because of this mistake...",
            "Every retail investor I talk to believes this — and it's costing them money...",
            "I wish someone had told me this before I started investing...",
            "The numbers shocked even me when I looked it up...",
            "Here's what the mutual fund advertisements never show you...",
        ],
    },
}

_TOPIC_KEYWORD_MAP = {
    # Maps common topic keywords to relevant niche hashtag sets
    "nifty": ["#Nifty50", "#NiftyAlert", "#NSEIndia", "#NiftyTrading", "#IndexFund"],
    "sensex": ["#Sensex", "#BSEIndia", "#SensexAlert", "#IndiaEquity"],
    "mutual fund": ["#MutualFundsSahi", "#SIPInvesting", "#MFIndia", "#ELSS", "#NAV"],
    "sip": ["#SIPInvesting", "#MutualFundsSahi", "#LongTermInvesting", "#WealthCreation"],
    "smallcap": ["#SmallCapStocks", "#SmallCap", "#MultibaggerStocks", "#HiddenGems"],
    "midcap": ["#MidCapStocks", "#NSEMidcap", "#GrowthStocks", "#ValueInvesting"],
    "ipo": ["#IPO2026", "#IPOAlert", "#NewIPO", "#GMP", "#IPOIndia"],
    "f&o": ["#FnO", "#OptionsTrading", "#FuturesAndOptions", "#DerivativesIndia", "#F&O"],
    "intraday": ["#IntradayTrading", "#DayTrading", "#NSEIntraday", "#ScalpingIndia"],
    "gold": ["#GoldInvesting", "#SovereignGoldBond", "#GoldETF", "#SGB", "#GoldVsStocks"],
    "real estate": ["#RealEstateIndia", "#PropertyInvestment", "#REITs", "#HousingMarket"],
    "crypto": ["#CryptoIndia", "#BitcoinIndia", "#Web3India", "#CryptoRegulation"],
    "trap": ["#MarketTrap", "#BearTrap", "#BullTrap", "#MarketDebunk", "#InvestingMyths"],
    "scam": ["#StockScam", "#PumpAndDump", "#InvestingScams", "#MarketFraud"],
    "dividend": ["#DividendStocks", "#DividendInvesting", "#PassiveIncome", "#HighDividend"],
    "debt": ["#DebtFunds", "#LiquidFunds", "#FixedIncome", "#BondInvesting"],
}


_THEMATIC_CLUSTERS = [
    ["#MarketDebunk", "#StockMarketMyths", "#InvestingTruths", "#RetailInvestor", "#MarketTrap"],
    ["#WealthCreationIndia", "#SIPInvesting", "#MutualFundsSahi", "#FinancialFreedomIndia", "#SmartInvesting"],
    ["#NiftyAlert", "#NSEIndia", "#NiftyTrading", "#StockMarketIndia", "#SmartMoneyIndia"],
    ["#MoneyMistakes", "#FinanceLiteracy", "#IndiaInvests", "#PassiveIncome", "#WealthBuilding"],
]


def _get_recent_hashtags_from_ledger() -> list[str]:
    """Retrieve hashtags used in the most recent uploads from publish ledger."""
    try:
        from src.utils.config import settings
        ledger_path = settings.DATA_DIR / "publish_ledger.json"
        if ledger_path.is_file():
            with open(ledger_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    recent = []
                    for entry in data[-3:]:
                        recent.extend(entry.get("hashtags", []))
                    return recent
    except Exception:
        pass
    return []


def _extract_topic_tags(thesis: str, platform: str, count: int = 6) -> list[str]:
    """
    Extract relevant niche hashtags with dynamic cluster rotation.
    Avoids repeating the exact same hashtag fingerprint across back-to-back uploads.
    """
    thesis_lower = thesis.lower()
    matched_tags: list[str] = []

    for keyword, tags in _TOPIC_KEYWORD_MAP.items():
        if keyword in thesis_lower:
            matched_tags.extend(tags)

    # Rotate cluster based on publish ledger history (pick cluster with lowest recent overlap)
    recent_tags = set(t.lower() for t in _get_recent_hashtags_from_ledger())
    chosen_cluster = min(
        _THEMATIC_CLUSTERS,
        key=lambda cluster: len(set(t.lower() for t in cluster) & recent_tags)
    )

    seen = set()
    unique_tags = []
    for t in matched_tags:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique_tags.append(t)

    # Append rotating cluster tags that aren't already included
    for t in chosen_cluster:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique_tags.append(t)

    # Fallback to base niche if needed
    if platform == "instagram":
        base = _ENGLISH_NICHE_HASHTAGS["instagram"]["niche_high_engagement"]
    elif platform == "facebook":
        base = _ENGLISH_NICHE_HASHTAGS["facebook"]["topic_tags"]
    else:
        base = _ENGLISH_NICHE_HASHTAGS["youtube"]["search_tags"]

    for t in base:
        if t.lower() not in seen:
            seen.add(t.lower())
            unique_tags.append(t)

    # Shuffle non-primary tags slightly to prevent fixed positional fingerprint
    primary = unique_tags[:2]
    secondary = unique_tags[2:]
    random.shuffle(secondary)
    result = primary + secondary
    return result[:count]


def _try_rapidapi_hashtags(keyword: str, platform: str) -> list[str]:
    """
    Attempt to fetch live trending hashtags from RapidAPI.
    Tries multiple known endpoints in cascade order.
    Returns [] if no subscribed endpoint found or quota exhausted.
    """
    if not _RAPIDAPI_KEY:
        return []

    endpoints = [
        # Endpoint format: (host, url, params_builder)
        (
            "trending-hashtags.p.rapidapi.com",
            "https://trending-hashtags.p.rapidapi.com/hashtags",
            {"keyword": keyword, "platform": platform},
        ),
        (
            "instagram-statistics-api.p.rapidapi.com",
            "https://instagram-statistics-api.p.rapidapi.com/community/tags",
            {"q": keyword.replace(" ", "")},
        ),
        (
            "instagram7.p.rapidapi.com",
            "https://instagram7.p.rapidapi.com/hashtag_posts",
            {"tag": keyword.replace(" ", "")},
        ),
        (
            "hash-tag-generator.p.rapidapi.com",
            "https://hash-tag-generator.p.rapidapi.com/get-hashtags",
            {"keyword": keyword},
        ),
    ]

    for host, url, params in endpoints:
        try:
            resp = requests.get(
                url,
                headers={"x-rapidapi-key": _RAPIDAPI_KEY, "x-rapidapi-host": host},
                params=params,
                timeout=6,
            )
            if resp.status_code == 200:
                data = resp.json()
                # Try to extract tags from common response patterns
                raw_tags: list[str] = []
                if isinstance(data, list):
                    raw_tags = [str(t) for t in data]
                elif isinstance(data, dict):
                    for key in ("hashtags", "tags", "data", "results", "items"):
                        if key in data and isinstance(data[key], list):
                            raw_tags = [str(t) for t in data[key]]
                            break

                if raw_tags:
                    # Clean and prefix with #
                    cleaned = []
                    for tag in raw_tags[:20]:
                        tag = re.sub(r"[^\w]", "", str(tag))
                        if tag and len(tag) < 40:
                            cleaned.append(f"#{tag}" if not tag.startswith("#") else tag)
                    if cleaned:
                        log.info("✓ RapidAPI [%s] returned %d tags for '%s'", host, len(cleaned), keyword)
                        return cleaned[:12]
        except Exception as exc:
            log.debug("RapidAPI [%s] failed: %s", host, exc)

    return []


def _rewrite_hook_with_gemini(
    current_hook: str,
    trending_tags: list[str],
    thesis: str,
    platform: str,
    gemini_key: str,
) -> str:
    """Use Gemini flash-lite to rewrite the hook using trending topic context."""
    if not gemini_key:
        return current_hook

    _platform_rules = {
        "instagram": (
            "Write a single scroll-stopping Instagram Reels first-line hook. "
            "MAX 80 characters. Start with ONE emoji (🚨 or ⚠️ or 💰 or 🔥). "
            "Create a curiosity gap about the financial topic. No full stops at end."
        ),
        "youtube": (
            "Write a single YouTube Shorts title in format: [Power word] [Specific claim] #Shorts. "
            "MAX 50 characters total including #Shorts. High search-intent."
        ),
        "facebook": (
            "Write a single sentence Facebook Reels story opener. "
            "Sounds like a Tamil/Indian person telling a friend about a money mistake. "
            "Relatable, conversational. No hashtags."
        ),
    }

    rule = _platform_rules.get(platform, "Write one improved marketing hook.")

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=gemini_key)
        tag_context = ", ".join(trending_tags[:6]) if trending_tags else ""
        tag_line = f"\nTRENDING CONTEXT (thematic inspiration only): {tag_context}" if tag_context else ""

        prompt = f"""You are a {platform.upper()} copywriter for Indian finance short-form video.

TASK: {rule}

TOPIC: {thesis}
CURRENT TEXT: {current_hook}{tag_line}

STRICT OUTPUT RULE: Output ONLY the rewritten text. One line. No labels. No explanation. No quotes. No "Instagram:" or "YouTube:" prefix."""

        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.8, max_output_tokens=80),
        )
        rewritten = (response.text or current_hook).strip().strip('"').strip("'")
        if rewritten and len(rewritten) > 5:
            log.info("✓ Gemini rewrite [%s]: %s", platform, rewritten[:80])
            return rewritten
    except Exception as exc:
        log.debug("Gemini hook rewrite failed: %s", exc)

    return current_hook


# ─────────────────────────────────────────────────────────────────────────────
#  SUBAGENT 1: YouTube SEO Agent
# ─────────────────────────────────────────────────────────────────────────────

class YouTubeSEOAgent:
    """
    Research-backed YouTube Shorts SEO specialist for Market Debunk English channel.

    Responsibilities:
    1. Fetch trending search tags for the video's topic via RapidAPI
    2. Inject curated niche Indian finance search tags
    3. Rewrite title for maximum search-intent + CTR alignment
    4. Ensure pinned_comment drives comment velocity
    """

    PLATFORM = "youtube"
    MAX_SEARCH_TAGS = 12
    MAX_TITLE_LEN = 50

    def __init__(self, gemini_key: str = ""):
        self.gemini_key = gemini_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_SCRIPT_API_KEY") or ""

    def enhance(self, pkg, thesis: str) -> None:
        """Enhance YouTube metadata in-place. pkg is a PlatformDistributionPackage."""
        log.info("🔍 YouTubeSEOAgent: Researching search tags for '%s'...", thesis[:60])

        # 1. Extract topic core keyword
        topic_kw = self._extract_core_keyword(thesis)

        # 2. Fetch live tags (RapidAPI → curated DB)
        live_tags = _try_rapidapi_hashtags(topic_kw + " india stock market", "youtube")
        if not live_tags:
            live_tags = _ENGLISH_NICHE_HASHTAGS["youtube"]["search_tags"]

        # 3. Get topic-specific tags from our research DB
        topic_tags = _extract_topic_tags(thesis, "youtube", count=6)

        # 4. Merge: topic-specific first, then live research, then base
        all_tags = []
        seen = set()
        for tag in topic_tags + live_tags + _ENGLISH_NICHE_HASHTAGS["youtube"]["search_tags"]:
            clean = tag.lstrip("#").lower()
            if clean not in seen:
                seen.add(clean)
                all_tags.append(tag.lstrip("#"))  # YouTube uses no-# tags

        pkg.youtube.search_tags = all_tags[:self.MAX_SEARCH_TAGS]

        # 5. Inject strong niche hashtags into the hashtags field
        yt_hashtags = _extract_topic_tags(thesis, "instagram", count=3)
        if not yt_hashtags:
            yt_hashtags = ["#IndianStockMarket", "#NiftyAlert", "#StockMarketIndia"]
        yt_hashtags = yt_hashtags[:3] + ["#Shorts"]
        pkg.youtube.hashtags = list(dict.fromkeys(yt_hashtags))[:5]

        # 6. Rewrite title for max CTR
        pkg.youtube.title = self._rewrite_title(pkg.youtube.title, thesis)

        # 7. Power-up pinned comment
        pkg.youtube.pinned_comment = self._enhance_pinned_comment(pkg.youtube.pinned_comment, thesis)

        log.info("✅ YouTubeSEOAgent: Enhanced — %d search tags, title: '%s'",
                 len(pkg.youtube.search_tags), pkg.youtube.title)

    def _extract_core_keyword(self, thesis: str) -> str:
        """Extract a 2-3 word search keyword from the thesis."""
        # Remove common filler
        cleaned = re.sub(r'\b(the|a|an|is|are|was|were|be|to|of|in|on|at|for|with|by|from|about|that|this|it|they|we|you|i|and|or|but|if|then|when|how|why|what|who|which)\b', '', thesis.lower())
        words = [w for w in cleaned.split() if len(w) > 3]
        return " ".join(words[:3]) if words else "nifty stock market"

    def _rewrite_title(self, current_title: str, thesis: str) -> str:
        """Rewrite title to be more search-intent aligned and CTR-optimized."""
        # Remove #Shorts suffix for processing
        base = current_title.replace("#Shorts", "").strip()

        # Check if title has weak/generic openers and fix them
        weak_openers = ["the truth", "what you", "here's why", "did you know", "warning about"]
        has_weak_opener = any(base.lower().startswith(w) for w in weak_openers)

        if has_weak_opener or len(base) > 42:
            # Try Gemini rewrite first
            rewritten = _rewrite_hook_with_gemini(
                base, _ENGLISH_NICHE_HASHTAGS["youtube"]["search_tags"][:6], thesis, "youtube", self.gemini_key
            )
            if rewritten and rewritten != base:
                # Ensure it ends with #Shorts and is within limit
                rewritten = rewritten.replace("#Shorts", "").strip()
                if len(rewritten) > 42:
                    rewritten = rewritten[:42].rsplit(" ", 1)[0]
                return f"{rewritten} #Shorts"

        # Ensure it ends with #Shorts
        if not current_title.endswith("#Shorts"):
            base = base[:44] if len(base) > 44 else base
            return f"{base} #Shorts"

        return current_title

    def _enhance_pinned_comment(self, current: str, thesis: str) -> str:
        """Make the pinned comment more likely to trigger real comments."""
        if len(current) > 20:
            return current  # Already has content
        topic_kw = self._extract_core_keyword(thesis).title()
        options = [
            f"Have you ever lost money because of a {topic_kw} mistake? Tell us below 👇",
            f"Are you currently holding positions in {topic_kw}? Drop your entry price 👇",
            f"Did you know about this {topic_kw} trap before watching? Comment YES or NO 👇",
            f"What's your current {topic_kw} strategy? Let's debate 👇",
        ]
        return random.choice(options)


# ─────────────────────────────────────────────────────────────────────────────
#  SUBAGENT 2: Instagram SEO Agent
# ─────────────────────────────────────────────────────────────────────────────

class InstagramSEOAgent:
    """
    Research-backed Instagram Reels SEO specialist for Market Debunk English channel.

    Responsibilities:
    1. Fetch top trending hashtags for the Indian finance niche via RapidAPI
    2. Prioritise niche (medium-competition, high-engagement) over mega-tags
    3. Rewrite first_line_hook into a 2-line scroll-stopping format
    4. Ensure save/share CTA is platform-optimised for Reels algorithm
    """

    PLATFORM = "instagram"
    MAX_HASHTAGS = 8
    MAX_FIRST_LINE = 80

    def __init__(self, gemini_key: str = ""):
        self.gemini_key = gemini_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_SCRIPT_API_KEY") or ""

    def enhance(self, pkg, thesis: str) -> None:
        """Enhance Instagram metadata in-place."""
        log.info("🔍 InstagramSEOAgent: Researching trending hashtags for '%s'...", thesis[:60])

        # 1. Fetch live hashtags
        topic_kw = thesis.split()[:4]
        search_kw = " ".join(topic_kw) + " india investing"
        live_tags = _try_rapidapi_hashtags(search_kw, "instagram")

        # 2. Always build a strong curated set
        topic_tags = _extract_topic_tags(thesis, "instagram", count=5)
        core_tags = _ENGLISH_NICHE_HASHTAGS["instagram"]["core"][:3]
        emotional_tags = _ENGLISH_NICHE_HASHTAGS["instagram"]["emotional_triggers"][:2]

        # 3. Merge: topic-specific > live research > core niche > emotional
        all_tags: list[str] = []
        seen: set[str] = set()
        for tag in topic_tags + live_tags + core_tags + emotional_tags:
            clean = tag.lstrip("#").lower()
            if clean not in seen and len(all_tags) < self.MAX_HASHTAGS:
                seen.add(clean)
                all_tags.append(f"#{tag.lstrip('#')}")

        pkg.instagram.hashtags = all_tags[:self.MAX_HASHTAGS]

        # 4. Rewrite first_line_hook to be scroll-stopping
        pkg.instagram.first_line_hook = self._rewrite_hook(pkg.instagram.first_line_hook, thesis, all_tags)

        # 5. Strengthen share/save CTA (drives the #1 algorithm signal)
        pkg.instagram.share_save_cta = self._strengthen_cta(pkg.instagram.share_save_cta)

        # 6. Upgrade comment trigger for DM flow
        pkg.instagram.comment_trigger = self._upgrade_comment_trigger(pkg.instagram.comment_trigger, thesis)

        log.info("✅ InstagramSEOAgent: Enhanced — %d hashtags, hook: '%s...'",
                 len(pkg.instagram.hashtags), pkg.instagram.first_line_hook[:50])

    def _rewrite_hook(self, current_hook: str, thesis: str, trending_tags: list[str]) -> str:
        """Rewrite the first_line_hook into a proven scroll-stopping 2-line format."""
        # First try: Gemini-powered rewrite with trending context
        rewritten = _rewrite_hook_with_gemini(current_hook, trending_tags, thesis, "instagram", self.gemini_key)
        if rewritten and rewritten != current_hook:
            return rewritten[:self.MAX_FIRST_LINE]

        # Fallback: Template-based power hook
        topic_words = [w for w in thesis.split() if len(w) > 4][:3]
        topic_str = " ".join(topic_words).title() if topic_words else "This Market Move"

        power_hooks = [
            f"🚨 {topic_str} is a trap — here's what they hide from you",
            f"⚠️ The real reason {topic_str} is destroying retail investors",
            f"💰 Why smart money avoids {topic_str} (and you should too)",
            f"🔥 {topic_str}: the dirty secret nobody in finance talks about",
            f"📉 Stop falling for the {topic_str} myth — watch this first",
        ]
        return random.choice(power_hooks)[:self.MAX_FIRST_LINE]

    def _strengthen_cta(self, current_cta: str) -> str:
        """Ensure the save/share CTA explicitly triggers the two highest-weight Reels signals."""
        strong_ctas = [
            "📌 Save this before your next trade — you WILL need it\n📩 Send to 1 friend who needs to see this 👆",
            "💾 Save this Reel now (your future self will thank you)\n📩 Share with anyone who invests — they need this",
            "📌 Save this — screenshot the key point & share it with your investor group 👆",
        ]
        # Use current if it's already strong, else replace
        if "save" in current_cta.lower() and "share" in current_cta.lower() and len(current_cta) > 40:
            return current_cta
        return random.choice(strong_ctas)

    def _upgrade_comment_trigger(self, current: str, thesis: str) -> str:
        """Upgrade comment trigger to drive DM flow and comment velocity."""
        triggers = [
            "💬 Comment 'GUIDE' below → we'll DM you the full risk checklist for FREE",
            "💬 Type 'DEBUNK' in comments → get our full breakdown sent to your DMs 📥",
            "💬 Comment your biggest investing fear below 👇 Let's discuss",
            "💬 Comment 'YES' if this happened to you — 'NO' if you caught it in time",
        ]
        if "comment" in current.lower() and len(current) > 30:
            return current
        return random.choice(triggers)


# ─────────────────────────────────────────────────────────────────────────────
#  SUBAGENT 3: Facebook SEO Agent
# ─────────────────────────────────────────────────────────────────────────────

class FacebookSEOAgent:
    """
    Research-backed Facebook Reels SEO specialist for Market Debunk English channel.

    Responsibilities:
    1. Fetch trending topic tags for Facebook Reels via RapidAPI
    2. Rewrite story_hook to open with a relatable everyday investor scenario
    3. Ensure discussion_question triggers genuine debate (not yes/no)
    4. Inject niche-appropriate topic tags
    """

    PLATFORM = "facebook"
    MAX_TOPIC_TAGS = 5

    def __init__(self, gemini_key: str = ""):
        self.gemini_key = gemini_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMINI_SCRIPT_API_KEY") or ""

    def enhance(self, pkg, thesis: str) -> None:
        """Enhance Facebook metadata in-place."""
        log.info("🔍 FacebookSEOAgent: Researching topic tags for '%s'...", thesis[:60])

        # 1. Fetch live tags
        search_kw = " ".join(thesis.split()[:4]) + " india"
        live_tags = _try_rapidapi_hashtags(search_kw, "facebook")

        # 2. Build strong curated set
        topic_tags = _extract_topic_tags(thesis, "facebook", count=4)
        base_tags = _ENGLISH_NICHE_HASHTAGS["facebook"]["topic_tags"][:3]

        all_tags: list[str] = []
        seen: set[str] = set()
        for tag in topic_tags + live_tags + base_tags:
            clean = tag.lstrip("#").lower()
            if clean not in seen and len(all_tags) < self.MAX_TOPIC_TAGS:
                seen.add(clean)
                all_tags.append(f"#{tag.lstrip('#')}")

        pkg.facebook.topic_tags = all_tags[:self.MAX_TOPIC_TAGS]

        # 3. Rewrite story_hook for relatability
        pkg.facebook.story_hook = self._rewrite_story_hook(pkg.facebook.story_hook, thesis)

        # 4. Strengthen discussion question for real debate (not binary yes/no)
        pkg.facebook.discussion_question = self._strengthen_discussion_q(
            pkg.facebook.discussion_question, thesis
        )

        log.info("✅ FacebookSEOAgent: Enhanced — %d tags, hook: '%s...'",
                 len(pkg.facebook.topic_tags), pkg.facebook.story_hook[:60])

    def _rewrite_story_hook(self, current_hook: str, thesis: str) -> str:
        """Rewrite to open with a relatable everyday investor scenario."""
        rewritten = _rewrite_hook_with_gemini(current_hook, [], thesis, "facebook", self.gemini_key)
        if rewritten and rewritten != current_hook and len(rewritten) > 20:
            return rewritten

        topic_words = [w for w in thesis.split() if len(w) > 4][:2]
        topic_str = " ".join(topic_words).title() if topic_words else "this investment"

        openers = _ENGLISH_NICHE_HASHTAGS["facebook"]["story_openers"]
        base_opener = random.choice(openers)
        return f"{base_opener} They thought {topic_str} was their safest move. The math tells a completely different story."

    def _strengthen_discussion_q(self, current_q: str, thesis: str) -> str:
        """Replace weak yes/no questions with open-ended debate starters."""
        weak_patterns = ["would you", "do you", "yes or no", "agree?", "right?"]
        is_weak = any(p in current_q.lower() for p in weak_patterns) or len(current_q) < 40

        if not is_weak:
            return current_q

        topic_words = [w for w in thesis.split() if len(w) > 4][:2]
        topic_str = " ".join(topic_words).title() if topic_words else "this"

        strong_questions = [
            f"What's the ONE thing you wish someone had told you about {topic_str} before you invested? Comment below 👇",
            f"If you had ₹1 lakh to invest right now knowing what this video shows, where would you put it instead? 👇",
            f"Tag a friend who is currently making this {topic_str} mistake. Let's help them before it's too late 👇",
            f"What did your broker/advisor tell you about {topic_str} that turned out to be wrong? Share your story 👇",
        ]
        return random.choice(strong_questions)
