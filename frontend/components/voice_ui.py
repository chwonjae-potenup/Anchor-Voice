"""
Voice authentication UI:
- TTS question playback (backend -> browser fallback)
- microphone recording
- STT transcription
- phishing analysis progression
"""
from __future__ import annotations

import httpx
import streamlit as st

from frontend.api_config import API_BASE
from frontend.components.audio_helpers import play_tts, transcribe_audio

DEFAULT_MAX_QUESTIONS = 5
DEFAULT_YOUTH_AGE_GROUP = "10~20대"


def _safe_max_questions() -> int:
    raw = int(st.session_state.get("voice_max_questions", DEFAULT_MAX_QUESTIONS) or DEFAULT_MAX_QUESTIONS)
    return max(3, min(raw, 10))


def render(state):
    st.markdown("## 5단계 음성 확인")
    st.markdown(
        "> 질문을 음성으로 읽어드립니다.\n"
        "> 마이크 버튼으로 답변하면 텍스트로 인식됩니다."
    )
    st.markdown("---")

    if "voice_step" not in st.session_state:
        st.session_state.voice_step = 1
    if "voice_log" not in st.session_state:
        st.session_state.voice_log = []
    if "voice_done" not in st.session_state:
        st.session_state.voice_done = False
    if "voice_max_questions" not in st.session_state:
        st.session_state.voice_max_questions = _safe_max_questions()
    if "voice_current_question" not in st.session_state:
        st.session_state.voice_current_question = None

    _render_history(st.session_state.voice_log)

    if st.session_state.voice_done:
        _finalize(state, st.session_state.voice_log)
        return

    current_q = st.session_state.voice_current_question
    if current_q is None:
        current_q = _fetch_next_question(
            st.session_state.voice_log,
            st.session_state.voice_max_questions,
        )
        if current_q.get("done"):
            st.session_state.voice_done = True
            st.rerun()
            return
        st.session_state.voice_current_question = current_q
        st.session_state.voice_step = int(current_q["id"])

    step = st.session_state.voice_step
    if step > _safe_max_questions():
        st.session_state.voice_done = True
        st.rerun()
        return

    _render_current_question(current_q, state)


def _render_history(log: list[dict]):
    if not log:
        return

    with st.expander(f"대화 기록 ({len(log)}개)", expanded=True):
        for item in log:
            st.markdown(f"**Q{item['question_id']}** {item['question']}")
            answer = (item.get("answer_text") or "").strip()
            if answer:
                st.markdown(
                    "<div style='background:#1e3a5f;border-radius:8px;"
                    "padding:0.5rem 1rem;margin:0.3rem 0;color:#90cdf4;'>"
                    f"답변: {answer}</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.caption("무응답")
            st.markdown("---")


def _render_current_question(question: dict, state):
    total = _safe_max_questions()
    step = st.session_state.voice_step

    st.progress(step / total, text=f"질문 {step} / {total}")
    st.markdown(f"### 질문 {step}")
    st.markdown(
        "<div class='kb-voice-question-card' "
        "style='background:#2d3748;border-left:4px solid #60a5fa;"
        "border-radius:10px;padding:1rem;font-size:1.1rem;color:#f8fafc;'>"
        f"<span style='color:#f8fafc;'>{question['text']}</span></div>",
        unsafe_allow_html=True,
    )
    reason = (question.get("reason") or "").strip()
    if reason:
        st.caption(f"질문 목적: {reason}")

    col_tts, _ = st.columns([1, 3])
    with col_tts:
        if st.button("다시 듣기", key=f"tts_{step}"):
            _play_tts(question["text"])

    tts_key = f"tts_played_{step}"
    if tts_key not in st.session_state:
        st.session_state[tts_key] = True
        _play_tts(question["text"])

    st.markdown("---")
    st.markdown("##### 마이크로 답변해 주세요")
    st.caption("버튼 클릭으로 녹음 시작/정지")

    try:
        from audio_recorder_streamlit import audio_recorder

        audio_bytes = audio_recorder(
            text="녹음 시작/정지",
            recording_color="#e74c3c",
            neutral_color="#2ecc71",
            icon_name="microphone",
            icon_size="2x",
            pause_threshold=2.0,
            key=f"recorder_{step}",
        )
    except ImportError:
        st.error("audio-recorder-streamlit 패키지가 필요합니다: `uv pip install audio-recorder-streamlit`")
        audio_bytes = None

    if not audio_bytes:
        return

    st.audio(audio_bytes, format="audio/wav")
    with st.spinner("음성을 텍스트로 변환하는 중..."):
        answer_text = _transcribe(audio_bytes)

    if answer_text:
        _render_answer_confirm(question, answer_text, state)
        return

    st.warning("음성 인식에 실패했습니다. 아래에 직접 입력해 진행할 수 있습니다.")
    manual_key = f"manual_answer_{step}"
    manual_answer = st.text_input("직접 입력", key=manual_key).strip()
    if manual_answer:
        if st.button("직접 입력으로 다음 질문", key=f"manual_confirm_{step}", type="primary"):
            _submit_answer(question, manual_answer, state)


def _render_answer_confirm(question: dict, answer_text: str, state):
    step = st.session_state.voice_step
    tts_key = f"tts_played_{step}"

    st.markdown(
        "<div class='kb-voice-answer-card' style='background:#1a202c;border:1px solid #4299e1;"
        "border-radius:8px;padding:0.8rem 1rem;margin:0.5rem 0;color:#e2e8f0;'>"
        f"<b style='color:#bfdbfe;'>인식된 답변:</b> <span style='color:#e2e8f0;'>{answer_text}</span></div>",
        unsafe_allow_html=True,
    )

    col_confirm, col_retry = st.columns(2)
    with col_confirm:
        if st.button("확인 (다음 질문)", use_container_width=True, key=f"confirm_{step}"):
            _submit_answer(question, answer_text, state)
    with col_retry:
        if st.button("다시 녹음", use_container_width=True, key=f"retry_{step}"):
            if tts_key in st.session_state:
                del st.session_state[tts_key]
            st.rerun()


def _fetch_next_question(log: list[dict], max_questions: int) -> dict:
    """
    Get next adaptive question from backend.
    Falls back to static anchor questions when API call fails.
    """
    payload = {
        "conversation_log": log,
        "max_questions": max(3, min(int(max_questions), 10)),
        "age_group": st.session_state.get("user_age_group", DEFAULT_YOUTH_AGE_GROUP),
    }

    try:
        resp = httpx.post(
            f"{API_BASE}/api/auth/voice/next-question",
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("done"):
            return {"done": True}
        return {
            "done": False,
            "id": int(data.get("question_id", len(log) + 1)),
            "text": data.get("question_text", ""),
            "intent": data.get("question_intent", ""),
            "reason": data.get("reason", ""),
        }
    except Exception as e:
        st.warning(f"질문 생성 API 실패로 기본 질문으로 진행합니다: {e}")
        try:
            from ai.llm_engine import FIRST_QUESTION_INTENT, FIRST_QUESTION_TEXT
            from ai.anchor_prompts import ANCHOR_QUESTIONS

            step = len(log) + 1
            if step == 1:
                return {
                    "done": False,
                    "id": 1,
                    "text": FIRST_QUESTION_TEXT,
                    "intent": FIRST_QUESTION_INTENT,
                    "reason": "질문 생성 API 실패로 1번 기본 사유 질문 사용",
                }
            if step > len(ANCHOR_QUESTIONS):
                return {"done": True}
            q = ANCHOR_QUESTIONS[step - 1]
            return {
                "done": False,
                "id": q["id"],
                "text": q["text"],
                "intent": "anchor_fallback",
                "reason": "백엔드 질문 생성 실패로 고정 질문 사용",
            }
        except Exception:
            return {"done": True}


def _play_tts(text: str):
    play_tts(text, timeout=15)


def _transcribe(audio_bytes: bytes) -> str:
    text, error = transcribe_audio(audio_bytes, lang="ko", timeout=30)
    if error:
        st.warning(f"STT 실패: {error}")
    return text


def _submit_answer(question: dict, answer_text: str, state):
    if _should_force_block_locally(question, answer_text):
        st.session_state.phishing_result = {
            "is_phishing": True,
            "confidence": 0.95,
            "phishing_type": "agency_fraud",
            "summary": "질문 1에서 기관 이체 지시를 인정해 즉시 차단합니다.",
            "triggered_questions": [int(question.get("id", 1))],
            "recommended_action": "block",
            "risk_tier": "high",
        }
        st.session_state.voice_gate_passed = False
        st.session_state.voice_gate_status = "block"
        state.go_to("stealth")
        return

    log_entry = {
        "question_id": question["id"],
        "question": question["text"],
        "question_intent": question.get("intent", ""),
        "answer_text": answer_text,
    }
    st.session_state.voice_log.append(log_entry)

    with st.spinner("분석 중..."):
        prev_log = st.session_state.voice_log[:-1]
        try:
            resp = httpx.post(
                f"{API_BASE}/api/auth/voice/answer",
                json={
                    "question_id": question["id"],
                    "question_text": question["text"],
                    "question_intent": question.get("intent", ""),
                    "answer_text": answer_text,
                    "max_questions": _safe_max_questions(),
                    "age_group": st.session_state.get("user_age_group", DEFAULT_YOUTH_AGE_GROUP),
                    "conversation_log": prev_log,
                },
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as e:
            # Fail-closed: never proceed silently when risk analysis call fails.
            st.session_state.additional_auth_reason = f"음성 위험 분석 실패({e})로 추가 인증이 필요합니다."
            st.session_state.additional_auth_source = "voice"
            st.session_state.voice_gate_passed = False
            st.session_state.voice_gate_status = "analysis_failed"
            state.go_to("additional_auth")
            return

        try:
            result = resp.json()
        except Exception as e:
            st.session_state.additional_auth_reason = f"음성 분석 응답 파싱 실패({e})로 추가 인증이 필요합니다."
            st.session_state.additional_auth_source = "voice"
            st.session_state.voice_gate_passed = False
            st.session_state.voice_gate_status = "analysis_failed"
            state.go_to("additional_auth")
            return

        if _route_by_gate_action(result, state):
            return

    if question["id"] >= _safe_max_questions():
        st.session_state.voice_done = True
    else:
        next_q = _fetch_next_question(
            st.session_state.voice_log,
            _safe_max_questions(),
        )
        if next_q.get("done"):
            st.session_state.voice_done = True
            st.session_state.voice_current_question = None
            st.rerun()
            return

        st.session_state.voice_current_question = next_q
        st.session_state.voice_step = int(next_q["id"])
        next_tts_key = f"tts_played_{st.session_state.voice_step}"
        if next_tts_key in st.session_state:
            del st.session_state[next_tts_key]

    st.rerun()


def _finalize(state, log: list[dict]):
    st.markdown("### 최종 분석 중...")
    with st.spinner("AI가 대화 내용을 분석하고 있습니다..."):
        if not log:
            # Risk-required voice flow cannot finish without any answer.
            if bool(st.session_state.get("require_voice_after_identity", False)):
                st.session_state.additional_auth_reason = "음성 검증 응답이 없어 추가 인증이 필요합니다."
                st.session_state.additional_auth_source = "voice"
                st.session_state.voice_gate_passed = False
                st.session_state.voice_gate_status = "no_answer"
                state.go_to("additional_auth")
            else:
                st.session_state.auth_method = "음성 질의응답 (무응답 종료)"
                st.session_state.voice_gate_passed = True
                st.session_state.voice_gate_status = "proceed"
                state.go_to("result")
            return

        last_entry = log[-1]
        last_log = log[:-1]
        last_answer = last_entry.get("answer_text", "")

        try:
            resp = httpx.post(
                f"{API_BASE}/api/auth/voice/answer",
                json={
                    "question_id": last_entry.get("question_id", 1),
                    "question_text": last_entry.get("question", ""),
                    "question_intent": last_entry.get("question_intent", ""),
                    "answer_text": last_answer,
                    "max_questions": _safe_max_questions(),
                    "age_group": st.session_state.get("user_age_group", DEFAULT_YOUTH_AGE_GROUP),
                    "conversation_log": last_log,
                },
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()
        except Exception as e:
            st.session_state.additional_auth_reason = f"최종 음성 분석 실패({e})로 추가 인증이 필요합니다."
            st.session_state.additional_auth_source = "voice"
            st.session_state.voice_gate_passed = False
            st.session_state.voice_gate_status = "analysis_failed"
            state.go_to("additional_auth")
            return

        st.session_state.phishing_result = result
        if _route_by_gate_action(result, state):
            return
        # Final step must be fail-closed: if backend didn't return a terminal action,
        # never allow silent transfer completion.
        st.session_state.additional_auth_reason = (
            "음성 위험 판단 결과가 확정되지 않아(terminal action 누락) "
            "추가 인증이 필요합니다."
        )
        st.session_state.additional_auth_source = "voice"
        st.session_state.voice_gate_passed = False
        st.session_state.voice_gate_status = "analysis_inconclusive"
        state.go_to("additional_auth")


def _route_by_gate_action(result: dict, state) -> bool:
    action = str(result.get("recommended_action", "")).strip().lower()

    # Backward compatibility for legacy payloads without recommended_action.
    if not action:
        if result.get("is_phishing") and result.get("phishing_type") not in {"pending", "normal"}:
            action = "block"
        else:
            action = "pending"

    if action == "block":
        st.session_state.phishing_result = result
        st.session_state.voice_gate_passed = False
        st.session_state.voice_gate_status = "block"
        state.go_to("stealth")
        return True

    if action == "additional_auth":
        reason = result.get("summary") or "의심 신호가 있어 추가 인증이 필요합니다."
        st.session_state.additional_auth_reason = f"음성 위험 판단 결과: {reason}"
        st.session_state.additional_auth_source = "voice"
        st.session_state.voice_gate_passed = False
        st.session_state.voice_gate_status = "additional_auth"
        state.go_to("additional_auth")
        return True

    if action == "proceed":
        st.session_state.auth_method = "음성 질의응답 (LLM/CDD)"
        st.session_state.voice_gate_passed = True
        st.session_state.voice_gate_status = "proceed"
        state.go_to("result")
        return True

    if action == "pending":
        st.session_state.voice_gate_passed = False
        st.session_state.voice_gate_status = "pending"

    return False


def _should_force_block_locally(question: dict, answer_text: str) -> bool:
    """
    Frontend hard safety net:
    if backend response is stale/misconfigured, block obvious high-risk admission.
    """
    intent = str(question.get("intent", "")).strip().lower()
    text = (answer_text or "").strip().lower()
    if not text:
        return False
    question_id = int(question.get("id", 0) or 0)
    question_text = str(question.get("text", "") or "")
    is_agency_q1 = question_id == 1 and any(k in question_text for k in ["공공기관", "경찰", "검찰", "금감원"])
    if intent not in {"agency_directive", "anchor_fallback"} and not is_agency_q1:
        return False

    compact = "".join(text.split())
    negative_signals = ["아니", "없", "안받", "받지않", "아닙"]
    if any(k in compact for k in negative_signals):
        return False

    yes_signals = ["네", "예", "맞", "응", "그렇", "지시받", "요구받", "하라고", "받았습니다", "받았어요", "받았어"]
    directive_signals = ["지시", "요구", "이체하라", "현금전달", "보내라고", "옮기라고", "안전계좌"]
    return any(k in text for k in yes_signals) or any(k in compact for k in directive_signals)
