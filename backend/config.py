"""
Runtime settings for backend services.
"""
from __future__ import annotations

import os

from app_config import app_config


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


class Settings:
    # LLM
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    

    # Risk thresholds
    RISK_THRESHOLD_HIGH: int = _env_int("RISK_THRESHOLD_HIGH", 70)
    RISK_THRESHOLD_LOW: int = _env_int("RISK_THRESHOLD_LOW", 30)

    # Service addresses
    BACKEND_SCHEME: str = app_config.backend_scheme
    BACKEND_HOST: str = app_config.backend_host
    BACKEND_PUBLIC_HOST: str = app_config.backend_public_host
    BACKEND_PORT: int = app_config.backend_port
    FRONTEND_HOST: str = app_config.frontend_host
    FRONTEND_PORT: int = app_config.frontend_port
    FRONTEND_BASE_URL: str = app_config.frontend_base_url
    API_BASE_URL: str = app_config.api_base_url

    # Whisper STT runtime
    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "base")
    WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "auto")
    WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "auto")
    WHISPER_BEAM_SIZE: int = _env_int("WHISPER_BEAM_SIZE", 1)
    WHISPER_VAD_FILTER: bool = _env_bool("WHISPER_VAD_FILTER", True)

    # Face analysis runtime
    DEEPFACE_MODEL_NAME: str = os.getenv("DEEPFACE_MODEL_NAME", "ArcFace")
    DEEPFACE_MODEL_FALLBACK: str = os.getenv("DEEPFACE_MODEL_FALLBACK", "VGG-Face")
    DEEPFACE_DETECTOR_BACKEND: str = os.getenv("DEEPFACE_DETECTOR_BACKEND", "opencv")
    DEEPFACE_DISTANCE_METRIC: str = os.getenv("DEEPFACE_DISTANCE_METRIC", "cosine")
    FACE_SEQUENCE_MAX_FRAMES: int = _env_int("FACE_SEQUENCE_MAX_FRAMES", 18)
    FACE_FRAME_MAX_SIDE: int = _env_int("FACE_FRAME_MAX_SIDE", 720)

    # Backend warmup
    PRELOAD_WHISPER: bool = _env_bool("PRELOAD_WHISPER", True)
    PRELOAD_DEEPFACE: bool = _env_bool("PRELOAD_DEEPFACE", True)


settings = Settings()
