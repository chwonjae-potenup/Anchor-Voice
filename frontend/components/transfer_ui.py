"""
frontend/components/transfer_ui.py
Transfer flow UI:
- Step 1: recipient input
- Step 2: amount keypad + risk simulation options

Flow integration:
transfer -> risk-check -> face -> (voice if required) -> result/additional_auth
"""

from __future__ import annotations

from datetime import datetime

import httpx
import streamlit as st

from frontend.api_config import API_BASE
from frontend.components.bank_utils import BANKS, validate_and_format_account

HIGH_RISK_THRESHOLD = 70
CAUTION_RISK_THRESHOLD = 35
LOW_RISK_THRESHOLD = 30

HIGH_AMOUNT_LIMIT = 1_000_000
HIGH_AMOUNT_AI_THRESHOLD = 10_000_000

DEFAULT_USUAL_AMOUNT = 300_000
DEFAULT_USUAL_HOUR_START = 9
DEFAULT_USUAL_HOUR_END = 21

AGE_PROFILE = "10~20대"
HIGH_AMOUNT_REVIEW_MESSAGE = "고액 이체 전, 송금 목적과 수취인 정보를 다시 한 번 확인해 주세요."

STEP_RECIPIENT = "recipient"
STEP_AMOUNT = "amount"

BANK_WIDGET_KEY = "transfer_selected_bank_widget"
ACCOUNT_WIDGET_KEY = "transfer_recipient_account_raw_widget"


def _is_primary_high_amount_trigger(amount: int) -> bool:
    return int(amount or 0) >= HIGH_AMOUNT_AI_THRESHOLD


def _reset_voice_state() -> None:
    for key in [
        "voice_step",
        "voice_log",
        "voice_done",
        "voice_max_questions",
        "voice_current_question",
        "voice_gate_passed",
        "voice_gate_status",
    ]:
        st.session_state.pop(key, None)


def _local_risk_score(amount: int, hour: int, is_new: bool, is_blacklisted: bool) -> dict:
    repeat_attempt_count = int(st.session_state.get("transfer_submit_attempt_count", 0) or 0)
    recent_call_after = bool(st.session_state.get("transfer_recent_call_after", False))
    usual_amount = int(st.session_state.get("transfer_usual_amount", DEFAULT_USUAL_AMOUNT) or DEFAULT_USUAL_AMOUNT)
    usual_hour_start = int(
        st.session_state.get("transfer_usual_hour_start", DEFAULT_USUAL_HOUR_START) or DEFAULT_USUAL_HOUR_START
    )
    usual_hour_end = int(
        st.session_state.get("transfer_usual_hour_end", DEFAULT_USUAL_HOUR_END) or DEFAULT_USUAL_HOUR_END
    )

    score = 0
    reasons: list[str] = []

    if is_blacklisted:
        score += 70
        reasons.append("의심 계좌(블랙리스트) 송금")
    if is_new:
        score += 20
        reasons.append("처음 보내는 계좌")
    if amount >= HIGH_AMOUNT_LIMIT:
        score += 15
        reasons.append(f"고액 이체 ({amount:,}원)")
    if amount >= HIGH_AMOUNT_AI_THRESHOLD:
        score += 20
        reasons.append(f"1차 트리거 고액 송금 ({amount:,}원)")
    if hour >= 22 or hour < 6:
        score += 10
        reasons.append(f"야간 거래 ({hour}시)")
    if repeat_attempt_count >= 2:
        score += 20
        reasons.append(f"반복 이체 시도 ({repeat_attempt_count}회)")
    if recent_call_after:
        score += 20
        reasons.append("최근 통화 직후 송금")

    amount_outlier = amount >= max(HIGH_AMOUNT_LIMIT, usual_amount * 3)
    if usual_hour_start <= usual_hour_end:
        time_outlier = hour < usual_hour_start or hour > usual_hour_end
    else:
        time_outlier = not (hour >= usual_hour_start or hour <= usual_hour_end)
    unusual_pattern = bool(amount_outlier or time_outlier)
    if unusual_pattern:
        score += 15
        reasons.append("평소 패턴과 다른 시간대/금액")

    score = min(score, 100)
    if score >= HIGH_RISK_THRESHOLD:
        level = "high"
        decision_level = "risk"
    elif score >= CAUTION_RISK_THRESHOLD:
        level = "medium"
        decision_level = "caution"
    elif score < LOW_RISK_THRESHOLD:
        level = "low"
        decision_level = "safe"
    else:
        level = "medium"
        decision_level = "caution"

    secondary_trigger_reasons: list[str] = []
    if is_new:
        secondary_trigger_reasons.append("처음 보내는 계좌")
    if recent_call_after:
        secondary_trigger_reasons.append("최근 통화 직후 송금")
    if unusual_pattern:
        secondary_trigger_reasons.append("평소 패턴과 다른 시간대/금액")
    if repeat_attempt_count >= 2:
        secondary_trigger_reasons.append("짧은 시간 내 반복 이체 시도")

    trigger_reasons: list[str] = []
    if amount >= HIGH_AMOUNT_AI_THRESHOLD:
        trigger_reasons.append("1차 트리거: 고액 송금")
    trigger_reasons.extend(secondary_trigger_reasons)

    ai_intervention_required = bool(
        amount >= HIGH_AMOUNT_AI_THRESHOLD or len(secondary_trigger_reasons) >= 1 or decision_level == "risk"
    )

    return {
        "risk_score": score,
        "risk_level": level,
        "decision_level": decision_level,
        "reason": reasons,
        "ai_intervention_required": ai_intervention_required,
        "trigger_reasons": trigger_reasons,
    }


def _fetch_risk_from_backend(payload: dict) -> dict:
    resp = httpx.post(
        f"{API_BASE}/api/transfer/risk-check",
        json=payload,
        timeout=8,
    )
    resp.raise_for_status()
    return resp.json()


def _init_transfer_state() -> None:
    defaults = {
        "transfer_step": STEP_RECIPIENT,
        "transfer_selected_bank": list(BANKS.keys())[0] if BANKS else "",
        "transfer_recipient_account_raw": "",
        "transfer_recipient_account_validated": "",
        "transfer_amount": 0,
        "transfer_amount_display": "0원",
        "transfer_error": "",
        "transfer_notice": "",
        "transfer_recent_action_message": "",
        "transfer_is_new": False,
        "transfer_is_blacklisted": False,
        "transfer_recent_call_after": False,
        "transfer_usual_amount": DEFAULT_USUAL_AMOUNT,
        "transfer_usual_hour_start": DEFAULT_USUAL_HOUR_START,
        "transfer_usual_hour_end": DEFAULT_USUAL_HOUR_END,
        "transfer_submit_attempt_count": 0,
        "transfer_decision_level": "safe",
        "transfer_ai_intervention_required": False,
        "transfer_primary_high_amount_trigger": False,
        "transfer_trigger_reasons": [],
        "transfer_result_level": "safe",
        "transfer_caution_message": "",
        "transfer_ai_popup_open": False,
        "transfer_high_amount_reviewed": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Rehydrate widget state from canonical state.
    if BANK_WIDGET_KEY not in st.session_state:
        st.session_state[BANK_WIDGET_KEY] = st.session_state.transfer_selected_bank
    if ACCOUNT_WIDGET_KEY not in st.session_state:
        st.session_state[ACCOUNT_WIDGET_KEY] = st.session_state.transfer_recipient_account_raw

    _sync_amount_display()


def _format_currency(amount: int) -> str:
    return f"{int(amount):,}원"


def _sync_amount_display() -> None:
    st.session_state.transfer_amount_display = _format_currency(int(st.session_state.transfer_amount or 0))


def _submit_mock_transfer_request() -> dict:
    return {
        "success": True,
        "message": "이체 요청이 생성되었습니다. 다음 단계에서 본인 인증을 진행합니다.",
        "recipient_bank": st.session_state.transfer_selected_bank,
        "recipient_account": st.session_state.transfer_recipient_account_validated,
        "amount": int(st.session_state.transfer_amount or 0),
    }


def _go_home_tab() -> None:
    st.session_state.mobile_tab = "안심홈"
    st.rerun()


def _go_recipient_step() -> None:
    st.session_state.transfer_step = STEP_RECIPIENT
    st.session_state.transfer_high_amount_reviewed = False
    st.session_state.transfer_primary_high_amount_trigger = False
    st.session_state.transfer_submit_attempt_count = 0
    st.rerun()


def _handle_keypad_input(key: str) -> None:
    current = str(int(st.session_state.transfer_amount or 0))
    if current == "0":
        current = ""

    next_amount = (current + key).lstrip("0") or "0"
    try:
        st.session_state.transfer_amount = int(next_amount)
    except ValueError:
        st.session_state.transfer_amount = 0

    _sync_amount_display()
    st.session_state.transfer_high_amount_reviewed = False
    st.rerun()


def _handle_keypad_delete() -> None:
    current = str(int(st.session_state.transfer_amount or 0))
    next_amount = current[:-1] or "0"
    st.session_state.transfer_amount = int(next_amount)
    _sync_amount_display()
    st.session_state.transfer_high_amount_reviewed = False
    st.rerun()


def _resolve_account_for_transfer(bank: str, account_raw: str) -> tuple[str, bool, str]:
    if not account_raw:
        return "", False, "계좌번호를 입력해 주세요."

    if bank == "기타(직접입력)":
        account = account_raw.strip()
        digits = "".join(ch for ch in account if ch.isdigit())
        if len(digits) < 8:
            return "", False, "계좌번호는 최소 8자리 이상이어야 합니다."
        return account, True, ""

    account, is_valid = validate_and_format_account(bank, account_raw)
    if not is_valid:
        expected_len = BANKS.get(bank, {}).get("len", "-")
        return "", False, f"{bank} 계좌번호는 {expected_len}자리 숫자여야 합니다."
    return account, True, ""


def _submit_recipient() -> None:
    bank = st.session_state.transfer_selected_bank
    raw = st.session_state.transfer_recipient_account_raw
    account, is_valid, err = _resolve_account_for_transfer(bank, raw)
    if not is_valid:
        st.session_state.transfer_error = err
        return

    st.session_state.transfer_error = ""
    st.session_state.transfer_notice = ""
    st.session_state.transfer_recent_action_message = ""
    st.session_state.transfer_recipient_account_validated = account
    st.session_state.transfer_step = STEP_AMOUNT
    st.session_state.transfer_submit_attempt_count = 0
    st.session_state.transfer_high_amount_reviewed = False
    st.session_state.transfer_primary_high_amount_trigger = False
    st.rerun()


def _proceed_transfer_after_review(state) -> None:
    amount = int(st.session_state.transfer_amount or 0)
    primary_high_amount_trigger = _is_primary_high_amount_trigger(amount)

    bank = st.session_state.transfer_selected_bank
    account = st.session_state.transfer_recipient_account_validated
    is_new = bool(st.session_state.transfer_is_new)
    is_blacklisted = bool(st.session_state.transfer_is_blacklisted)
    recent_call_after = bool(st.session_state.transfer_recent_call_after)
    usual_amount = max(1, int(st.session_state.transfer_usual_amount or DEFAULT_USUAL_AMOUNT))
    usual_hour_start = int(st.session_state.transfer_usual_hour_start or DEFAULT_USUAL_HOUR_START)
    usual_hour_end = int(st.session_state.transfer_usual_hour_end or DEFAULT_USUAL_HOUR_END)
    hour = datetime.now().hour

    st.session_state.transfer_submit_attempt_count = int(st.session_state.transfer_submit_attempt_count or 0) + 1
    repeat_attempt_count = int(st.session_state.transfer_submit_attempt_count)

    st.session_state.user_age_group = AGE_PROFILE
    _reset_voice_state()

    state.set_transfer_data(
        account=account,
        amount=amount,
        hour=hour,
        is_new=is_new,
        is_blacklisted=is_blacklisted,
        repeat=repeat_attempt_count,
        recent_call_after=recent_call_after,
        usual_amount=usual_amount,
        usual_hour_start=usual_hour_start,
        usual_hour_end=usual_hour_end,
    )

    payload = {
        "account_number": account,
        "amount": amount,
        "hour": hour,
        "is_new_account": is_new,
        "is_blacklisted": is_blacklisted,
        "repeat_attempt_count": repeat_attempt_count,
        "recent_call_after": recent_call_after,
        "usual_amount": usual_amount,
        "usual_hour_start": usual_hour_start,
        "usual_hour_end": usual_hour_end,
    }

    with st.spinner("이체 위험도를 분석하는 중..."):
        try:
            data = _fetch_risk_from_backend(payload)
        except Exception:
            data = _local_risk_score(amount, hour, is_new, is_blacklisted)
            st.session_state.transfer_notice = "서버 연결 이슈로 로컬 위험도 계산으로 대체했습니다."

    score = int(data.get("risk_score", 0))
    level = str(data.get("risk_level", "low"))
    decision_level = str(
        data.get(
            "decision_level",
            "risk" if level == "high" else "caution" if level == "medium" else "safe",
        )
    )
    reasons = list(data.get("reason", []))
    trigger_reasons = list(data.get("trigger_reasons", []))
    if primary_high_amount_trigger and "1차 트리거: 고액 송금" not in trigger_reasons:
        trigger_reasons.insert(0, "1차 트리거: 고액 송금")

    ai_intervention_required = bool(data.get("ai_intervention_required", level in {"high", "medium"}))
    # Hard policy: primary trigger (>= 1천만원)는 항상 음성 검증 필수
    ai_intervention_required = primary_high_amount_trigger or ai_intervention_required or decision_level == "risk"

    st.session_state.risk_score = score
    st.session_state.risk_level = level
    st.session_state.transfer_decision_level = decision_level
    st.session_state.transfer_ai_intervention_required = ai_intervention_required
    st.session_state.transfer_primary_high_amount_trigger = primary_high_amount_trigger
    st.session_state.transfer_trigger_reasons = trigger_reasons

    if decision_level == "caution" and not ai_intervention_required:
        st.session_state.transfer_result_level = "caution"
        st.session_state.transfer_caution_message = "주의 신호가 있어 가족/상담센터 재확인 후 진행을 권고합니다."
    else:
        st.session_state.transfer_result_level = "safe"
        st.session_state.transfer_caution_message = ""

    st.session_state.require_voice_after_identity = ai_intervention_required
    st.session_state.voice_gate_passed = not st.session_state.require_voice_after_identity
    st.session_state.voice_gate_status = "required" if st.session_state.require_voice_after_identity else "not_required"
    st.session_state.additional_auth_source = None

    decision_label = {"safe": "안전", "caution": "주의", "risk": "위험"}.get(decision_level, decision_level)
    reason_text = ", ".join(reasons) if reasons else "특이 위험 요인 없음"
    trigger_text = ", ".join(trigger_reasons) if trigger_reasons else "해당 없음"
    ai_text = "필요" if ai_intervention_required else "불필요"
    st.session_state.transfer_notice = (
        f"수취은행 {bank}, 위험점수 {score}점 ({decision_label}) | 요인: {reason_text} | "
        f"AI 개입: {ai_text} ({trigger_text})"
    )

    submit_result = _submit_mock_transfer_request()
    st.session_state.transfer_recent_action_message = submit_result["message"]
    state.go_to("face")


def _submit_transfer(state) -> None:
    amount = int(st.session_state.transfer_amount or 0)
    if amount <= 0:
        st.session_state.transfer_error = "보낼 금액을 입력해 주세요."
        return

    st.session_state.transfer_error = ""
    st.session_state.transfer_recent_action_message = ""

    if amount >= HIGH_AMOUNT_AI_THRESHOLD and not bool(st.session_state.transfer_high_amount_reviewed):
        st.session_state.transfer_ai_popup_open = True
        return

    _proceed_transfer_after_review(state)


@st.dialog("AI 안심 확인", width="large", dismissible=False)
def _render_high_amount_ai_popup(state) -> None:
    st.markdown(
        """
        <div class="av-ai-review-hero">
          <div class="av-ai-review-chip">고액 이체 안전 점검</div>
          <div class="av-ai-review-title">1천만원 이상 이체 전<br/>AI 안심 확인</div>
          <div class="av-ai-review-subtitle">
            고액 이체는 안전 점검을 거친 뒤 본인 인증 단계로 이동합니다.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="av-ai-review-box">
          받는 은행: <b>{st.session_state.transfer_selected_bank}</b><br/>
          계좌번호: <b>{st.session_state.transfer_recipient_account_validated}</b><br/>
          검토 금액: <b>{st.session_state.transfer_amount_display}</b>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        f"""
        <div class="av-ai-review-transcript">
          {HIGH_AMOUNT_REVIEW_MESSAGE}
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("AI 확인", key="transfer_ai_review_done", use_container_width=True, type="primary"):
            st.session_state.transfer_ai_popup_open = False
            st.session_state.transfer_high_amount_reviewed = True
            st.session_state.transfer_recent_action_message = "고액 이체 사전 AI 확인을 완료했습니다."
            _proceed_transfer_after_review(state)
            st.rerun()
    with col2:
        if st.button("금액 다시 확인", key="transfer_ai_review_cancel", use_container_width=True):
            st.session_state.transfer_ai_popup_open = False
            st.rerun()


def _render_top_bar() -> None:
    topbar = st.container(key="transfer_top_bar")
    left_col, center_col, right_col = topbar.columns([1, 4, 1], gap="small")

    with left_col:
        if st.session_state.transfer_step == STEP_AMOUNT:
            if st.button("←", key="transfer_back_recipient"):
                _go_recipient_step()

    with center_col:
        title = "받는 분 선택" if st.session_state.transfer_step == STEP_RECIPIENT else "보낼 금액 입력"
        st.markdown(f'<div class="av-transfer-topbar-title">{title}</div>', unsafe_allow_html=True)

    with right_col:
        if st.button("⌂", key="transfer_go_home_tab"):
            _go_home_tab()


def _render_recipient_step() -> None:
    st.markdown('<div class="av-transfer-title">누구에게<br/>보낼까요?</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="av-transfer-subtitle">은행과 계좌번호를 입력하면 다음 단계로 이동합니다.</div>',
        unsafe_allow_html=True,
    )

    bank_options = list(BANKS.keys()) + ["기타(직접입력)"]

    # Re-sync widget state from persistent state before rendering widgets.
    current_bank = st.session_state.transfer_selected_bank
    if current_bank not in bank_options:
        current_bank = bank_options[0]
        st.session_state.transfer_selected_bank = current_bank
    if st.session_state.get(BANK_WIDGET_KEY) not in bank_options:
        st.session_state[BANK_WIDGET_KEY] = current_bank
    if ACCOUNT_WIDGET_KEY not in st.session_state:
        st.session_state[ACCOUNT_WIDGET_KEY] = st.session_state.transfer_recipient_account_raw

    st.markdown('<div class="av-transfer-card">', unsafe_allow_html=True)
    st.selectbox("수취 은행", options=bank_options, key=BANK_WIDGET_KEY)
    st.session_state.transfer_selected_bank = st.session_state[BANK_WIDGET_KEY]
    st.text_input(
        "수취 계좌번호",
        key=ACCOUNT_WIDGET_KEY,
        placeholder="'-' 없이 숫자만 입력하세요",
    )
    st.session_state.transfer_recipient_account_raw = st.session_state[ACCOUNT_WIDGET_KEY]
    st.markdown("</div>", unsafe_allow_html=True)

    if st.session_state.transfer_error:
        st.error(st.session_state.transfer_error)
    if st.session_state.transfer_recent_action_message:
        st.info(st.session_state.transfer_recent_action_message)
    if st.session_state.transfer_notice:
        st.caption(st.session_state.transfer_notice)

    if st.button("다음", key="transfer_recipient_next", use_container_width=True, type="primary"):
        _submit_recipient()


def _render_amount_step(state) -> None:
    st.markdown('<div class="av-transfer-title">얼마를<br/>보낼까요?</div>', unsafe_allow_html=True)

    st.markdown('<div class="av-transfer-card">', unsafe_allow_html=True)
    st.markdown(
        f'<div class="av-transfer-chip">받는 은행 · {st.session_state.transfer_selected_bank}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="av-transfer-chip">계좌번호 · {st.session_state.transfer_recipient_account_validated}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="av-transfer-amount">{st.session_state.transfer_amount_display}</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="av-transfer-help">숫자 키패드로 금액을 입력해 주세요.</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    with st.container(key="transfer_risk_sim_panel"):
        with st.expander("위험도 시뮬레이션 옵션 (테스트)", expanded=False):
            st.checkbox("처음 이체하는 계좌", key="transfer_is_new")
            st.checkbox("의심 계좌(테스트)", key="transfer_is_blacklisted")
            st.checkbox("최근 통화 직후 송금", key="transfer_recent_call_after")
            st.number_input(
                "평소 송금 금액 기준(원)",
                min_value=10_000,
                step=10_000,
                key="transfer_usual_amount",
            )
            hour_col1, hour_col2 = st.columns(2)
            with hour_col1:
                st.number_input(
                    "평소 시작 시각",
                    min_value=0,
                    max_value=23,
                    step=1,
                    key="transfer_usual_hour_start",
                )
            with hour_col2:
                st.number_input(
                    "평소 종료 시각",
                    min_value=0,
                    max_value=23,
                    step=1,
                    key="transfer_usual_hour_end",
                )
            st.caption(f"적용 프로필: {AGE_PROFILE}")
            st.caption(f"현재 전송 시도 횟수: {int(st.session_state.transfer_submit_attempt_count or 0)}회")

    if st.session_state.transfer_error:
        st.error(st.session_state.transfer_error)
    if st.session_state.transfer_recent_action_message:
        st.info(st.session_state.transfer_recent_action_message)
    if st.session_state.transfer_notice:
        st.caption(st.session_state.transfer_notice)

    if st.button("전송", key="transfer_submit", use_container_width=True, type="primary"):
        _submit_transfer(state)

    keypad_rows = [
        ["1", "2", "3"],
        ["4", "5", "6"],
        ["7", "8", "9"],
        ["00", "0", "⌫"],
    ]
    for row_idx, values in enumerate(keypad_rows):
        row_container = st.container(key=f"transfer_keypad_row_{row_idx}")
        cols = row_container.columns(3, gap="small")
        for col, value in zip(cols, values):
            with col:
                if value == "⌫":
                    if st.button(value, key=f"transfer_keypad_del_{row_idx}", use_container_width=True):
                        _handle_keypad_delete()
                else:
                    if st.button(value, key=f"transfer_keypad_{row_idx}_{value}", use_container_width=True):
                        _handle_keypad_input(value)


def render(state) -> None:
    _init_transfer_state()
    _render_top_bar()
    st.markdown("---")

    if st.session_state.transfer_step == STEP_RECIPIENT:
        _render_recipient_step()
    else:
        _render_amount_step(state)

    if st.session_state.transfer_ai_popup_open:
        _render_high_amount_ai_popup(state)
