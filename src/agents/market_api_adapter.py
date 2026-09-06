"""
src/agents/market_api_adapter.py

Dedicated Indian Share Market & Financial News Aggregator.
Queries both IndianAPI (stock.indianapi.in) and Marketaux (api.marketaux.com)
in parallel to aggregate institutional news, corporate actions, and breaking market stories.
"""
from __future__ import annotations

import hashlib
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Optional

import requests

from src.agents import evaluator
from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="market_api")

INDIAN_API_KEY_DEFAULT = "sk-live-Ca1EJj4XFo61nRpchb93tlGrs0IyVEC5cl4A6iF5"
MARKETAUX_API_TOKEN_DEFAULT = "bZ1PVR803PweIGinKuMa1r6Zk4kPn4v8xikQvUkC"


class DedicatedMarketAPIAdapter:
    """
    Dual-engine Market Intelligence Adapter.
    Pulls live signals and news concurrently from:
      1. Marketaux: Indian equity & macroeconomic financial news.
      2. IndianAPI: Real-time BSE/NSE corporate actions, earnings results, and trending movers.
    """

    def __init__(self):
        self.indian_api_key = getattr(settings, "INDIAN_API_KEY", "") or os.getenv("INDIAN_API_KEY") or INDIAN_API_KEY_DEFAULT
        self.marketaux_token = getattr(settings, "MARKETAUX_API_TOKEN", "") or os.getenv("MARKETAUX_API_TOKEN") or MARKETAUX_API_TOKEN_DEFAULT

    def is_configured(self) -> bool:
        """Returns True if at least one API key is available."""
        return bool(self.indian_api_key or self.marketaux_token)

    def _fetch_marketaux_news(self, limit: int = 6) -> list[dict]:
        """Fetch breaking Indian market news and entity sentiment from Marketaux."""
        if not self.marketaux_token:
            return []
        try:
            url = "https://api.marketaux.com/v1/news/all"
            params = {
                "api_token": self.marketaux_token,
                "countries": "in",
                "language": "en",
                "limit": limit,
            }
            resp = requests.get(url, params=params, timeout=12)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                signals = []
                for item in data:
                    title = (item.get("title") or "").strip()
                    desc = (item.get("description") or item.get("snippet") or "").strip()
                    source = item.get("source", "Marketaux")
                    pub_at = item.get("published_at", "")
                    url_link = item.get("url", "")
                    entities = item.get("entities", [])
                    entity_str = ", ".join(e.get("name", "") for e in entities if e.get("name"))

                    if not title:
                        continue

                    context = f"{desc} Entities: {entity_str}" if entity_str else desc
                    signals.append({
                        "headline": title,
                        "context": context,
                        "source": f"Marketaux ({source})",
                        "published_at": pub_at,
                        "url": url_link,
                    })
                log.info("Marketaux returned %d Indian financial news articles", len(signals))
                return signals
            else:
                log.warning("Marketaux API returned status %d: %s", resp.status_code, resp.text[:100])
        except Exception as exc:
            log.warning("Marketaux news fetch error: %s", exc)
        return []

    def _fetch_indian_api_news(self) -> list[dict]:
        """Fetch corporate announcements, quarterly earnings, and market results from IndianAPI."""
        if not self.indian_api_key:
            return []
        try:
            url = "https://stock.indianapi.in/news"
            headers = {"X-Api-Key": self.indian_api_key}
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                items = resp.json()
                signals = []
                if isinstance(items, list):
                    for item in items[:6]:
                        title = (item.get("title") or "").strip()
                        summary = (item.get("summary") or "").strip()
                        source = item.get("source", "IndianAPI (BSE/NSE)")
                        pub_at = item.get("pub_date", "")
                        url_link = item.get("url", "")

                        if not title:
                            continue

                        signals.append({
                            "headline": title,
                            "context": summary,
                            "source": f"IndianAPI: {source}",
                            "published_at": pub_at,
                            "url": url_link,
                        })
                log.info("IndianAPI returned %d corporate news articles", len(signals))
                return signals
            else:
                log.warning("IndianAPI news returned status %d: %s", resp.status_code, resp.text[:100])
        except Exception as exc:
            log.warning("IndianAPI news fetch error: %s", exc)
        return []

    def _fetch_indian_api_trending(self) -> list[dict]:
        """Fetch trending stocks, top gainers, and top losers from IndianAPI."""
        if not self.indian_api_key:
            return []
        try:
            url = "https://stock.indianapi.in/trending"
            headers = {"X-Api-Key": self.indian_api_key}
            resp = requests.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                data = resp.json().get("trending_stocks", {})
                signals = []
                movers = (data.get("top_gainers", [])[:3]) + (data.get("top_losers", [])[:3])
                for m in movers:
                    company = m.get("company_name", "")
                    pct = m.get("percent_change", "")
                    price = m.get("price", "")
                    net = m.get("net_change", "")
                    if not company:
                        continue
                    headline = f"Significant market volatility in {company}: stock moves {pct}%"
                    context = f"{company} traded at ₹{price} (net change ₹{net}, {pct}%). High volatility reported."
                    signals.append({
                        "headline": headline,
                        "context": context,
                        "source": "IndianAPI (NSE/BSE Movers)",
                        "published_at": datetime.now(timezone.utc).isoformat(),
                        "url": "",
                    })
                return signals
        except Exception as exc:
            log.warning("IndianAPI trending fetch error: %s", exc)
        return []

    def fetch_market_signals(self) -> list[dict]:
        """
        Executes parallel calls to BOTH Marketaux and IndianAPI simultaneously,
        interleaving and compiling a rich, high-value pool of Indian financial stories.
        """
        if not self.is_configured():
            log.info("Dedicated Market APIs not configured.")
            return []

        all_signals: list[dict] = []
        log.info("Querying BOTH Marketaux & IndianAPI simultaneously...")

        with ThreadPoolExecutor(max_workers=3) as executor:
            future_marketaux = executor.submit(self._fetch_marketaux_news, 6)
            future_indian_news = executor.submit(self._fetch_indian_api_news)
            future_indian_trending = executor.submit(self._fetch_indian_api_trending)

            for f in as_completed([future_marketaux, future_indian_news, future_indian_trending]):
                try:
                    res = f.result()
                    if res:
                        all_signals.extend(res)
                except Exception as err:
                    log.warning("Market signal worker error: %s", err)

        log.info("Aggregated %d total candidate signals from Marketaux & IndianAPI.", len(all_signals))
        return all_signals

    def get_topic_seed(self) -> Optional[dict]:
        """
        Gathers signals from both APIs, validates against concept duplication,
        macro-domain cooldown, and fuzzy matching, and returns a verified candidate.
        """
        signals = self.fetch_market_signals()
        if not signals:
            return None

        for sig in signals:
            headline = sig.get("headline", "").strip()
            context = sig.get("context", "").strip()
            source = sig.get("source", "Indian Financial News")
            url_link = sig.get("url", "")
            pub_at = sig.get("published_at", "")

            if not headline or len(headline.split()) < 4:
                continue

            source_id = "market_api:" + hashlib.sha256((url_link or headline).lower().encode("utf-8")).hexdigest()[:16]

            if evaluator.is_source_id_used(source_id):
                continue

            is_dup, score, reason = evaluator.is_duplicate(headline)
            if is_dup:
                log.info("Market signal candidate '%s' blocked: %s", headline[:50], reason)
                continue

            raw_text = (
                f"Verified Indian Stock Market Intelligence from {source} (published: {pub_at}).\n"
                f"Headline: {headline}\n"
                f"Context: {context}\n"
                f"URL: {url_link}"
            )

            log.info("✓ Discovered approved story candidate from Market API: '%s' (%s)", headline, source)
            return {
                "channel": f"Market API: {source}",
                "video_id": "",
                "source_id": source_id,
                "video_title": headline,
                "raw_text": raw_text,
            }

        return None
