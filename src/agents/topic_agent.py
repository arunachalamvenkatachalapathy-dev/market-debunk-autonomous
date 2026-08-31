"""
src/agents/topic_agent.py

Phase 1 — Topic Discovery
This agent uses Gemini (Vertex AI) to generate an original, highly engaging
financial story seed, ensuring full copyright and YouTube ToS compliance.
No scraping of competitor transcripts is performed.
"""
import json
import re
import random
from typing import Optional
from datetime import datetime

from google import genai

from src.utils.config import settings
from src.utils.logger import get_logger

log = get_logger(__name__, phase="topic_discovery")

# List of high-level finance topics for Gemini to choose from
FINANCE_TOPICS = [
    "Expense Ratios and Hidden Mutual Fund Fees",
    "The dangers of blindly following stock tips on Telegram",
    "Why Option Trading destroys retail wealth",
    "The reality of IPO flipping and listing gains",
    "SIP vs Lumpsum during all-time highs",
    "The trap of high-dividend yield stocks",
    "Why real estate isn't always the best investment",
    "The psychology of panic selling",
    "How inflation quietly eats your savings account",
    "The sunk cost fallacy in holding losing stocks",
    "Understanding compounding vs simple interest",
    "The reality of 'guaranteed return' insurance policies"
]

def _fallback_story_seed(topic: str) -> dict:
    """Minimal fallback when LLM fails."""
    return {
        "thesis": f"The hidden truth about {topic}",
        "story_seed": {
            "inciting_event": f"Arjun realizes his {topic.lower()} strategy isn't working as expected.",
            "protagonist_flaw": "He trusted conventional advice without understanding the underlying mechanics.",
            "real_world_anchor": "Historical market data showing retail investor behavior.",
            "concept_name": "Market Mispricing",
            "concept_one_liner": "When prices don't reflect real value, savvy investors profit while others lose."
        }
    }

def discover_topic(day_override: Optional[int] = None) -> dict:
    """
    Generates an original financial story seed using Gemini directly.
    Replaces the old YouTube scraping method to ensure full copyright and ToS compliance.
    """
    log.info("Generating original financial topic via Gemini...")
    
    # Pick a random high-level topic to ground the generation
    base_topic = random.choice(FINANCE_TOPICS)
    log.info("Selected base topic: %s", base_topic)

    prompt = f"""You are an elite financial content strategist and storyteller for an Indian YouTube Shorts channel.
Your task is to invent an original, highly engaging, and educational financial story seed based on this topic:
"{base_topic}"

Output ONLY a valid JSON object with exactly these keys:
{{
  "thesis": "One sentence (max 25 words): a controversial or provocative claim about this topic. Should make viewers say 'wait, really?!'",
  "story_seed": {{
    "inciting_event": "A specific, relatable everyday moment that sets up the story (e.g. 'Arjun checks his mutual fund app and his returns are 0% despite the Nifty being up 12%')",
    "protagonist_flaw": "The common mistake most people make, which Arjun will also make (e.g. 'He trusted his fund manager blindly and never checked the expense ratio')",
    "real_world_anchor": "A real, factual market dynamic, law, or historical trend that anchors this story in reality (e.g. 'Active funds charge up to 2% yearly, which compounds against you')",
    "concept_name": "The official finance term being explained (e.g. 'Expense Ratio Drag')",
    "concept_one_liner": "One plain-English sentence explaining what this concept means (e.g. 'Even when markets go up, hidden fund fees quietly eat your profits every year')"
  }}
}}

Output ONLY the JSON. No markdown fences, no explanation."""

    try:
        client = genai.Client(vertexai=True, project="exalted-shape-502013-q5", location="us-central1")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        raw_json = response.text.strip()
        if "```" in raw_json:
            raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json, flags=re.MULTILINE)
            raw_json = re.sub(r"\s*```\s*$", "", raw_json, flags=re.MULTILINE)
            
        result = json.loads(raw_json)
        
        thesis = result.get("thesis", "The truth about investing")
        story_seed = result.get("story_seed", {})
        
        log.info("Success! Generated original story seed | concept: %s", story_seed.get("concept_name", "?"))
        
        # We simulate a "video" for the orchestrator to pass deduplication
        video_id = f"ORIG_{int(random.random()*100000)}"
        return {
            "channel": "Market Debunk Original",
            "video_id": video_id,
            "video_title": f"Market Debunk on {story_seed.get('concept_name', 'Finance')}",
            "thesis": thesis,
            "story_seed": story_seed,
            "transcript_length": 0,
        }
        
    except Exception as exc:
        log.error("Gemini failed to generate original topic: %s. Using fallback.", exc)
        result = _fallback_story_seed(base_topic)
        return {
            "channel": "Market Debunk Original",
            "video_id": f"FALL_{int(random.random()*100000)}",
            "video_title": f"Market Debunk on {result['story_seed']['concept_name']}",
            "thesis": result["thesis"],
            "story_seed": result["story_seed"],
            "transcript_length": 0,
        }
