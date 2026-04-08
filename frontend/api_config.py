"""
frontend/api_config.py
Frontend components share one API base URL to avoid hard-coded drift.
"""
from app_config import app_config

API_BASE = app_config.api_base_url
