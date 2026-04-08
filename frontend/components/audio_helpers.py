"""
Audio helper utilities shared across voice/face components.
"""
from __future__ import annotations

import json
from typing import Optional, Tuple

import httpx
import streamlit as st
import streamlit.components.v1 as components

from frontend.api_config import API_BASE


def _response_error_detail(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
        detail = payload.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail.strip()
    except Exception:
        pass

    text = (resp.text or "").strip()
    if text:
        return text[:180]
    return f"HTTP {resp.status_code}"


def _browser_tts(text: str, lang: str = "ko-KR") -> None:
    script = f"""
    <script>
      const txt = {json.dumps(text)};
      const utter = new SpeechSynthesisUtterance(txt);
      utter.lang = {json.dumps(lang)};
      utter.rate = 1.0;
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utter);
    </script>
    """
    components.html(script, height=0)


def play_tts(text: str, timeout: float = 15) -> bool:
    """
    Try backend TTS first, then fallback to browser SpeechSynthesis.
    Returns True when backend TTS succeeds.
    """
    try:
        resp = httpx.post(
            f"{API_BASE}/api/tts/speak",
            json={"text": text, "lang": "ko"},
            timeout=timeout,
        )
        if resp.status_code == 200:
            st.audio(resp.content, format="audio/mp3", autoplay=True)
            return True

        detail = _response_error_detail(resp)
        _browser_tts(text)
        st.warning(f"TTS 백엔드 실패: {detail} (API: {API_BASE}, 브라우저 음성으로 대체)")
        return False

    except Exception as e:
        _browser_tts(text)
        st.warning(f"TTS 연결 오류: {e} (API: {API_BASE}, 브라우저 음성으로 대체)")
        return False


def transcribe_audio(
    audio_bytes: bytes,
    lang: str = "ko",
    timeout: float = 30,
) -> Tuple[str, Optional[str]]:
    """
    Returns (text, error). error is None on success.
    """
    try:
        resp = httpx.post(
            f"{API_BASE}/api/stt/transcribe",
            files={"file": ("answer.wav", audio_bytes, "audio/wav")},
            data={"lang": lang},
            timeout=timeout,
        )
        if resp.status_code == 200:
            try:
                return resp.json().get("text", ""), None
            except Exception:
                return "", "STT 응답 파싱 실패"

        return "", f"{_response_error_detail(resp)} (API: {API_BASE})"

    except Exception as e:
        return "", f"{e} (API: {API_BASE})"
