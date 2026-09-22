import json
import pytest
from pathlib import Path
from src.agents.question_agent import QuestionCraftingAgent

def test_question_ends_with_question_mark():
    agent = QuestionCraftingAgent()
    q = agent._topic_map_fallback("sip expense ratio", {})
    assert q.endswith("?")

def test_question_contains_you_or_your():
    agent = QuestionCraftingAgent()
    q = agent._topic_map_fallback("mutual fund", {})
    assert "you" in q.lower() or "your" in q.lower()

def test_anti_repetition_blocks_duplicate():
    agent = QuestionCraftingAgent()
    used = {"Is your SIP silently charging more than you were promised?": {}}
    is_dup, score, match = agent._is_repeated("Is your SIP silently charging more than you were promised?", used)
    assert is_dup is True

def test_specificity_scorer_rewards_product_names():
    agent = QuestionCraftingAgent()
    score1 = agent._score_specificity("Is your money at risk?")
    score2 = agent._score_specificity("Is your SIP silently eating 2% of your returns?")
    assert score2 > score1

def test_question_not_generic():
    agent = QuestionCraftingAgent()
    assert agent._score_specificity("Did you know your bank charges fees?") == 0

def test_topic_question_map_covers_all_traps():
    from src.agents.question_agent import TOPIC_QUESTION_MAP
    assert len(TOPIC_QUESTION_MAP) >= 20
    assert "sip" in TOPIC_QUESTION_MAP
    assert "emi" in TOPIC_QUESTION_MAP
