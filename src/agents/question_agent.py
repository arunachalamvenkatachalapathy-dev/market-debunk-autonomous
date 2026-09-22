"""
src/agents/question_agent.py

QuestionCraftingAgent — Generates specific, non-repeating personal-implication
question hooks for Market Debunk English videos.

PHILOSOPHY:
  Questions must create PERSONAL ANXIETY — not curiosity about information.
  Bad (generic):  "Did you know banks charge hidden fees?"
  Bad (repeated): Same question used in a prior video.
  Good (specific): "Is your SIP silently eating 2% of your returns every year?"

ANTI-REPETITION:
  All used questions are stored in data/used_questions.json with timestamps.
  A fuzzy-match check (threshold: 65) blocks near-duplicate questions.
  Questions expire from the ledger after 60 days.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from thefuzz import fuzz

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="question_crafting")

_LEDGER_PATH = settings.DATA_DIR / "used_questions.json"
_EXPIRY_DAYS = 60
_DEDUP_THRESHOLD = 65  # fuzzy score 0-100

# ──────────────────────────────────────────────────────────────────────────────
#  Specificity Scoring
# ──────────────────────────────────────────────────────────────────────────────

SPECIFICITY_BONUS: Dict[str, int] = {
    # Specific financial products
    "sip": 15, "swp": 15, "elss": 15, "ulip": 15,
    "fd": 12, "fixed deposit": 12, "rd": 10, "recurring deposit": 10,
    "ppf": 12, "nps": 10, "epfo": 12, "pf": 10,
    "emi": 12, "cibil": 12, "tds": 12, "gst": 10,
    "mutual fund": 12, "expense ratio": 15, "nav": 10,
    "credit card": 12, "debit card": 10, "savings account": 10,
    "home loan": 12, "personal loan": 12, "gold": 8,
    "jewellery": 10, "broker": 10, "f&o": 12, "options": 10,
    # Action verbs implying personal impact
    "charging": 10, "deducting": 10, "stealing": 8,
    "hiding": 8, "trapping": 8, "eating": 8, "draining": 8,
    "silently": 6, "secretly": 6, "quietly": 5,
    # Numbers and amounts always increase specificity
}

GENERIC_PENALTY: Dict[str, int] = {
    "did you know": -30,        # awareness framing — banned
    "have you heard": -25,
    "are you aware": -25,
    "do you want": -20,
    "have you ever": -20,
    "your money": -5,           # too vague alone
}

# ──────────────────────────────────────────────────────────────────────────────
#  Topic → Fallback Question Map (25 financial trap categories)
# ──────────────────────────────────────────────────────────────────────────────

TOPIC_QUESTION_MAP: Dict[str, str] = {
    "sip": "Is your SIP silently charging more than you were promised?",
    "swp": "Is your SWP plan secretly depleting your corpus every month?",
    "mutual fund": "Is your mutual fund advisor hiding a trail commission from you?",
    "regular plan": "Are you still losing lakhs every year in a regular mutual fund plan?",
    "direct plan": "Did your distributor ever tell you about the direct fund option?",
    "expense ratio": "Is your fund's expense ratio quietly eating your annual returns?",
    "elss": "Is your ELSS fund charging hidden fees your advisor never mentioned?",
    "ulip": "Is your ULIP plan hiding 40% first-year charges from you?",
    "emi": "Did you really think zero-cost EMI means paying no interest at all?",
    "zero cost": "Did you really think zero-cost EMI costs you nothing extra?",
    "credit card": "Do you actually know what your credit card's minimum due is costing you?",
    "minimum due": "Is your minimum-due payment silently trapping you in a debt spiral?",
    "fd": "Is your FD earning less than inflation is silently taking away?",
    "fixed deposit": "Is your bank's FD actually beating inflation right now?",
    "rd": "Is your recurring deposit secretly losing value to inflation every year?",
    "insurance": "Is your insurance policy quietly draining your savings every single month?",
    "lic": "Is your LIC policy secretly eating your savings while promising returns?",
    "ppf": "Is your PPF return quietly falling behind inflation this year?",
    "nps": "Is your NPS fund delivering the retirement returns they actually promised?",
    "epfo": "Did your employer actually deposit your PF contribution this month?",
    "home loan": "Is your home loan EMI hiding a processing fee you never agreed to?",
    "cibil": "Is your CIBIL score dropping because of something you never did wrong?",
    "upi": "Did your bank quietly charge you for a UPI transfer this month?",
    "gold": "Is your gold jewellery investment secretly losing money in making charges?",
    "broker": "Is your broker charging hidden transaction fees on every single trade?",
    "options": "Are you losing money on F&O options without knowing the real reason why?",
    "savings account": "Is your savings account earning 3% while your bank profits off your money?",
    "bank": "Is your bank silently deducting charges you never approved or agreed to?",
    "tds": "Is your bank deducting TDS on your FD without telling you how much?",
}

# ──────────────────────────────────────────────────────────────────────────────
#  LLM Prompt
# ──────────────────────────────────────────────────────────────────────────────

def _build_generation_prompt(thesis: str, hook_type: str, topic_keywords: str, used_sample: List[str]) -> str:
    used_block = ""
    if used_sample:
        used_block = (
            "\n\nSTRICTLY FORBIDDEN — These questions were already used recently. "
            "Do NOT repeat or paraphrase them:\n"
            + "\n".join(f'  - "{q}"' for q in used_sample[:15])
            + "\n"
        )

    hook_guide = {
        "LOSS_IMPLICATION": (
            "Loss-Implication: Ask if something bad is ALREADY happening to the viewer's money RIGHT NOW.\n"
            "  Pattern: 'Is your [specific product] silently [draining/charging/stealing] [amount/returns]?'\n"
            "  Example: 'Is your SIP silently eating 2% of your returns every year?'"
        ),
        "COMPETENCE_CHALLENGE": (
            "Competence-Challenge: Test if the viewer actually understands their own financial product.\n"
            "  Pattern: 'Do you actually know what your [specific product] is charging you?'\n"
            "  Example: 'Do you actually know what your credit card minimum due costs you each month?'"
        ),
        "MYTH_BUST": (
            "Myth-Bust: Challenge a false belief the viewer currently holds about a financial product.\n"
            "  Pattern: 'Did you really think [product/action] was [false belief]?'\n"
            "  Example: 'Did you really think zero-cost EMI means paying no interest at all?'"
        ),
        "AUTHORITY_CHALLENGE": (
            "Authority-Challenge: Ask if the viewer's advisor/agent/bank is hiding something specific.\n"
            "  Pattern: 'Is your [advisor/agent/bank] hiding [specific thing] from you?'\n"
            "  Example: 'Is your mutual fund distributor hiding a 1% trail commission from you?'"
        ),
        "OUTCOME_GAP": (
            "Outcome-Gap: Ask why the viewer's product is underperforming what was promised.\n"
            "  Pattern: 'Why is your [product] giving you less than [benchmark/promise]?'\n"
            "  Example: 'Why is your FD returning 5% when inflation is silently running at 6%?'"
        ),
    }.get(hook_type, "Loss-Implication: Ask if something bad is already happening to the viewer's money.")

    return f"""You are generating OPENING QUESTION HOOKS for a viral Indian financial short video.

TOPIC: {thesis}
HOOK TYPE: {hook_type}
FINANCIAL KEYWORDS: {topic_keywords}

HOOK TYPE GUIDE:
{hook_guide}

RULES (all are mandatory):
1. The question MUST end with "?"
2. Must contain "you" or "your" — the viewer must feel personally implicated
3. Must be SPECIFIC to the exact financial trap — name the actual product/mechanism
4. Must be 6 to 12 words ONLY
5. Must create ANXIETY about the viewer's CURRENT situation (not general awareness)
6. STRICTLY BANNED OPENERS: "Did you know", "Have you heard", "Are you aware", "Do you want"
7. The question must name or strongly imply the SPECIFIC financial product being exposed

SPECIFICITY TEST: A good question fails if you can replace the product name with "stuff" and it still makes sense.
  BAD: "Is your money at risk?" (too vague)
  GOOD: "Is your SIP silently eroding 2% of your returns?" (specific product + mechanism)
{used_block}
Generate EXACTLY 3 candidate questions. Each must be completely different in phrasing and angle.
Return ONLY valid JSON: {{"candidates": ["Q1", "Q2", "Q3"]}}"""


# ──────────────────────────────────────────────────────────────────────────────
#  QuestionCraftingAgent
# ──────────────────────────────────────────────────────────────────────────────

class QuestionCraftingAgent:
    """
    Generates specific, non-repeating personal-implication question hooks.

    Sits between ChannelDirectorAgent and script_agent.generate_script().
    Pipeline position: Phase 1.75 in manager.py.
    """

    def __init__(self):
        self.ledger_path = _LEDGER_PATH

    # ── Public API ──────────────────────────────────────────────────────────

    def craft_question(
        self,
        thesis: str,
        hook_type: str = "LOSS_IMPLICATION",
        topic_keywords: str = "",
    ) -> str:
        """
        Main entry point.
        Returns the best specific, non-repeated question hook for Scene 1.
        Guaranteed to return a string ending with "?" containing "you"/"your".
        """
        log.info("🎯 QuestionCraftingAgent: Crafting hook [%s] for thesis: '%s'", hook_type, thesis[:60])

        used = self.load_used_questions()
        used_sample = list(used.keys())

        # Step 1: Try LLM generation
        candidates = self._generate_candidates(thesis, hook_type, topic_keywords, used_sample)

        # Step 2: Score and filter
        best = self._select_best(candidates, used)

        # Step 3: Fallback to topic map if no good LLM candidate
        if not best:
            log.warning("QuestionCraftingAgent: All LLM candidates failed — using topic-map fallback.")
            best = self._topic_map_fallback(thesis + " " + topic_keywords, used)

        # Step 4: Last-resort generic (still ends with ?)
        if not best:
            best = self._emergency_fallback(thesis)

        # Step 5: Persist to ledger
        self._persist_question(best, thesis, hook_type, channel="english")

        log.info("✓ QuestionCraftingAgent: Final hook → '%s'", best)
        return best

    # ── Ledger I/O ──────────────────────────────────────────────────────────

    def load_used_questions(self) -> Dict[str, Any]:
        """Load ledger, evicting entries older than EXPIRY_DAYS."""
        if not self.ledger_path.exists():
            return {}
        try:
            with open(self.ledger_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            cutoff = datetime.now(timezone.utc) - timedelta(days=_EXPIRY_DAYS)
            cleaned = {}
            for q, meta in data.items():
                try:
                    ts_str = meta.get("ts", "") if isinstance(meta, dict) else ""
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts >= cutoff:
                        cleaned[q] = meta
                except (ValueError, TypeError, AttributeError):
                    pass
            return cleaned
        except Exception as e:
            log.warning("QuestionCraftingAgent: Could not load ledger (%s)", e)
            return {}

    def _persist_question(self, question: str, topic: str, hook_type: str, channel: str = "english") -> None:
        """Write the chosen question to the anti-repetition ledger."""
        try:
            existing = self.load_used_questions()
            existing[question] = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "topic": topic[:80],
                "hook_type": hook_type,
                "channel": channel,
            }
            self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.ledger_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
            log.info("✓ QuestionCraftingAgent: Persisted question to ledger.")
        except Exception as e:
            log.warning("QuestionCraftingAgent: Could not persist to ledger (%s)", e)

    # ── LLM Generation ──────────────────────────────────────────────────────

    def _generate_candidates(
        self,
        thesis: str,
        hook_type: str,
        topic_keywords: str,
        used_sample: List[str],
        temperature: float = 0.80,
    ) -> List[str]:
        """Call LLM to generate 3 candidate question hooks."""
        prompt = _build_generation_prompt(thesis, hook_type, topic_keywords, used_sample)
        raw = self._call_llm(prompt, temperature=temperature)
        if not raw:
            return []
        try:
            data = self._extract_json(raw)
            candidates = data.get("candidates", [])
            if isinstance(candidates, list):
                return [c.strip() for c in candidates if isinstance(c, str) and c.strip()]
        except Exception as e:
            log.debug("QuestionCraftingAgent: Could not parse LLM candidates (%s)", e)
        return []

    def _call_llm(self, prompt: str, temperature: float = 0.80) -> Optional[str]:
        """Minimal LLM call with key rotation."""
        try:
            from src.agents.script_agent import _get_api_clients
            from google.genai import types as genai_types
            clients = _get_api_clients()
            models = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite"]
            for model_name in models:
                for client in clients:
                    try:
                        cfg: Dict[str, Any] = {"temperature": temperature, "max_output_tokens": 400}
                        if "gemini" in model_name:
                            cfg["response_mime_type"] = "application/json"
                        resp = client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=genai_types.GenerateContentConfig(**cfg),
                        )
                        if resp and resp.text:
                            return resp.text
                    except Exception as e:
                        log.debug("QuestionCraftingAgent LLM attempt (%s): %s", model_name, e)
                        continue
        except Exception as e:
            log.warning("QuestionCraftingAgent: LLM call failed (%s)", e)
        return None

    @staticmethod
    def _extract_json(text: str) -> dict:
        text = text.strip()
        if "```" in text:
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
            text = re.sub(r"\s*```\s*$", "", text, flags=re.MULTILINE)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError("No JSON found")
        return json.loads(text[start:end])

    # ── Scoring & Selection ─────────────────────────────────────────────────

    def _score_specificity(self, question: str) -> int:
        """Score 0–100. Higher = more specific and personal."""
        if not question or not question.endswith("?"):
            return 0
        words = question.split()
        if not (6 <= len(words) <= 13):
            return 0

        q_lower = question.lower()

        # Mandatory: must contain "you" or "your"
        if "you" not in q_lower and "your" not in q_lower:
            return 0

        score = 30  # base

        for term, bonus in SPECIFICITY_BONUS.items():
            if term in q_lower:
                score += bonus

        for term, penalty in GENERIC_PENALTY.items():
            if term in q_lower:
                score += penalty  # penalty is negative

        # Reward numbers/rupee amounts
        if re.search(r"\d+", question):
            score += 12
        if re.search(r"₹\s*\d+|\d+\s*lakh|\d+\s*crore|\d+%", q_lower):
            score += 8

        return max(0, min(100, score))

    def _is_repeated(self, question: str, used: Dict[str, Any]) -> Tuple[bool, float, str]:
        """Check if question is too similar to an existing ledger entry."""
        max_score = 0.0
        closest = ""
        q_lower = question.lower()
        for existing_q in used.keys():
            score = fuzz.token_sort_ratio(q_lower, existing_q.lower())
            if score > max_score:
                max_score = score
                closest = existing_q
        is_dup = max_score >= _DEDUP_THRESHOLD
        return is_dup, max_score / 100.0, closest

    def _select_best(self, candidates: List[str], used: Dict[str, Any]) -> Optional[str]:
        """Pick the highest-scoring non-repeated candidate."""
        scored = []
        for c in candidates:
            is_dup, sim, closest = self._is_repeated(c, used)
            if is_dup:
                log.info(
                    "  ↳ Rejected (%.0f%% similar to existing): '%s' ≈ '%s'",
                    sim * 100, c[:60], closest[:50],
                )
                continue
            score = self._score_specificity(c)
            if score > 0:
                scored.append((score, c))
                log.debug("  ↳ Candidate score=%d: '%s'", score, c)

        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    # ── Fallbacks ───────────────────────────────────────────────────────────

    def _topic_map_fallback(self, topic_text: str, used: Dict[str, Any]) -> Optional[str]:
        """Find best matching entry in TOPIC_QUESTION_MAP that isn't repeated."""
        topic_lower = topic_text.lower()
        matched: List[Tuple[int, str]] = []

        for keyword, question in TOPIC_QUESTION_MAP.items():
            if keyword in topic_lower:
                is_dup, _, _ = self._is_repeated(question, used)
                if not is_dup:
                    # Score by keyword length (longer keyword = more specific match)
                    matched.append((len(keyword), question))

        if matched:
            matched.sort(key=lambda x: x[0], reverse=True)
            return matched[0][1]
        return None

    def _emergency_fallback(self, thesis: str) -> str:
        """Absolute last resort — still ends with ? and contains you."""
        # Extract the most meaningful noun from the thesis
        words = [w for w in thesis.split() if len(w) > 4 and w.lower() not in
                 {"about", "these", "those", "their", "there", "where", "which", "hidden", "market"}]
        subject = words[0] if words else "investment"
        return f"Is your {subject.lower()} secretly working against you right now?"
