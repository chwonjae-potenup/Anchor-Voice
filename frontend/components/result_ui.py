"""
frontend/components/result_ui.py  — Frontend Agent
정상 이체 완료 화면
"""
import streamlit as st
from datetime import datetime


def render(state):
    require_voice = bool(st.session_state.get("require_voice_after_identity", False))
    voice_gate_passed = bool(st.session_state.get("voice_gate_passed", False))
    voice_gate_status = str(st.session_state.get("voice_gate_status") or "").strip().lower()

    if require_voice and voice_gate_status == "block":
        state.go_to("stealth")
        return

    if require_voice and not voice_gate_passed:
        st.error("음성 위험 검증이 완료되지 않아 이체를 진행할 수 없습니다. 음성 확인 단계로 돌아갑니다.")
        state.go_to("voice")
        return

    data = st.session_state.get("transfer_data", {})
    amount = data.get("amount", 0)
    account = data.get("account_number", "***")
    auth_method = st.session_state.get("auth_method") or "안전 확인 완료"

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

    st.markdown(f"""
    | 항목 | 내용 |
    |------|------|
    | 수취 계좌 | `{account}` |
    | 이체 금액 | **{amount:,}원** |
    | 완료 시각 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |
    | 인증 방식 | {auth_method} ✅ |
    """)
    st.markdown("---")
    if st.button("새 이체 시작", use_container_width=True):
        state.reset()
