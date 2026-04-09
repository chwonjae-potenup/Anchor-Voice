"""
frontend/state_manager.py  — Frontend Agent
Streamlit session_state 기반 화면 상태 관리
"""
import streamlit as st
from typing import Optional


# Plan-defined screen flow:
# transfer -> face/voice -> additional_auth -> result
SCREENS = ["transfer", "face", "voice", "additional_auth", "result"]
SCREEN_ALIASES = {
    "face_auth": "face",
    "voice_auth": "voice",
    "fallback_auth": "additional_auth",
    "extra_auth": "additional_auth",
    # Backward compatibility for old sessions that still hold "stealth".
    "stealth": "additional_auth",
}


def init_state():
    """앱 시작 시 상태 초기화"""
    defaults = {
        "screen": "transfer",
        "transfer_data": {},        # TransferRequest 데이터
        "user_age_group": "10~20대",
        "risk_score": None,
        "risk_level": None,
        "transfer_decision_level": "safe",
        "transfer_ai_intervention_required": False,
        "transfer_primary_high_amount_trigger": False,
        "transfer_trigger_reasons": [],
        "transfer_result_level": "safe",
        "transfer_caution_message": "",
        "require_voice_after_identity": False,
        "voice_gate_passed": False,
        "voice_gate_status": None,
        "auth_method": None,
        "additional_auth_reason": None,
        "additional_auth_source": None,
        "conversation_log": [],     # [{question_id, answer}, ...]
        "current_question_id": 1,
        "phishing_result": None,
        "sos_result": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def go_to(screen: str):
    """화면 전환"""
    normalized = SCREEN_ALIASES.get(screen, screen)
    assert normalized in SCREENS, f"알 수 없는 화면: {screen}"
    st.session_state.screen = normalized
    st.rerun()


def get_screen() -> str:
    current = st.session_state.get("screen", "transfer")
    return SCREEN_ALIASES.get(current, current)


def set_transfer_data(account: str, amount: int, hour: int,
                      is_new: bool = False, is_blacklisted: bool = False,
                      repeat: int = 0, recent_call_after: bool = False,
                      usual_amount: int = 300_000,
                      usual_hour_start: int = 9,
                      usual_hour_end: int = 21):
    st.session_state.transfer_data = {
        "account_number": account,
        "amount": amount,
        "hour": hour,
        "is_new_account": is_new,
        "is_blacklisted": is_blacklisted,
        "repeat_attempt_count": repeat,
        "recent_call_after": recent_call_after,
        "usual_amount": usual_amount,
        "usual_hour_start": usual_hour_start,
        "usual_hour_end": usual_hour_end,
    }


def add_answer(question_id: int, answer: bool):
    st.session_state.conversation_log.append(
        {"question_id": question_id, "answer": answer}
    )
    st.session_state.current_question_id += 1


def reset():
    """거래 완료 후 상태 초기화"""
    for key in [
        "transfer_step",
        "transfer_selected_bank",
        "transfer_selected_bank_widget",
        "transfer_recipient_account_raw",
        "transfer_recipient_account_raw_widget",
        "transfer_recipient_account_validated",
        "transfer_amount",
        "transfer_amount_display",
        "transfer_error",
        "transfer_notice",
        "transfer_recent_action_message",
        "transfer_is_new",
        "transfer_is_blacklisted",
        "transfer_recent_call_after",
        "transfer_usual_amount",
        "transfer_usual_hour_start",
        "transfer_usual_hour_end",
        "transfer_submit_attempt_count",
        "transfer_ai_popup_open",
        "transfer_high_amount_reviewed",
        "transfer_data",
        "user_age_group",
        "risk_score",
        "risk_level",
        "transfer_decision_level",
        "transfer_ai_intervention_required",
        "transfer_primary_high_amount_trigger",
        "transfer_trigger_reasons",
        "transfer_result_level",
        "transfer_caution_message",
        "require_voice_after_identity",
        "voice_gate_passed",
        "voice_gate_status",
        "auth_method",
        "additional_auth_reason",
        "additional_auth_source",
        "conversation_log",
        "current_question_id",
        "phishing_result",
        "sos_result",
        "voice_step",
        "voice_log",
        "voice_done",
        "voice_max_questions",
        "voice_current_question",
    ]:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.screen = "transfer"
    st.session_state.current_question_id = 1
    st.session_state.conversation_log = []
