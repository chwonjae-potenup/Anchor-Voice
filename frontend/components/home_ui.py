"""
Mobile-first home dashboard for anti-phishing service.
"""

from __future__ import annotations

import streamlit as st


def render(state):
    st.markdown(
        """
        <div class="kb-hero">
            <div class="kb-hero-kicker">10~20대 특화 피싱 예방</div>
            <h2>10~20 피싱 안심센터</h2>
            <p>“나는 안 당해”라는 생각이 가장 위험합니다. 이체 전 30초 점검으로 먼저 확인하세요.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 오늘의 경보")
    alerts = [
        {
            "tag": "기관사칭형",
            "title": "가짜 공문 + 안전계좌 이체 요구",
            "desc": "검찰·경찰·금감원은 전화로 자금 이체를 지시하지 않습니다.",
        },
        {
            "tag": "셀프 감금형",
            "title": "모텔 이동·공기계 개통·연락차단 지시",
            "desc": "주변에 알리지 말라는 요구는 고위험 신호입니다.",
        },
        {
            "tag": "가담 유도형",
            "title": "고액 알바로 현금 수거/인출책 모집",
            "desc": "모르는 사람의 자금 전달 업무는 범죄 가담 위험이 높습니다.",
        },
    ]

    for alert in alerts:
        st.markdown(
            f"""
            <div class="kb-alert-card">
                <span class="kb-alert-tag">{alert["tag"]}</span>
                <h4>{alert["title"]}</h4>
                <p>{alert["desc"]}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("### 빠른 실행")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("안심 이체 시작", use_container_width=True, type="primary"):
            st.session_state.mobile_tab = "안심이체"
            state.go_to("transfer")
    with col2:
        if st.button("체험관 퀵입장", use_container_width=True):
            st.session_state.mobile_tab = "체험관"
            st.rerun()

    col3, col4 = st.columns(2)
    with col3:
        if st.button("피싱 소식 보기", use_container_width=True):
            st.session_state.mobile_tab = "피싱소식"
            st.rerun()
    with col4:
        if st.button("안면 등록", use_container_width=True):
            st.session_state.mobile_tab = "안면등록"
            st.rerun()
