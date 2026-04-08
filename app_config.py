"""
Centralized runtime address/port configuration shared by frontend/backend/tests.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _maybe_load_dotenv() -> None:
    """Load .env when available, but never fail if dotenv is unavailable."""
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        # Keep runtime robust in constrained environments.
        pass


def _load_env_file_fallback() -> None:
    """
    Minimal .env loader that works even when python-dotenv isn't available.
    Only sets keys that are not already in process env.
    """
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return

    try:
        for raw in env_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        # Never break app startup due to env parsing.
        pass


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, str(default))
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class AppConfig:
    backend_scheme: str
    backend_host: str          # bind host for uvicorn
    backend_public_host: str   # host used by frontend/client calls
    backend_port: int
    frontend_host: str
    frontend_port: int

    @property
    def api_base_url(self) -> str:
        override = os.getenv("API_BASE_URL", "").strip()
        if override:
            return override.rstrip("/")
        return f"{self.backend_scheme}://{self.backend_public_host}:{self.backend_port}"

    @property
    def frontend_base_url(self) -> str:
        override = os.getenv("FRONTEND_BASE_URL", "").strip()
        if override:
            return override.rstrip("/")
        return f"http://{self.frontend_host}:{self.frontend_port}"


def load_app_config() -> AppConfig:
    _load_env_file_fallback()
    _maybe_load_dotenv()
    return AppConfig(
        backend_scheme=os.getenv("BACKEND_SCHEME", "http"),
        backend_host=os.getenv("BACKEND_HOST", "0.0.0.0"),
        backend_public_host=os.getenv("BACKEND_PUBLIC_HOST", "localhost"),
        backend_port=_env_int("BACKEND_PORT", 8000),
        frontend_host=os.getenv("FRONTEND_HOST", "localhost"),
        frontend_port=_env_int("FRONTEND_PORT", 8501),
    )


app_config = load_app_config()
