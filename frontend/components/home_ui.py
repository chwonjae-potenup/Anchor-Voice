"""
Home screen migrated with teammate-style logic:
- Mock account summary card
- Section cards (card/invest/insurance)
- Quick actions for transfer/simulator/news/face registration
"""

from __future__ import annotations

import streamlit as st


def _init_home_mock_state() -> None:
    defaults = {
        "home_account_name": "SUL 주거래 우대통장",
        "home_account_number": "110-482-190284",
        "home_account_balance": 12_850_320,
        "home_card_name": "SUL Prime 카드",
        "home_card_masked": "1234 •••• •••• 9402",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _format_currency(amount: int) -> str:
    return f"{int(amount):,}원"


def _fetch_home_account_summary() -> dict:
    return {
        "account_name": st.session_state.home_account_name,
        "account_number": st.session_state.home_account_number,
        "account_balance": st.session_state.home_account_balance,
    }


def _go_tab(tab_name: str) -> None:
    st.session_state.mobile_tab = tab_name
    st.rerun()


def _render_home_header() -> None:
    st.markdown(
        """
        <div class="kb-hero">
            <div class="kb-hero-kicker">SUL STYLE HOME · ANCHOR VOICE</div>
            <h2>내 금융 홈</h2>
            <p>실제 모바일 뱅킹처럼 보이는 구조 위에 안심 이체, 얼굴 인증, 음성 검증 흐름을 연결했습니다.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_account_transfer_card(state) -> None:
    summary = _fetch_home_account_summary()
    st.markdown(
        f"""
        <div class="av-home-account-card">
          <div class="av-home-account-kicker">💶 {summary["account_name"]}</div>
          <div class="av-home-account-number">{summary["account_number"]}</div>
          <div class="av-home-account-balance">{_format_currency(summary["account_balance"])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("이체", key="home_go_transfer", use_container_width=True, type="primary"):
        st.session_state.mobile_tab = "안심이체"
        state.go_to("transfer")


def _render_info_card(title: str, subtitle: str, badge: str) -> None:
    st.markdown(
        f"""
        <div class="av-home-info-card">
          <div class="av-home-info-badge">{badge}</div>
          <div class="av-home-info-title">{title}</div>
          <div class="av-home-info-subtitle">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_bottom_navigation() -> None:
    st.markdown(
        """
        <div class="av-home-bottom-nav">
          <div class="av-home-bottom-item av-home-bottom-item-active">🏠 홈</div>
          <div class="av-home-bottom-item">💳 금융</div>
          <div class="av-home-bottom-item">🎁 혜택</div>
          <div class="av-home-bottom-item">📈 주식</div>
          <div class="av-home-bottom-item">☰ 전체</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render(state):
    _init_home_mock_state()
    _render_home_header()

    if st.session_state.get("transfer_recent_action_message"):
        st.info(st.session_state.transfer_recent_action_message)

    st.markdown("### 주거래 계좌")
    _render_account_transfer_card(state)

    st.markdown("### 금융 요약")
    _render_info_card(
        title=st.session_state.home_card_name,
        subtitle=f"{st.session_state.home_card_masked} · 이번 달 결제예정 428,500원",
        badge="💳",
    )
    _render_info_card(
        title="SUL 투자계좌",
        subtitle="해외주식 · ETF · 모의 수익률 +4.28%",
        badge="📈",
    )
    _render_info_card(
        title="생활안심 보험 관리",
        subtitle="보장 확인, 납입 일정, 증명서 발급을 한 번에 확인하세요.",
        badge="🛡️",
    )

    st.markdown("### 빠른 실행")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("체험관", key="home_go_simulator", use_container_width=True):
            _go_tab("체험관")
    with col2:
        if st.button("피싱소식", key="home_go_news", use_container_width=True):
            _go_tab("피싱소식")

    col3, col4 = st.columns(2)
    with col3:
        if st.button("안면등록", key="home_go_face_reg", use_container_width=True):
            _go_tab("안면등록")
    with col4:
        if st.button("안심이체", key="home_go_transfer_alt", use_container_width=True):
            st.session_state.mobile_tab = "안심이체"
            state.go_to("transfer")

    _render_bottom_navigation()
