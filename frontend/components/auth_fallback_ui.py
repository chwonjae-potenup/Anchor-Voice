"""
frontend/components/auth_fallback_ui.py
추가 인증 UI (공인인증서/비밀번호)
"""
import streamlit as st


def render(state):
    st.markdown("## 🔒 추가 인증")
    reason = st.session_state.get("additional_auth_reason")
    if reason:
        st.warning(reason)
        st.caption("안전을 위해 비밀번호 또는 공인인증서로 추가 인증을 진행합니다.")
    else:
        st.caption("비밀번호 또는 공인인증서로 인증을 진행합니다.")
    st.markdown("---")

    auth_type = st.radio("인증 방법 선택", ["비밀번호 (간편 인증)", "공인인증서 (데모)"])

    if auth_type == "비밀번호 (간편 인증)":
        pw = st.text_input("계좌 비밀번호 (숫자 4자리)", type="password", max_chars=4)
        if st.button("인증하기", type="primary", use_container_width=True):
            if len(pw) == 4 and pw.isdigit():
                st.success("✅ 비밀번호 인증 완료!")
                _complete(state, "비밀번호 추가 인증")
            else:
                st.error("비밀번호 숫자 4자리를 정확히 입력해주세요.")

    elif auth_type == "공인인증서 (데모)":
        st.info("💾 [이동식 디스크] 홍길동_개인 (만료일: 2026-12-31)")
        cert_pw = st.text_input("공인인증서 암호", type="password")
        if st.button("인증서 전자서명 →", type="primary", use_container_width=True):
            if len(cert_pw) >= 4:
                st.success("✅ 전자서명 완료!")
                _complete(state, "공인인증서 추가 인증")
            else:
                st.error("전자서명 암호를 입력해주세요.")


def _complete(state, auth_method: str):
    st.session_state.auth_method = auth_method
    source = st.session_state.get("additional_auth_source")
    require_voice = bool(st.session_state.get("require_voice_after_identity", False))
    st.session_state.pop("additional_auth_reason", None)
    st.session_state.pop("additional_auth_source", None)
    if source == "face" and require_voice:
        st.session_state.voice_gate_passed = False
        st.session_state.voice_gate_status = "required"
        state.go_to("voice")
        return
    if source == "voice":
        st.session_state.voice_gate_passed = True
        st.session_state.voice_gate_status = "additional_auth_passed"
        state.go_to("result")
        return
    if require_voice:
        # Fail-closed: if high/medium-risk transfer still requires voice, do not bypass it.
        st.session_state.voice_gate_passed = False
        st.session_state.voice_gate_status = "required"
        state.go_to("voice")
        return
    state.go_to("result")
