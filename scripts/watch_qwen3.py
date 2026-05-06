"""
Qwen3 Model Watch & Auto-Reload
Polls Ollama every 30s. When a new qwen3 model appears, hits /chat endpoint
to trigger llm.check_availability() and update tier_models.
"""
import time
import requests
import sys

API = "http://localhost:8765"
OLLAMA = "http://localhost:11434"
TARGET_MODELS = {"qwen3:1.7b", "qwen3:4b", "qwen3:8b"}
seen = set()

print("🔍 Watching for Qwen3 model downloads to complete...")

while True:
    try:
        r = requests.get(f"{OLLAMA}/api/tags", timeout=5)
        available = {m["name"] for m in r.json().get("models", [])}
        qwen3_ready = available & TARGET_MODELS
        new = qwen3_ready - seen

        if new:
            print(f"✅ New Qwen3 models ready: {new}")
            seen |= new
            # Trigger backend to re-check and reassign tiers
            try:
                requests.get(f"{API}/health", timeout=5)
                print(f"   → Pinged JARVIS backend to refresh tier assignments.")
            except Exception:
                pass

        if qwen3_ready:
            print(f"   Qwen3 ready: {qwen3_ready} | Waiting for: {TARGET_MODELS - qwen3_ready}")

        if TARGET_MODELS <= available:
            print("🎉 All 3 Qwen3 models downloaded! JARVIS is now running full Qwen3 stack.")
            print("   Restart the JARVIS backend once for clean tier assignment.")
            sys.exit(0)

    except Exception as e:
        print(f"   [poll error] {e}")

    time.sleep(30)
