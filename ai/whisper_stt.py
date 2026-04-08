"""
faster-whisper based STT helpers.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_model = None
_model_runtime_key = ""
_last_stt_error = ""


def get_last_stt_error() -> str:
    return _last_stt_error


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _has_cuda() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _resolve_runtime(model_size: Optional[str] = None) -> tuple[str, str, str]:
    size = model_size or os.getenv("WHISPER_MODEL_SIZE", "small")
    req_device = os.getenv("WHISPER_DEVICE", "auto").strip().lower()
    req_compute = os.getenv("WHISPER_COMPUTE_TYPE", "auto").strip().lower()

    if req_device == "auto":
        device = "cuda" if _has_cuda() else "cpu"
    else:
        device = req_device

    if req_compute == "auto":
        compute = "float16" if device == "cuda" else "int8"
    else:
        compute = req_compute

    runtime_key = f"{size}|{device}|{compute}"
    return size, device, compute if compute else "int8"


def _load_model(size: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    logger.info(
        "Whisper model loading: size=%s device=%s compute_type=%s",
        size,
        device,
        compute_type,
    )
    model = WhisperModel(size, device=device, compute_type=compute_type)
    logger.info("Whisper model loaded")
    return model


def _get_model(model_size: Optional[str] = None):
    global _model, _model_runtime_key

    size, device, compute_type = _resolve_runtime(model_size)
    runtime_key = f"{size}|{device}|{compute_type}"

    if _model is not None and _model_runtime_key == runtime_key:
        return _model

    try:
        _model = _load_model(size=size, device=device, compute_type=compute_type)
        _model_runtime_key = runtime_key
        return _model
    except Exception as e:
        # GPU init can fail by driver/runtime mismatch. Fall back to CPU safely.
        if device == "cuda":
            logger.warning("Whisper CUDA load failed. Falling back to CPU. (%s)", e)
            _model = _load_model(size=size, device="cpu", compute_type="int8")
            _model_runtime_key = f"{size}|cpu|int8"
            return _model
        raise


def prewarm_model() -> bool:
    global _last_stt_error
    _last_stt_error = ""
    try:
        _get_model()
        return True
    except Exception as e:
        _last_stt_error = str(e)
        logger.error("Whisper prewarm error: %s", e)
        return False


def _transcribe_with_model(model, audio_source: str, lang: str = "ko") -> str:
    beam_size = max(1, _env_int("WHISPER_BEAM_SIZE", 1))
    vad_filter = _env_bool("WHISPER_VAD_FILTER", True)

    segments, info = model.transcribe(
        audio_source,
        language=lang,
        beam_size=beam_size,
        vad_filter=vad_filter,
        condition_on_previous_text=False,
    )
    text = " ".join(s.text.strip() for s in segments).strip()
    logger.info(
        "STT transcribed: %s chars (%s, %.1fs, beam=%d, vad=%s)",
        len(text),
        info.language,
        info.duration,
        beam_size,
        vad_filter,
    )
    return text


def transcribe_realtime(audio_bytes: bytes, lang: str = "ko") -> str:
    """
    Transcribe recorded bytes into text.
    Returns empty string on failure.
    """
    global _last_stt_error
    _last_stt_error = ""
    try:
        import tempfile

        model = _get_model()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            return _transcribe_with_model(model, tmp_path, lang=lang)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    except Exception as e:
        _last_stt_error = str(e)
        logger.error("STT transcribe error: %s", e)
        return ""


def transcribe_file(audio_path: str, lang: str = "ko") -> str:
    """
    Transcribe an audio file path into text.
    """
    global _last_stt_error
    _last_stt_error = ""
    try:
        model = _get_model()
        text = _transcribe_with_model(model, audio_path, lang=lang)
        logger.info("File STT transcribed: %s (%d chars)", audio_path, len(text))
        return text
    except Exception as e:
        _last_stt_error = str(e)
        logger.error("File STT error (%s): %s", audio_path, e)
        return ""
