from frontend.components.voice_ui import _should_force_block_locally
from frontend.components.voice_ui import _safe_max_questions


def test_force_block_when_q1_intent_missing_but_agency_text_and_yes_answer():
    question = {
        "id": 1,
        "text": "혹시 경찰, 검찰, 금감원 같은 공공기관에서 직접 이체나 현금 전달을 지시했나요?",
        "intent": "",
    }
    answer = "네 직접 지시받았어요"
    assert _should_force_block_locally(question, answer) is True


def test_no_force_block_on_negative_answer():
    question = {
        "id": 1,
        "text": "혹시 경찰, 검찰, 금감원 같은 공공기관에서 직접 이체나 현금 전달을 지시했나요?",
        "intent": "",
    }
    answer = "아니요 그런 지시는 없었습니다"
    assert _should_force_block_locally(question, answer) is False


def test_force_block_on_directive_phrase_without_explicit_yes():
    question = {
        "id": 1,
        "text": "혹시 경찰, 검찰, 금감원 같은 공공기관에서 직접 이체나 현금 전달을 지시했나요?",
        "intent": "",
    }
    answer = "직접 이체하라 했어요"
    assert _should_force_block_locally(question, answer) is True


def test_safe_max_questions_floor(monkeypatch):
    import streamlit as st

    monkeypatch.setitem(st.session_state, "voice_max_questions", 1)
    assert _safe_max_questions() == 3
