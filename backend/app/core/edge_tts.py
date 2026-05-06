"""
Microsoft Edge neural TTS (via edge-tts). Requires outbound HTTPS to Microsoft.
"""
from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger("JAR.EdgeTTS")

try:
    import edge_tts

    EDGE_TTS_AVAILABLE = True
except ImportError:  # pragma: no cover
    edge_tts = None  # type: ignore
    EDGE_TTS_AVAILABLE = False

_voices_cache: Optional[List[Dict[str, Any]]] = None
_voices_cache_expiry: float = 0.0
_VOICES_TTL_SEC = 600.0


async def list_edge_voices() -> List[Dict[str, Any]]:
    """Return cached Microsoft Edge voices (id, name, locale, gender)."""
    global _voices_cache, _voices_cache_expiry
    if not EDGE_TTS_AVAILABLE:
        return []
    now = time.monotonic()
    if _voices_cache is not None and now < _voices_cache_expiry:
        return _voices_cache

    raw = await edge_tts.list_voices()
    out: List[Dict[str, Any]] = []
    for v in raw:
        out.append(
            {
                "id": v.get("ShortName", ""),
                "name": (v.get("FriendlyName") or v.get("ShortName") or "").strip(),
                "locale": (v.get("Locale") or "").strip(),
                "gender": (v.get("Gender") or "").strip(),
            }
        )
    out.sort(key=lambda x: (x.get("locale") or "", x.get("id") or ""))
    _voices_cache = out
    _voices_cache_expiry = now + _VOICES_TTL_SEC
    logger.info("Edge TTS voice list refreshed (%d voices).", len(out))
    return out


async def stream_edge_mp3(text: str, voice: str) -> AsyncIterator[bytes]:
    """Stream MP3 chunks from Edge TTS."""
    if not EDGE_TTS_AVAILABLE:
        raise RuntimeError("edge-tts is not installed")
    communicate = edge_tts.Communicate(text, voice=voice)
    async for chunk in communicate.stream():
        if chunk.get("type") == "audio" and chunk.get("data"):
            yield chunk["data"]
