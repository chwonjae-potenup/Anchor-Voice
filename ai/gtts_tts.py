"""
gTTS based TTS helpers.
"""
from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_last_tts_error = ""


def get_last_tts_error() -> str:
    return _last_tts_error


def synthesize_speech(text: str, lang: str = "ko") -> bytes:
    """
    Convert text to MP3 bytes using gTTS.
    Returns empty bytes on failure.
    """
    global _last_tts_error
    _last_tts_error = ""
    try:
        from gtts import gTTS

        tts = gTTS(text=text, lang=lang, slow=False)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        audio_bytes = buf.read()
        logger.info("TTS converted: %d chars -> %d bytes", len(text), len(audio_bytes))
        return audio_bytes

    except Exception as e:
        _last_tts_error = str(e)
        logger.error("TTS convert error: %s", e)
        return b""


def speak_text(text: str, lang: str = "ko") -> bool:
    """
    Play synthesized speech locally (best effort).
    """
    try:
        audio_bytes = synthesize_speech(text, lang)
        if not audio_bytes:
            return False

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            import pygame

            pygame.mixer.init()
            pygame.mixer.music.load(tmp_path)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                pygame.time.Clock().tick(10)
            return True
        except ImportError:
            try:
                import playsound

                playsound.playsound(tmp_path)
                return True
            except Exception as pe:
                logger.warning("Speech playback failed (playsound): %s", pe)
                return False
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    except Exception as e:
        logger.error("speak_text error: %s", e)
        return False

