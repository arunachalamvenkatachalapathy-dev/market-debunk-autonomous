import sys, os
sys.path.insert(0, os.getcwd())
import logging

logging.basicConfig(level=logging.INFO)
from src.agents.manager import ManagerAgent

mgr = ManagerAgent()
pe = mgr.prompt_engineer
print("\n--- TESTING MULTI-CHANNEL INGESTION ---")
topic = pe.fetch_fresh_topic()
print(f"\n✅ FETCHED TOPIC SUCCESS:\n{topic}")
