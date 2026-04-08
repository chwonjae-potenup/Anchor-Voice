"""
Phishing notice board (youth-focused).
"""

from __future__ import annotations

import streamlit as st


POSTS = [
    {
        "date": "2026-04-05",
        "category": "기관사칭형",
        "title": "검찰 공문·영장 이미지 전송 후 안전계좌 이체 유도",
        "summary": "공문 이미지를 보내며 신뢰를 만든 뒤 자산 검증 명목으로 이체를 요구하는 사례가 증가했습니다.",
        "action": "대표번호 재확인 후 즉시 통화 종료, 앱 내 신고 버튼 사용",
    },
    {
        "date": "2026-04-03",
        "category": "셀프 감금형",
        "title": "모텔 이동 + 공기계 개통 + 부모 연락 차단 지시",
        "summary": "기밀 유지 명목으로 고립을 유도하고 원격 앱 설치를 강요하는 패턴입니다.",
        "action": "주변 성인 1명에게 위치 공유, 데이터/와이파이 끄라는 요구 즉시 거절",
    },
    {
        "date": "2026-04-01",
        "category": "가담 유도형",
        "title": "고액 알바로 현금 수거/인출 전달 업무 모집",
        "summary": "채권 회수·심부름 알바처럼 위장하지만 보이스피싱 전달책 가담 위험이 큽니다.",
        "action": "출처 불명 고수익 금융 알바는 지원 금지, 계좌/카드 전달 절대 금지",
    },
    {
        "date": "2026-03-30",
        "category": "원격제어형",
        "title": "보안 앱 설치 유도 후 통화·문자 감시",
        "summary": "원격 제어앱 설치 후 금융 앱 접근을 유도해 계좌를 탈취하는 방식입니다.",
        "action": "알 수 없는 링크·APK 설치 금지, 설치 즉시 삭제 후 비밀번호 변경",
    },
]


def render():
    st.markdown("## 피싱 소식")
    st.caption("10~20대 타깃 수법을 중심으로 최근 패턴과 대응법을 제공합니다.")
    st.markdown("---")

    categories = ["전체"] + sorted({p["category"] for p in POSTS})
    selected = st.selectbox("유형 필터", categories, index=0)

    filtered = POSTS if selected == "전체" else [p for p in POSTS if p["category"] == selected]
    if not filtered:
        st.info("선택한 유형의 소식이 없습니다.")
        return

    for post in filtered:
        st.markdown(
            f"""
            <div class="kb-news-card">
                <div class="kb-news-meta">{post["date"]} · {post["category"]}</div>
                <h4>{post["title"]}</h4>
                <p>{post["summary"]}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.success(f"대응: {post['action']}")
