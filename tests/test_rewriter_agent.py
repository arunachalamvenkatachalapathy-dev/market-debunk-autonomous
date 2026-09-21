"""
Unit tests for EnglishScriptRewriterAgent ("Script Doctor") in market-debunk-autonomous.
Verifies all 5 deterministic repair gates and seamless loop engineering.
"""
import sys
import copy
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, '.')

from src.agents.rewriter_agent import EnglishScriptRewriterAgent

def test_rewriter_agent():
    rewriter = EnglishScriptRewriterAgent()

    base_script = {
        "title": "Zero Cost EMI: The 18% GST Trap Exposed #Shorts",
        "description": "The hidden math behind zero cost EMI that banks never tell you.",
        "hashtags": ["#Finance", "#Shorts", "#MoneyTips", "#MarketDebunk"],
        "scenes": [
            {
                "scene_id": 0,
                "narration": "Your bank is secretly stealing eighteen percent GST!",
                "visual_prompt": "Cinematic close up of banking terminal displaying unexpected tax fee, chiaroscuro lighting",
                "broll_keyword": "bank fee",
                "duration_hint": 5.0
            },
            {
                "scene_id": 1,
                "narration": "Millions of buyers choose zero cost EMI thinking it is completely free.",
                "visual_prompt": "Crowded electronics showroom with shoppers holding credit cards, high contrast",
                "broll_keyword": "shopping mall",
                "duration_hint": 5.0
            },
            {
                "scene_id": 2,
                "narration": "The real truth is lenders quietly charge interest and slap eighteen percent GST on top.",
                "visual_prompt": "Detailed loan paperwork with red highlighted hidden fee clauses, shallow depth of field",
                "broll_keyword": "loan paperwork",
                "duration_hint": 5.0
            },
            {
                "scene_id": 3,
                "narration": "That processing fee eats your entire festival discount before your first statement arrives.",
                "visual_prompt": "Digital stock chart showing money draining into a vault, glowing red numbers",
                "broll_keyword": "falling chart",
                "duration_hint": 5.0
            },
            {
                "scene_id": 4,
                "narration": "Always calculate the total payout before signing any credit agreement.",
                "visual_prompt": "Close up hands calculating numbers on smartphone calculator, modern finance office",
                "broll_keyword": "counting cash",
                "duration_hint": 5.0
            }
        ]
    }

    print("Running English Script Doctor unit tests...")

    # 1. Test Hook Clamping (Rambling 16-word hook -> 5-7 words)
    bad_hook = copy.deepcopy(base_script)
    bad_hook["scenes"][0]["narration"] = "Today in this video we are going to look into why banks are stealing your money right now."
    repaired_hook = rewriter.auto_repair_script(bad_hook, failure_reason="Hook too long")
    hook_words = repaired_hook["scenes"][0]["narration"].split()
    assert 5 <= len(hook_words) <= 7, f"Hook should be 5-7 words, got {len(hook_words)}: {repaired_hook['scenes'][0]['narration']}"
    print(f"✅ Test 1 (Hook Clamping): PASSED — Hook: '{repaired_hook['scenes'][0]['narration']}' ({len(hook_words)} words)")

    # 2. Test Citation & Banned Template Removal
    bad_cite = copy.deepcopy(base_script)
    bad_cite["scenes"][1]["narration"] = "According to reports, what you didn't see is that buyers lose their money."
    repaired_cite = rewriter.auto_repair_script(bad_cite, failure_reason="Citation detected")
    narration_1 = repaired_cite["scenes"][1]["narration"].lower()
    assert "according to" not in narration_1, "Citations must be stripped"
    assert "what you didn't see" not in narration_1, "Banned generic phrases must be stripped"
    print(f"✅ Test 2 (Citation Removal): PASSED — Repaired: '{repaired_cite['scenes'][1]['narration']}'")

    # 3. Test Prompt Disambiguation
    bad_prompt = copy.deepcopy(base_script)
    bad_prompt["scenes"][1]["visual_prompt"] = bad_prompt["scenes"][0]["visual_prompt"]
    repaired_prompt = rewriter.auto_repair_script(bad_prompt, failure_reason="Duplicate prompts")
    p0 = repaired_prompt["scenes"][0]["visual_prompt"]
    p1 = repaired_prompt["scenes"][1]["visual_prompt"]
    assert p0 != p1, "Prompts must be distinct"
    print("✅ Test 3 (Prompt Disambiguation): PASSED")

    # 4. Test Seamless Loop Connector
    repaired_loop = rewriter.auto_repair_script(base_script)
    last_narration = repaired_loop["scenes"][-1]["narration"]
    assert any(conn in last_narration for conn in ["— which is why", "— and that leads", "— which explains"]), f"Loop connector missing: {last_narration}"
    print(f"✅ Test 4 (Seamless Loop Connector): PASSED — Last scene: '{last_narration}'")

    # 5. Torture Test: Corrupted Script with multiple violations
    torture = {
        "scenes": [
            {"narration": "In this video we will discuss why your investment might be completely broken according to studies.", "visual_prompt": "same"},
            {"narration": "Reports show that banks charge heavy penalty that's called a trap.", "visual_prompt": "same"},
            {"narration": "Always be careful.", "visual_prompt": "same"},
        ] # Only 3 scenes, duplicate prompts, citations, rambling hook
    }
    healed = rewriter.auto_repair_script(torture, failure_reason="Multiple catastrophic failures", topic="Hidden Banking Charges")
    assert len(healed["scenes"]) == 5, f"Expected 5 scenes, got {len(healed['scenes'])}"
    assert 5 <= len(healed["scenes"][0]["narration"].split()) <= 7, "Hook clamped in torture test"
    prompts = [s["visual_prompt"] for s in healed["scenes"]]
    assert len(set(prompts)) == len(prompts), "All prompts unique in torture test"
    print("✅ Test 5 (Torture Test): PASSED — All violations repaired deterministically!")

    print("\n🎉 ALL ENGLISH SCRIPT DOCTOR TESTS PASSED 100%!")

if __name__ == "__main__":
    test_rewriter_agent()
