import json
import sys
import asyncio
import os
import time
from pathlib import Path

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from src.agents import voice_agent, visual_agent
from src.rendering import subtitles, assembler

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def run():
    # We bypass the LLM and hardcode a short 10-second test script
    script_dict = {
        "title": "Stop Fighting the Market (Short Test)",
        "scenes": [
            {
                "scene_id": 1,
                "narration": "Ramesh bought a stock at 500 rupees. Now it's at 300.",
                "visual_prompt": "Ramesh looking at a stock chart showing a drop from 500 to 300 rupees."
            },
            {
                "scene_id": 2,
                "narration": "Stop fighting the market. Start fighting your own psychology.",
                "visual_prompt": "looking calm and confident into the camera lens, mastering his psychology, warm lighting on his face."
            }
        ]
    }

    run_id = f'RUN_LOSS_AVERSION_{int(time.time())}'
    run_dir = Path('output') / run_id
    audio_dir = run_dir / 'audio'
    visuals_dir = run_dir / 'visuals'
    clips_dir = run_dir / 'clips'

    run_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(exist_ok=True)
    visuals_dir.mkdir(exist_ok=True)
    clips_dir.mkdir(exist_ok=True)

    with open(run_dir / 'script.json', 'w', encoding='utf-8') as f:
        json.dump(script_dict, f, indent=2, ensure_ascii=False)

    print(f'[1/4] Synthesizing voice (en-IE-ConnorNeural)...')
    voice_results = voice_agent.synthesize_all_scenes(script_dict['scenes'], audio_dir)
    print(f'[1/4] Voice done — {len(voice_results)} scenes')

    print("[2/4] Generating images dynamically using visual_agent...")
    visual_results = visual_agent.source_all_visuals(script_dict['scenes'], visuals_dir)
    print(f'[2/4] Images done — {len(visual_results)} scenes')

    print(f'[3/4] Building subtitles (Arial Black, 3-word chunks, bottom-center)...')
    ass_path = subtitles.generate_ass_file(voice_results, run_dir / 'subtitles.ass')
    print(f'[3/4] Subtitles done: {ass_path}')

    print(f'[4/4] Assembling final video...')
    assembler.assemble_video(voice_results, visual_results, ass_path, run_dir)
    final_video = run_dir / 'distribution_ready.mp4'
    print(f'[DONE] Final video: {final_video.absolute()}')
    print(f'       Size: {final_video.stat().st_size // 1024} KB')


run()
