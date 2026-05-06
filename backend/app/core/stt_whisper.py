"""
Local speech-to-text using faster-whisper (optional dependency).
Model is loaded lazily on first transcription to keep startup fast.
"""
from __future__ import annotations

import logging
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Optional

logger = logging.getLogger("JAR.STT")

_STT_IMPORT_OK = False
if TYPE_CHECKING:
    from faster_whisper import WhisperModel

try:
    from faster_whisper import WhisperModel as _WhisperModel

    _STT_IMPORT_OK = True
except ImportError:
    _WhisperModel = None  # type: ignore[misc, assignment]

_model: Optional["WhisperModel"] = None
_model_lock = Lock()


def stt_import_ok() -> bool:
    return _STT_IMPORT_OK


def _get_model():
    global _model
    if not _STT_IMPORT_OK:
        raise RuntimeError("faster-whisper is not installed")
    with _model_lock:
        if _model is None:
            from app.config import (
                JAR_WHISPER_COMPUTE_TYPE,
                JAR_WHISPER_DEVICE,
                JAR_WHISPER_MODEL,
            )

            logger.info(
                "Loading Whisper STT model %r (device=%s, compute_type=%s)",
                JAR_WHISPER_MODEL,
                JAR_WHISPER_DEVICE,
                JAR_WHISPER_COMPUTE_TYPE,
            )
            _model = _WhisperModel(
                JAR_WHISPER_MODEL,
                device=JAR_WHISPER_DEVICE,
                compute_type=JAR_WHISPER_COMPUTE_TYPE,
            )
        return _model


def transcribe_file(
    audio_path: Path,
    *,
    language: Optional[str] = None,
) -> str:
    """
    Transcribe a short audio file (webm/wav/mp3/…). Requires ffmpeg for many formats.
    """
    path = audio_path.resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))

    model = _get_model()
    lang = language
    segments, _info = model.transcribe(
        str(path),
        language=lang,
        beam_size=5,
        vad_filter=True,
    )
    parts = [s.text.strip() for s in segments if s.text and s.text.strip()]
    return " ".join(parts).strip()
