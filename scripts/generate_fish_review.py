"""Generate a review-only MP3 with Fish's S2.1 Pro Free developer API.

Usage: FISH_AUDIO_API_KEY=<secret from a protected runner> python scripts/generate_fish_review.py \
  --text-file script.txt --output /tmp/review.mp3
Never place a key in source, arguments, logs, or artifacts. No publishing here.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import random
import time

import requests

ENDPOINT = "https://api.fish.audio/v1/tts"
MODEL = "s2.1-pro-free"
ELITE = "d8a1340984ee4b63ad1ffae27a6a4339"


def generate(text: str, destination: Path, api_key: str, *, reference_id=ELITE, session=None, sleep=time.sleep) -> Path:
    if not text.strip() or not api_key.strip():
        raise ValueError("Text and FISH_AUDIO_API_KEY are required")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite {destination}")
    client = session or requests
    payload = {
        "text": text.strip(), "reference_id": reference_id, "format": "mp3",
        "temperature": 0.7, "top_p": 0.7, "prosody": {"speed": 1.0, "volume": 0},
        "chunk_length": 300, "normalize": True, "latency": "normal",
    }
    headers = {"Authorization": f"Bearer {api_key.strip()}", "Content-Type": "application/json", "model": MODEL}
    for attempt in range(4):
        try:
            res = client.post(ENDPOINT, json=payload, headers=headers, timeout=120)
        except requests.RequestException as exc:
            if attempt == 3:
                raise RuntimeError("Fish request failed after retries") from exc
            sleep(2 ** attempt + random.random())
            continue
        if res.status_code == 200:
            if len(res.content) < 1000 or not (res.content[:3] == b"ID3" or res.content[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")):
                raise RuntimeError("Fish returned no recognizable MP3; output not saved")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(res.content)
            return destination
        if res.status_code in (500, 502, 503, 504) and attempt < 3:
            sleep(2 ** attempt + random.random())
            continue
        # Do not print the response body: providers sometimes echo input or secrets.
        raise RuntimeError(f"Fish TTS HTTP {res.status_code}; output not saved")
    raise RuntimeError("Fish retries exhausted")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reference-id", default=ELITE, help="Fish library voice ID")
    args = parser.parse_args()
    generate(args.text_file.read_text(encoding="utf-8"), args.output, os.environ.get("FISH_AUDIO_API_KEY", ""), reference_id=args.reference_id)
    print(f"Review audio saved: {args.output}")


if __name__ == "__main__":
    main()
