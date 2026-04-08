"""
Hands-on phishing simulation for youth users.
"""

from __future__ import annotations

import streamlit as st


SCENARIOS = {
    "기관사칭: 안전계좌 이체 유도": {
        "script": [
            "수사관: 당신 명의 계좌가 범죄에 연루되었습니다.",
            "수사관: 무죄 입증을 위해 안전계좌로 잠시 이체해야 합니다.",
            "수사관: 가족이나 은행 직원에게 절대 말하지 마세요.",
        ],
        "options": [
            "기관이 전화로 이체 지시",
            "안전계좌 이체 요구",
            "비밀 유지 강요",
            "정상적인 카드 배송 안내",
        ],
        "correct": {
            "기관이 전화로 이체 지시",
            "안전계좌 이체 요구",
            "비밀 유지 강요",
        },
    },
    "셀프 감금: 모텔 이동 + 공기계 지시": {
        "script": [
            "상대: 사건 기밀이라 지금부터 누구와도 연락하면 안 됩니다.",
            "상대: 모텔로 이동해서 공기계 하나 개통하세요.",
            "상대: 제가 보내는 앱을 설치하고 지시대로만 하세요.",
        ],
        "options": [
            "연락 차단 지시",
            "격리 장소 이동 지시",
            "원격/앱 설치 지시",
            "정상적인 본인확인 절차",
        ],
        "correct": {
            "연락 차단 지시",
            "격리 장소 이동 지시",
            "원격/앱 설치 지시",
        },
    },
    "가담 유도: 고액 알바 현금 수거": {
        "script": [
            "모집자: 하루 2시간 고액 알바, 현금만 전달하면 됩니다.",
            "모집자: 채권 회수 업무라서 계좌로 돈 받으면 바로 인출해 주세요.",
            "모집자: 통장·체크카드 맡겨주면 수당을 더 드립니다.",
        ],
        "options": [
            "고액 단기 알바 미끼",
            "현금 수거·인출 전달 요구",
            "통장/카드 제공 요구",
            "공식 채용 공고 링크 제공",
        ],
        "correct": {
            "고액 단기 알바 미끼",
            "현금 수거·인출 전달 요구",
            "통장/카드 제공 요구",
        },
    },
}


def render(state):
    st.markdown("## 피싱 체험관")
    st.caption("10~20대 실제 타깃 패턴을 짧게 체험하고 위험 신호를 찾는 훈련입니다.")
    st.markdown("---")

    scenario_name = st.selectbox("시나리오 선택", list(SCENARIOS.keys()))
    scenario = SCENARIOS[scenario_name]

    st.markdown("### 통화 상황")
    for line in scenario["script"]:
        st.markdown(f"- {line}")

    st.markdown("### 위험 신호 체크")
    selected = st.multiselect(
        "해당 시나리오에서 의심되는 항목을 모두 고르세요.",
        scenario["options"],
    )

    if st.button("채점하기", use_container_width=True, key="sim_score_btn"):
        if not selected:
            st.warning("의심 신호를 1개 이상 선택한 뒤 채점해 주세요.")
        else:
            selected_set = set(selected)
            correct = scenario["correct"]
            missed = correct - selected_set
            wrong = selected_set - correct

            if not missed and not wrong:
                st.success("정답입니다. 실제 대응에서도 즉시 통화 종료 후 공식 채널 재확인이 핵심입니다.")
            else:
                if missed:
                    st.warning(f"놓친 신호: {', '.join(sorted(missed))}")
                if wrong:
                    st.info(f"재검토 항목: {', '.join(sorted(wrong))}")
                st.error("한 번 더 체크해보세요. 피싱은 복합 신호로 판단해야 합니다.")

    st.markdown("---")
    if st.button("이 시나리오 기준으로 안심 이체 시작", use_container_width=True):
        st.session_state.mobile_tab = "안심이체"
        state.go_to("transfer")
