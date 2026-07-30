import os
import sys
from google.genai import Client

sys.path.insert(0, os.getcwd())
from src.agents.prompt_engineer import PromptEngineerAgent

gemini_key = os.getenv("GEMINI_API_KEY")
if not gemini_key:
    # Try reading from config or env
    print("GEMINI_API_KEY not set in env, initializing mock/key client...")
    
client = Client(api_key=gemini_key) if gemini_key else None
pe = PromptEngineerAgent(client)

try:
    topic = pe.fetch_fresh_topic()
    print("=" * 60)
    print("FETCHED TOPIC SUCCESS:")
    print(topic)
    print("=" * 60)
except Exception as e:
    print("LOCAL TOPIC ERROR:", e)
