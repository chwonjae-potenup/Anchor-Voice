"""
Video capture component wrapper for Streamlit.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import streamlit.components.v1 as components

_COMPONENT_DIR = Path(__file__).resolve().parent / "video_capture_component"
_VIDEO_CAPTURE_COMPONENT = components.declare_component(
    "kb_video_capture_component",
    path=str(_COMPONENT_DIR),
)


def render_video_capture(
    label: str = "녹화 시작 (5초)",
    duration_ms: int = 5000,
    fps: int = 8,
    height: int = 500,
    key: str = "kb_video_capture_component",
) -> dict[str, Any] | None:
    """
    Returns:
      {
        "capture_id": "<unique id>",
        "frames": [<base64 jpeg>, ...]
      }
    or None when no recording has been completed yet.
    """
    value = _VIDEO_CAPTURE_COMPONENT(
        label=label,
        duration_ms=max(1000, int(duration_ms)),
        fps=max(4, min(20, int(fps))),
        key=key,
        default=None,
    )
    if not isinstance(value, dict):
        return None

    capture_id = str(value.get("capture_id", "")).strip()
    frames = value.get("frames")
    if not capture_id or not isinstance(frames, list) or not frames:
        return None
    return {"capture_id": capture_id, "frames": frames}


def frames_to_bytes_list(frames_b64: list[str]) -> list[bytes]:
    """
    Convert base64 JPEG strings to bytes list.
    """
    result: list[bytes] = []
    for item in frames_b64:
        if not isinstance(item, str) or not item:
            continue
        try:
            result.append(base64.b64decode(item))
        except Exception:
            continue
    return result
