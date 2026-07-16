import requests
import json

token = "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"
parent_id = "39e84103-6e80-81b1-a4c1-dbe8984f92db" # The project hub page

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# The content we want to push
blocks = [
    {
        "object": "block",
        "type": "heading_1",
        "heading_1": {
            "rich_text": [{"type": "text", "text": {"content": "Multi-Agent Workflow Implementation Complete"}}]
        }
    },
    {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": "The codebase has been successfully overhauled to align precisely with the framework rules. The video factory is now orchestrated autonomously by three distinct AI Agents:"}}]
        }
    },
    {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": "Prompt Engineer Agent: Fetches fresh topics and generates strict 5-scene JSON scripts with constraints on the Hook length and mascot state cues."}}]
        }
    },
    {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": "Evaluator Agent: Implements Pre-Flight (hook length, no citations) and Post-Flight checks (audio duration match and LUFS loudness)."}}]
        }
    },
    {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {
            "rich_text": [{"type": "text", "text": {"content": "Manager Agent: Delegates to the sub-agents and handles error retries."}}]
        }
    },
    {
        "object": "block",
        "type": "heading_2",
        "heading_2": {
            "rich_text": [{"type": "text", "text": {"content": "Visual Framework Upgrades"}}]
        }
    },
    {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [{"type": "text", "text": {"content": "• Replaced Veo/Imagen with free Pollinations.ai (navy blue/vibrant orange color grade enforced).\n• FFmpeg assembly now handles Mascot overlays (center-bottom), Logo (top-right), Subtitles (60-75% bottom), and Loudness (-14 LUFS)."}}]
        }
    }
]

payload = {
    "parent": {"page_id": parent_id},
    "properties": {
        "title": {
            "title": [{"type": "text", "text": {"content": "Architecture Walkthrough (Antigravity IDE)"}}]
        }
    },
    "children": blocks
}

res = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)
if res.status_code == 200:
    print("Successfully pushed to Notion!")
else:
    print("Error:", res.status_code, res.text)
