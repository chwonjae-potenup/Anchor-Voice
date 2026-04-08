"""
frontend/app.py
Mobile-first Anchor-Voice app shell.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import streamlit as st

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend import state_manager as state
from frontend.components import (
    auth_fallback_ui,
    face_ui,
    home_ui,
    notice_board_ui,
    result_ui,
    simulator_ui,
    stealth_ui,
    transfer_ui,
    voice_ui,
)


st.set_page_config(
    page_title="KB 안심뱅킹 | Anchor-Voice",
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

def _load_global_css() -> None:
    css_path = Path(__file__).resolve().parent / "static" / "styles.css"
    if not css_path.exists():
        return
    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


_load_global_css()

st.markdown(
    """
    <div class="kb-app-header">
        <div class="kicker">KB Youth Safe Banking | 10~20 Target</div>
        <h1>🛡️ 10~20 피싱 안심센터</h1>
        <p>"나는 안 당한다"는 방심을 깨는 10~20대 특화 피싱 예방 서비스</p>
    </div>
    """,
    unsafe_allow_html=True,
)

state.init_state()

if "mobile_tab" not in st.session_state:
    st.session_state.mobile_tab = "안심홈"

tabs = ["안심홈", "안심이체", "체험관", "피싱소식", "안면등록"]
current_tab = st.radio(
    "메뉴",
    tabs,
    index=tabs.index(st.session_state.mobile_tab) if st.session_state.mobile_tab in tabs else 0,
    horizontal=True,
    label_visibility="collapsed",
)
st.session_state.mobile_tab = current_tab

st.markdown("---")


def _render_transfer_flow():
    screen = state.get_screen()

    if screen == "transfer":
        transfer_ui.render(state)
    elif screen == "face":
        face_ui.render(state)
    elif screen == "voice":
        voice_ui.render(state)
    elif screen == "additional_auth":
        auth_fallback_ui.render(state)
    elif screen == "stealth":
        stealth_ui.render(state)
    elif screen == "result":
        result_ui.render(state)
    else:
        st.error(f"알 수 없는 화면: {screen}")
        state.go_to("transfer")


if current_tab == "안심홈":
    home_ui.render(state)
elif current_tab == "안심이체":
    _render_transfer_flow()
elif current_tab == "체험관":
    simulator_ui.render(state)
elif current_tab == "피싱소식":
    notice_board_ui.render()
else:
    face_ui.render_registration()
