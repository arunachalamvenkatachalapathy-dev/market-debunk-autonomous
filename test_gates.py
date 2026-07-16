"""Quick smoke test for all Evaluator gates with mock data."""
import sys
sys.path.insert(0, '.')
from src.agents.evaluator import EvaluatorAgent
from src.agents.evaluator_report import EvaluatorReport

eval_agent = EvaluatorAgent()
report = EvaluatorReport(topic='Test topic')

# --- GATE 1: Topic ---
p, r, d = eval_agent.gate_topic('Is SIP really the safest way to invest in mutual funds in 2026?')
report.record_gate('topic', p, r, d)
print(f"TOPIC: passed={p} | {r}")

# --- GATE 2: Script (GOOD) ---
good_script = {
    'title': 'SIP Myth Busted',
    'description': 'The truth about SIP #finance #shorts',
    'scenes': [
        {'narration': 'SIP is SAFE? Think again.', 'visual_prompt': 'vault with gold bars', 'visual_category': 'vaults', 'arrow_state': 'arrow_up'},
        {'narration': 'Every month millions pour money into SIPs thinking they cannot lose.', 'visual_prompt': 'crowded stock exchange floor', 'visual_category': 'crowds', 'arrow_state': 'arrow_up'},
        {'narration': 'But here is what nobody tells you about market timing and SIP returns.', 'visual_prompt': 'stack of financial documents', 'visual_category': 'paperwork', 'arrow_state': 'arrow_up'},
        {'narration': 'SIPs can LOSE money in a sideways market for YEARS. Your returns are not guaranteed.', 'visual_prompt': 'declining stock chart on digital screen', 'visual_category': 'digital', 'arrow_state': 'arrow_down'},
        {'narration': 'So diversify. Do not put all eggs in one basket. That is the REAL secret.', 'visual_prompt': 'hands holding diverse portfolio', 'visual_category': 'hands', 'arrow_state': 'arrow_down'}
    ]
}
p, r, d = eval_agent.gate_script(good_script)
report.record_gate('script', p, r, d)
print(f"SCRIPT (good): passed={p} | {r} | runtime={d.get('est_runtime')}s")

# --- GATE 2: Script (BAD - citation) ---
import copy
bad_cite = copy.deepcopy(good_script)
bad_cite['scenes'][2]['narration'] = 'According to experts, markets are cyclical and SIPs follow.'
p, r, _ = eval_agent.gate_script(bad_cite)
print(f"SCRIPT (bad citation): passed={p} | {r}")

# --- GATE 2: Script (BAD - long hook) ---
bad_hook = copy.deepcopy(good_script)
bad_hook['scenes'][0]['narration'] = 'This is a very long hook that has way too many words in it definitely bad.'
p, r, d = eval_agent.gate_script(bad_hook)
print(f"SCRIPT (bad hook): passed={p} | {r} | hook_words={d.get('hook_word_count')}")

# --- GATE 2: Script (BAD - category repeat) ---
bad_cat = copy.deepcopy(good_script)
bad_cat['scenes'][1]['visual_category'] = 'vaults'  # same as scene 0
p, r, d = eval_agent.gate_script(bad_cat)
print(f"SCRIPT (bad category): passed={p} | {r}")

# --- GATE 5: Mascot (GOOD) ---
good_mascot = {
    'flip_scene': 4,
    'segments': [
        {'scene_number': 1, 'arrow_state': 'arrow_up', 'transition_rationale': 'Setup', 'position_x': '(W-w)/2', 'position_y': 'H-h-250'},
        {'scene_number': 2, 'arrow_state': 'arrow_up', 'transition_rationale': 'Building', 'position_x': '(W-w)/2', 'position_y': 'H-h-250'},
        {'scene_number': 3, 'arrow_state': 'arrow_up', 'transition_rationale': 'Tension', 'position_x': '(W-w)/2', 'position_y': 'H-h-250'},
        {'scene_number': 4, 'arrow_state': 'arrow_down', 'transition_rationale': 'REVEAL', 'position_x': '(W-w)/2', 'position_y': 'H-h-250'},
        {'scene_number': 5, 'arrow_state': 'arrow_down', 'transition_rationale': 'CTA', 'position_x': '(W-w)/2', 'position_y': 'H-h-250'},
    ]
}
p, r, d = eval_agent.gate_mascot(good_mascot, good_script)
report.record_gate('mascot', p, r, d)
print(f"MASCOT (good): passed={p} | {r}")

# --- GATE 5: Mascot (BAD - flip wrong) ---
bad_mascot = copy.deepcopy(good_mascot)
bad_mascot['segments'][3]['arrow_state'] = 'arrow_up'  # should be down at flip
p, r, d = eval_agent.gate_mascot(bad_mascot, good_script)
print(f"MASCOT (bad flip): passed={p} | {r}")

# --- GATE 8: Publish Metadata (GOOD) ---
good_meta = {
    'youtube_titles': ['SIP Myth BUSTED #Shorts', 'Your SIP Is LOSING Money #Shorts', 'Nobody Tells You This About SIP #Shorts'],
    'youtube_description': 'The truth about SIP investing that nobody tells you. #finance #sip #investing #myth #shorts #india #market',
    'youtube_tags': ['shorts', 'finance', 'sip', 'investing', 'myth', 'india', 'market', 'stocks'],
    'telegram_caption': 'Your SIP might be LOSING money #MarketDebunk #Finance',
    'instagram_description': 'The myth about SIP investing BUSTED #sip #finance #investing #market #india #shorts #viral',
    'category_id': '27'
}
p, r, d = eval_agent.gate_publish_metadata(good_meta)
report.record_gate('publish_metadata', p, r, d)
print(f"PUBLISH META (good): passed={p} | {r}")

# --- GATE 8: Publish Metadata (BAD - too few titles) ---
bad_meta = copy.deepcopy(good_meta)
bad_meta['youtube_titles'] = ['Only one title #Shorts']
p, r, d = eval_agent.gate_publish_metadata(bad_meta)
print(f"PUBLISH META (bad titles): passed={p} | {r}")

# --- REPORT ---
print()
report.print_summary()
print()
print(f"RECOMMENDATION: {report.get_recommendation()}")
