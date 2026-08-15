import os
import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

NVIDIA_NIM_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
DEFAULT_NVIDIA_MODELS = [
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.1-70b-instruct",
    "mistralai/mistral-7b-instruct-v0.3"
]

class NvidiaClient:
    """
    High-performance creative & reasoning engine using NVIDIA NIM APIs.
    Used for viral hook brainstorming, debate script generation, and high-CTR title engineering.
    """
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("NVIDIA_API_KEY") or "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"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def generate_text(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 1500) -> str:
        """Generates text from NVIDIA NIM model with multi-model fallback."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        for model in DEFAULT_NVIDIA_MODELS:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            try:
                res = requests.post(NVIDIA_NIM_URL, headers=self.headers, json=payload, timeout=20)
                if res.status_code == 200:
                    data = res.json()
                    content = data["choices"][0]["message"]["content"]
                    return content.strip()
                else:
                    logger.warning(f"NVIDIA model {model} returned {res.status_code}: {res.text[:120]}")
            except Exception as e:
                logger.warning(f"NVIDIA model {model} attempt failed: {e}")

        raise RuntimeError("All NVIDIA NIM models failed.")

    def generate_json(self, prompt: str, system_prompt: Optional[str] = None, temperature: float = 0.4) -> Dict[str, Any]:
        """Generates and parses structured JSON output."""
        json_sys_prompt = (
            (system_prompt or "") + 
            "\nCRITICAL: You MUST respond ONLY with a single valid JSON object. Do not include markdown codeblocks or text outside the JSON."
        )
        raw_text = self.generate_text(prompt, system_prompt=json_sys_prompt, temperature=temperature)
        
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace != -1:
            cleaned = cleaned[first_brace:last_brace+1]

        return json.loads(cleaned)
