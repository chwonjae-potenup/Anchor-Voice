"""
frontend/components/stealth_ui.py  — Frontend Agent
스텔스 SOS 위장 이체 완료 화면
실제로는 이체가 차단됐지만, 가해자 눈에는 완료처럼 보이는 UI
"""
import streamlit as st
from datetime import datetime
import httpx
from frontend.api_config import API_BASE


def render(state):
    data = st.session_state.get("transfer_data", {})
    amount = data.get("amount", 0)
    account = data.get("account_number", "***")
    phishing_result = st.session_state.get("phishing_result", {})

    # ── 위장 완료 화면 (가해자가 보는 화면) ─────────────────────────────────────────
    st.markdown(
        """
        <div style='background:#f0fff4;border:2px solid #38a169;border-radius:12px;padding:2rem;text-align:center;'>
            <div style='font-size:3rem;'>✅</div>
            <h2 style='color:#276749;margin:0.5rem 0;'>strealth 모드로 이체가 완료되었습니다</h2>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(f"""
    | 항목 | 내용 |
    |------|------|
    | 수취 계좌 | `{account}` |
    | 이체 금액 | {amount:,}원 |
    | 완료 시각 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} |
    | 처리 은행 | 주식회사 앵커뱅크 |
    """)

    # ── 백그라운드: 실제 차단 및 SOS 신호 (화면에 표시 안 함) ──────────────────────
    _trigger_sos_silently(data, phishing_result)

    st.markdown("---")
    if st.button("메인으로 돌아가기", use_container_width=True):
        state.reset()
        state.go_to("transfer")


def _trigger_sos_silently(transfer_data: dict, phishing_evidence: dict):
    """백그라운드 SOS — 화면에 표시하지 않음"""
    try:
        httpx.post(
            f"{API_BASE}/api/sos/trigger",
            json={
                "transfer_info": transfer_data,
                "phishing_evidence": phishing_evidence,
            },
            timeout=5,
        )
    except Exception:
        pass  # 실패해도 UI에 노출 안 함
