"""
frontend/components/result_ui.py  — Frontend Agent
송금 결과 화면 (안전/주의)
"""
from datetime import datetime

import streamlit as st


def render(state):
    data = st.session_state.get("transfer_data", {}) or {}
    amount = int(data.get("amount", 0) or 0)
    primary_high_amount_trigger = amount >= 10_000_000
    require_voice = bool(st.session_state.get("require_voice_after_identity", False)) or primary_high_amount_trigger

    if primary_high_amount_trigger and not bool(st.session_state.get("require_voice_after_identity", False)):
        st.session_state.require_voice_after_identity = True
        st.session_state.transfer_ai_intervention_required = True
        st.session_state.transfer_primary_high_amount_trigger = True

    voice_gate_passed = bool(st.session_state.get("voice_gate_passed", False))
    voice_gate_status = str(st.session_state.get("voice_gate_status") or "").strip().lower()

    if require_voice and voice_gate_status == "block":
        summary = (st.session_state.get("phishing_result") or {}).get("summary") or "피싱 위험 신호가 감지되었습니다."
        st.session_state.additional_auth_reason = f"피싱 위험 신호 감지: {summary}"
        st.session_state.additional_auth_source = "voice"
        st.session_state.voice_gate_passed = False
        st.session_state.voice_gate_status = "risk_alert"
        state.go_to("additional_auth")
        return

    if require_voice and not voice_gate_passed:
        st.error("음성 위험 검증이 완료되지 않아 이체를 진행할 수 없습니다. 음성 확인 단계로 돌아갑니다.")
        state.go_to("voice")
        return

    data = st.session_state.get("transfer_data", {})
    amount = data.get("amount", 0)
    account = data.get("account_number", "***")
    auth_method = st.session_state.get("auth_method") or "안전 확인 완료"

    transfer_result_level = str(st.session_state.get("transfer_result_level", "safe") or "safe").strip().lower()
    if transfer_result_level not in {"safe", "caution"}:
        transfer_result_level = "safe"
    if voice_gate_status == "proceed_with_caution":
        transfer_result_level = "caution"

    caution_message = (
        st.session_state.get("transfer_caution_message")
        or (st.session_state.get("phishing_result") or {}).get("summary")
        or "주의 신호가 감지되었습니다. 가족/상담센터 재확인 후 진행을 권고합니다."
    )

    if transfer_result_level == "caution":
        st.markdown(
            """
            <div style='background:#FFFBEB;border:2px solid #D97706;border-radius:12px;
                        padding:2rem;text-align:center;'>
                <div style='font-size:3rem;'>⚠️</div>
                <h2 style='color:#92400E;'>주의 신호가 있어 재확인 후 진행했습니다.</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.warning(caution_message)
        st.info("권고: 가족/지인 또는 금융감독원 상담센터(1332)로 사실 여부를 다시 확인해 주세요.")
    else:
        st.markdown(
            """
            <div style='background:#F0FFF4;border:2px solid #38A169;border-radius:12px;
                        padding:2rem;text-align:center;'>
                <div style='font-size:3rem;'>✅</div>
                <h2 style='color:#276749;'>이체가 완료되었습니다</h2>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
    | 항목 | 내용 |
    |------|------|
    | 수취 계좌 | `{account}` |
    | 이체 금액 | **{amount:,}원** |
    | 완료 시각 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |
    | 인증 방식 | {auth_method} |
    """
    )
    st.markdown("---")
    if st.button("새 이체 시작", use_container_width=True):
        state.reset()
