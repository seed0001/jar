"""
JAR — Ollama LLM Provider (three-tier model map)
Windows-optimised: 2048 ctx, 8 threads, 10-minute keep-alive.
Vision / TTS / Voice pipeline fully removed.
"""
import json
import logging
from typing import AsyncGenerator, List, Dict, Optional

import aiohttp
import requests

from app.config import OLLAMA_BASE_URL, load_tier_models_config

logger = logging.getLogger("JAR.LLM")

# ── Windows performance profile ───────────────────────────────────────────────
WIN_OPTIONS = {
    "num_ctx": 2048,
    "num_thread": 8,
    "keep_alive": "10m",
    "temperature": 0.7,
    "top_p": 0.9,
    "repeat_penalty": 1.05,
}


class OllamaProvider:
    def __init__(self):
        self.base_url = OLLAMA_BASE_URL
        self.is_available = False
        self.available_models: List[str] = []
        self._session: Optional[aiohttp.ClientSession] = None
        self._tier_models: Dict[int, str] = load_tier_models_config()

    def reload_tier_models(self) -> None:
        self._tier_models = load_tier_models_config()

    @property
    def tier_models(self) -> Dict[int, str]:
        return dict(self._tier_models)

    def get_model_for_tier(self, tier: int = 2) -> str:
        t = max(1, min(3, int(tier)))
        return self._tier_models.get(t) or self._tier_models.get(2, "llama2-uncensored")

    @property
    def model(self) -> str:
        """Default / display model (tier 2)."""
        return self.get_model_for_tier(2)

    # ── session management ────────────────────────────────────────────────────
    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ── availability check ────────────────────────────────────────────────────
    def check_availability(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            if r.status_code == 200:
                self.available_models = [m["name"] for m in r.json().get("models", [])]
                logger.info(f"Ollama online. Models: {self.available_models}")
                for tier, name in self._tier_models.items():
                    if name and not any(name in m for m in self.available_models):
                        logger.warning(
                            f"Tier {tier} model '{name}' not found in Ollama. "
                            f"Run: ollama pull {name}"
                        )
                self.is_available = True
                return True
        except Exception as e:
            logger.warning(f"Ollama unavailable: {e}")
        self.is_available = False
        return False

    # ── synchronous chat (used by internal reasoning helpers) ─────────────────
    def chat(self, messages: List[Dict], tier: int = 2, max_tokens: int = 1024) -> str:
        model = self.get_model_for_tier(tier)
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {**WIN_OPTIONS, "num_predict": max_tokens},
        }
        try:
            r = requests.post(
                f"{self.base_url}/api/chat", json=payload, timeout=180
            )
            r.raise_for_status()
            return r.json()["message"]["content"]
        except Exception as e:
            logger.error(f"LLM chat error: {e}")
            raise

    # ── async streaming chat — primary path for /chat endpoint ────────────────
    async def stream_chat(
        self,
        messages: List[Dict],
        tier: int = 2,
        max_tokens: int = 2048,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        model = self.get_model_for_tier(tier)
        logger.info(f"LLM stream_chat started for model {model} (tier {tier})")
        options = {**WIN_OPTIONS, "num_predict": max_tokens, "temperature": temperature}

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": options,
        }
        logger.info(f"Streaming → {model} (ctx={WIN_OPTIONS['num_ctx']})")

        try:
            session = await self.get_session()
            logger.info(f"Connecting to Ollama at {self.base_url}/api/chat...")
            async with session.post(
                f"{self.base_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=300),
            ) as resp:
                logger.info(f"Ollama response status: {resp.status}")
                resp.raise_for_status()
                logger.info("Starting to iterate over Ollama stream content...")
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if data.get("done"):
                            logger.info("Ollama stream marked as 'done'")
                            break
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to decode line: {line}")
                        continue
            logger.info("Finished iterating over Ollama stream")
        except Exception as e:
            logger.error(f"Stream error ({model}): {e}")
            yield f"\n\n*I do beg your pardon, Sir — the connection faltered. ({e})*"


llm = OllamaProvider()
