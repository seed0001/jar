"""
JAR — Centralized Configuration
Loads from .env with sensible defaults for local Ollama deployment.
Vision removed; Edge TTS + optional local Whisper STT are wired from the API.
"""
import json
import os
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

_root = Path(__file__).parent.parent.parent
load_dotenv(_root / ".env")

# Repository root (default sandbox for file reads)
REPO_ROOT = _root

# Local tools (/chat): file read roots, web search, system snapshots
# Comma-separated absolute paths; empty = repo only.
JAR_ALLOWED_READ_PATHS = os.getenv("JAR_ALLOWED_READ_PATHS", "").strip()
JAR_FILE_READ_MAX_BYTES = int(os.getenv("JAR_FILE_READ_MAX_BYTES", "524288"))
JAR_PROCESS_LIMIT = int(os.getenv("JAR_PROCESS_LIMIT", "48"))
JAR_TOOL_HEURISTICS = os.getenv("JAR_TOOL_HEURISTICS", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "",
)

# ── LLM ────────────────────────────────────────────────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

_DEFAULT_MODEL = os.getenv("OLLAMA_DEFAULT_MODEL", "llama2-uncensored").strip() or "llama2-uncensored"
TIER_MODELS_PATH = _root / "jar_tier_models.json"


def load_tier_models_config() -> Dict[int, str]:
    """
    Tier 1 = fastest / light reasoning, 2 = balanced, 3 = deepest.
    Order: .env defaults → jar_tier_models.json overrides (if present).
    """
    out = {
        1: os.getenv("OLLAMA_MODEL_TIER1", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL,
        2: os.getenv("OLLAMA_MODEL_TIER2", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL,
        3: os.getenv("OLLAMA_MODEL_TIER3", _DEFAULT_MODEL).strip() or _DEFAULT_MODEL,
    }
    if TIER_MODELS_PATH.exists():
        try:
            data = json.loads(TIER_MODELS_PATH.read_text(encoding="utf-8"))
            for k in (1, 2, 3):
                sk = str(k)
                val = data.get(sk) or data.get(k)
                if val and str(val).strip():
                    out[k] = str(val).strip()
        except (json.JSONDecodeError, OSError, TypeError):
            pass
    return out

# ── Memory ─────────────────────────────────────────────────────────────────────
DB_PATH          = REPO_ROOT / "jar_memory.db"
SKILLS_DIR       = REPO_ROOT / "skills"
BUFFER_LIMIT     = int(os.getenv("BUFFER_LIMIT", "20"))
CONTEXT_PROFILES = int(os.getenv("CONTEXT_PROFILES", "5"))

# ── Edge TTS (Microsoft neural voices via edge-tts) ───────────────────────────
EDGE_TTS_DEFAULT_VOICE = os.getenv("EDGE_TTS_DEFAULT_VOICE", "en-GB-ThomasNeural").strip()

# ── Local STT (faster-whisper; POST /voice/transcribe) ─────────────────────────
# WHISPER_MODEL is supported for backward compatibility with existing .env files.
JAR_WHISPER_MODEL = (
    os.getenv("JAR_WHISPER_MODEL", "").strip()
    or os.getenv("WHISPER_MODEL", "base.en").strip()
    or "base.en"
)
JAR_WHISPER_DEVICE = os.getenv("JAR_WHISPER_DEVICE", "cpu").strip() or "cpu"
JAR_WHISPER_COMPUTE_TYPE = os.getenv("JAR_WHISPER_COMPUTE_TYPE", "int8").strip() or "int8"

# ── System ─────────────────────────────────────────────────────────────────────
CPU_THROTTLE_PCT = int(os.getenv("CPU_THROTTLE_PCT", "85"))
