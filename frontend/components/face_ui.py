"""
Face authentication UI.

Flow:
1) Face verify with registered image
2) Video mission challenge (two actions in sequence)
"""
from __future__ import annotations

import os
from typing import Any

import httpx
import streamlit as st

from frontend.api_config import API_BASE
from frontend.components.audio_helpers import play_tts
from frontend.components.video_capture import frames_to_bytes_list, render_video_capture


def render(state) -> None:
    st.markdown(
        """
        <div class="av-face-hero">
          <div class="av-face-hero-kicker">FACE AUTH · SAFE TRANSFER</div>
          <div class="av-face-hero-title">안면 인증으로 본인 여부를 확인합니다</div>
          <div class="av-face-hero-desc">
            얼굴 확인과 동작 미션을 통과하면, 위험도에 따라 음성 검증 또는 송금 완료 단계로 이동합니다.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    score = st.session_state.get("risk_score", 0)
    transfer_data = st.session_state.get("transfer_data", {}) or {}
    transfer_amount = int(transfer_data.get("amount", 0) or 0)
    primary_high_amount_trigger = transfer_amount >= 10_000_000
    require_voice = bool(st.session_state.get("require_voice_after_identity", False)) or primary_high_amount_trigger

    # Defensive hard gate: high-amount transfers must pass voice verification.
    if primary_high_amount_trigger and not bool(st.session_state.get("require_voice_after_identity", False)):
        st.session_state.require_voice_after_identity = True
        st.session_state.transfer_ai_intervention_required = True
        st.session_state.transfer_primary_high_amount_trigger = True
        if "1차 트리거: 고액 송금" not in (st.session_state.get("transfer_trigger_reasons") or []):
            st.session_state.transfer_trigger_reasons = [
                "1차 트리거: 고액 송금",
                *(st.session_state.get("transfer_trigger_reasons") or []),
            ]
    if require_voice:
        st.info(f"위험 점수 **{score}점**: 안면 인증 후 음성(LLM) 검증까지 진행됩니다.")
    else:
        st.success(f"위험 점수 **{score}점**: 안면 인증 완료 시 송금 단계로 진행합니다.")

    if not os.path.exists("registered_face.jpg"):
        _reset_face_state()
        _go_to_additional_auth(state, "등록된 얼굴 정보가 없어 추가 인증이 필요합니다.")
        return

    if "face_stage" not in st.session_state:
        st.session_state.face_stage = "verify"

    stage = st.session_state.face_stage
    if stage == "verify":
        _render_stage1_verify(state)
    elif stage == "challenge":
        _render_sequence_challenge(state)
    elif stage == "done":
        st.success("안면 인증이 완료되었습니다.")
        st.session_state.auth_method = "안면 인증 + 동작 시퀀스"
        _reset_face_state()
        if require_voice:
            st.session_state.voice_gate_passed = False
            st.session_state.voice_gate_status = "required"
            state.go_to("voice")
        else:
            st.session_state.voice_gate_passed = True
            st.session_state.voice_gate_status = "not_required"
            state.go_to("result")

    if st.button("다른 인증수단으로 진행", key="to_additional_auth"):
        _reset_face_state()
        _go_to_additional_auth(state, "안면 인증 대신 추가 인증으로 진행합니다.")


def render_registration() -> None:
    st.markdown(
        """
        <div class="av-face-stage-card">
          <div class="av-face-step-label">Face Register</div>
          <div class="av-face-step-title">기준 얼굴 등록</div>
          <div class="av-face-step-subtitle">최초 1회만 등록하면 이후 안면 인증에 사용됩니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if os.path.exists("registered_face.jpg"):
        st.success("이미 얼굴이 등록되어 있습니다.")
        if st.button("다시 등록하기 (기존 이미지 삭제)", key="re_register"):
            os.remove("registered_face.jpg")
            st.rerun()
        return

    st.info("처음 사용 시, 본인 얼굴 등록이 필요합니다.")
    st.caption("정면에서 밝은 환경으로 촬영해 주세요.")

    reg_img = st.camera_input("기준 얼굴 등록 (정면 촬영)", key="register_cam")
    if reg_img is None:
        return

    with st.spinner("얼굴 등록 중..."):
        try:
            resp = httpx.post(
                f"{API_BASE}/api/auth/face/register",
                files={"file": ("face.jpg", reg_img.getvalue(), "image/jpeg")},
                timeout=120,
            )
            result = resp.json()
            if result.get("verified"):
                st.success("얼굴 등록 완료")
                st.rerun()
            else:
                st.error(f"등록 실패: {result.get('message', '')}")
        except Exception as e:
            st.error(f"서버 오류: {e}")


def _render_stage1_verify(state) -> None:
    st.markdown(
        """
        <div class="av-face-stage-card">
          <div class="av-face-step-label">Step 1</div>
          <div class="av-face-step-title">얼굴 확인</div>
          <div class="av-face-step-subtitle">등록된 얼굴 사진과 현재 촬영 이미지를 비교합니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    img = st.camera_input("본인 확인 사진 촬영", key="verify_cam")
    if img is None:
        return

    with st.spinner("얼굴 확인 중..."):
        try:
            resp = httpx.post(
                f"{API_BASE}/api/auth/face",
                files={"file": ("face.jpg", img.getvalue(), "image/jpeg")},
                timeout=120,
            )
            result = resp.json()

            if result.get("verified"):
                st.success(f"얼굴 확인 완료 ({result.get('time_ms', 0)}ms)")
                st.session_state.face_stage = "challenge"
                st.rerun()
                return

            if result.get("fallback"):
                st.warning(f"{result.get('message', '인증 실패')} - 추가 인증으로 전환합니다.")
                _reset_face_state()
                _go_to_additional_auth(
                    state,
                    result.get("message", "안면 인증 시스템 오류로 추가 인증이 필요합니다."),
                )
                return

            st.error(result.get("message", "등록된 사진과 다른 사람입니다. 다시 인증해 주세요."))
            distance = result.get("distance")
            threshold = result.get("threshold")
            if isinstance(distance, (int, float)) and isinstance(threshold, (int, float)):
                st.caption(f"매칭 점수: {distance:.4f} / 허용 기준: {threshold:.4f}")
            elif isinstance(distance, (int, float)):
                st.caption(f"매칭 점수: {distance:.4f}")

        except httpx.TimeoutException:
            st.error("응답 시간 초과. 다시 시도해 주세요.")
        except Exception as e:
            st.error(f"서버 오류: {e}")


def _render_sequence_challenge(state) -> None:
    st.markdown(
        """
        <div class="av-face-stage-card">
          <div class="av-face-step-label">Step 2</div>
          <div class="av-face-step-title">동작 미션 (영상 분석)</div>
          <div class="av-face-step-subtitle">지시된 2개 동작을 순서대로 수행해 본인임을 추가 확인합니다.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "face_challenge" not in st.session_state:
        with st.spinner("미션 생성 중..."):
            try:
                resp = httpx.get(f"{API_BASE}/api/auth/face/challenge", timeout=10)
                st.session_state.face_challenge = resp.json()
            except Exception as e:
                st.error(f"미션 생성 오류: {e}")
                return

    challenge = st.session_state.face_challenge
    combined_text = challenge.get("combined_text", "")
    actions = challenge.get("actions", [])
    if len(actions) < 2:
        st.error("미션 데이터가 올바르지 않습니다.")
        return

    st.markdown(
        (
            "<div class='kb-face-instruction' style='background:#eff6ff;border-left:4px solid #2563eb;'>"
            "<div class='kb-face-instruction-title' style='color:#1d4ed8;'>지시사항</div>"
            f"<div style='color:#0f172a;'>{combined_text}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )

    tts_key = "face_challenge_tts_played"
    if tts_key not in st.session_state:
        st.session_state[tts_key] = True
        _play_tts(combined_text)

    if st.button("다시 듣기", key="challenge_tts_retry"):
        _play_tts(combined_text)

    st.markdown(
        f"""
<div class="kb-face-guide">
  <div class="kb-face-guide-title">수행 방법</div>
  <ol>
    <li>{actions[0]['text']}</li>
    <li>이어서 {actions[1]['text']}</li>
  </ol>
</div>
""",
        unsafe_allow_html=True,
    )
    st.caption("중요: 사진이 아니라 1회 영상 녹화로 순서를 검증합니다.")

    _render_video_challenge(actions, state)


def _render_video_challenge(actions: list[dict[str, Any]], state) -> None:
    capture_state_key = "face_challenge_frames_b64"
    capture_id_key = "face_challenge_capture_id"
    analyzed_capture_id_key = "face_challenge_analyzed_capture_id"
    result_key = "face_challenge_last_result"

    payload = render_video_capture(
        label="녹화 시작 (5초)",
        duration_ms=5000,
        fps=8,
        key="face_challenge_video_component",
        height=510,
    )

    if payload:
        capture_id = str(payload.get("capture_id", ""))
        frames_b64 = payload.get("frames", [])
        if capture_id and isinstance(frames_b64, list) and frames_b64:
            if capture_id != st.session_state.get(capture_id_key):
                st.session_state[capture_id_key] = capture_id
                st.session_state[capture_state_key] = frames_b64
                st.session_state.pop(result_key, None)

    captured = st.session_state.get(capture_state_key, [])
    capture_id = st.session_state.get(capture_id_key, "")
    analyzed_capture_id = st.session_state.get(analyzed_capture_id_key, "")

    if not captured:
        st.info("녹화 버튼을 누르고 두 동작을 순서대로 수행해 주세요.")
        return

    st.success(f"녹화 완료: {len(captured)} 프레임")

    # Auto-run analysis once per new capture.
    if capture_id and capture_id != analyzed_capture_id:
        st.session_state[analyzed_capture_id_key] = capture_id
        with st.spinner("동작 순서 분석 중..."):
            result = _detect_action_sequence(actions, frames_to_bytes_list(captured))
        st.session_state[result_key] = result
        _apply_sequence_result(state, result)
        return

    result = st.session_state.get(result_key)
    if result:
        if result.get("detected"):
            st.success("동작 시퀀스 확인 완료")
        else:
            st.warning(f"최근 분석 결과: {result.get('reason', '감지 실패')}")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("분석 다시 시도", key="reanalyze_sequence", type="primary"):
            with st.spinner("동작 순서 분석 중..."):
                result = _detect_action_sequence(actions, frames_to_bytes_list(captured))
            st.session_state[result_key] = result
            _apply_sequence_result(state, result)
    with col2:
        if st.button("다시 녹화", key="retry_sequence_capture"):
            st.session_state.pop(capture_state_key, None)
            st.session_state.pop(capture_id_key, None)
            st.session_state.pop(analyzed_capture_id_key, None)
            st.session_state.pop(result_key, None)
            st.rerun()


def _detect_action_sequence(actions: list[dict[str, Any]], frames_bytes: list[bytes]) -> dict:
    if len(frames_bytes) < 6:
        return {"detected": False, "reason": "유효 프레임이 부족합니다. 다시 촬영해 주세요."}
    try:
        files = [
            ("files", (f"frame_{idx}.jpg", b, "image/jpeg"))
            for idx, b in enumerate(frames_bytes)
        ]
        resp = httpx.post(
            f"{API_BASE}/api/auth/face/sequence-frames",
            data={
                "action1_id": actions[0]["id"],
                "action2_id": actions[1]["id"],
            },
            files=files,
            timeout=120,
        )
        if resp.status_code == 200:
            return resp.json()
        return {"detected": False, "reason": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"detected": False, "reason": str(e)}


def _apply_sequence_result(state, result: dict[str, Any]) -> None:
    if result.get("detected"):
        st.session_state.pop("face_fail_count", None)
        st.session_state.face_stage = "done"
        st.rerun()
        return
    _handle_challenge_fail(state, result.get("reason", "동작 순서 감지 실패"))


def _handle_challenge_fail(state, reason: str) -> None:
    fail_count = st.session_state.get("face_fail_count", 0) + 1
    st.session_state.face_fail_count = fail_count
    st.warning(f"동작이 감지되지 않았습니다. ({reason}) - {fail_count}/2회")

    if fail_count >= 2:
        st.error("동작 인증 2회 실패 - 추가 인증으로 전환합니다.")
        _reset_face_state()
        _go_to_additional_auth(state, "동작 인증이 반복 실패하여 추가 인증이 필요합니다.")


def _play_tts(text: str) -> None:
    play_tts(text, timeout=30)


def _go_to_additional_auth(state, reason: str) -> None:
    st.session_state.additional_auth_reason = reason
    st.session_state.additional_auth_source = "face"
    state.go_to("additional_auth")


def _reset_face_state() -> None:
    for key in [
        "face_stage",
        "face_challenge",
        "face_challenge_tts_played",
        "face_fail_count",
        "face_challenge_step",
        "challenge_action1_cam",
        "challenge_action2_cam",
        "face_challenge_frames_b64",
        "face_challenge_capture_id",
        "face_challenge_analyzed_capture_id",
        "face_challenge_last_result",
    ]:
        st.session_state.pop(key, None)
