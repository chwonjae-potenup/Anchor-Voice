"""
frontend/components/transfer_ui.py  — Frontend Agent
이체 정보 입력 화면

백엔드 의존성 최소화: CDD 점수 계산을 로컬에서 직접 수행하여
서버 타임아웃 문제 완전 제거. 서버가 없어도 이체 흐름 동작.
"""
import streamlit as st
import httpx
from datetime import datetime
from frontend.components.bank_utils import BANKS, validate_and_format_account
from frontend.api_config import API_BASE

# 임계값 (ai/cdd_scorer.py와 동일)
HIGH_RISK_THRESHOLD = 70


def _reset_voice_state() -> None:
    for key in [
        "voice_step",
        "voice_log",
        "voice_done",
        "voice_max_questions",
        "voice_current_question",
        "voice_gate_passed",
        "voice_gate_status",
    ]:
        st.session_state.pop(key, None)


def _local_risk_score(amount: int, hour: int, is_new: bool, is_blacklisted: bool) -> dict:
    """서버 없이 브라우저 쪽에서 직접 CDD 위험도 계산"""
    score = 0
    reasons = []

    if is_blacklisted:
        score += 70
        reasons.append("블랙리스트 수취 계좌")
    if is_new:
        score += 20
        reasons.append("처음 이체하는 신규 계좌")
    if amount >= 1_000_000:
        score += 15
        reasons.append(f"고액 이체 ({amount:,}원)")
    if hour >= 22 or hour < 6:
        score += 10
        reasons.append(f"야간 거래 ({hour}시)")

    score = min(score, 100)

    if score >= HIGH_RISK_THRESHOLD:
        level = "high"
    elif score < 30:
        level = "low"
    else:
        level = "medium"

    return {"risk_score": score, "risk_level": level, "reason": reasons}


def _fetch_risk_from_backend(payload: dict) -> dict:
    """Call backend risk-check API."""
    resp = httpx.post(
        f"{API_BASE}/api/transfer/risk-check",
        json=payload,
        timeout=8,
    )
    resp.raise_for_status()
    return resp.json()


def render(state):
    st.markdown("## 💳 이체 정보 입력")
    st.caption("본 서비스는 10~20대 피싱 타깃 시나리오에 맞춰 동작합니다.")
    st.markdown("---")

    # 은행 목록 + 기타 옵션
    bank_options = list(BANKS.keys()) + ["기타(직접입력)"]

    with st.form("transfer_form"):
        # NOTE: 현재 서비스는 10~20대 타깃으로 고정 운용합니다.
        # 연령대 선택 UI는 향후 멀티 세그먼트 재오픈 시 복구합니다.
        # age_options = ["선택해 주세요", "10대", "20대", "30대", "40대", "50대+"]
        # prev_age = st.session_state.get("user_age_group", "unknown")
        # age_index_map = {
        #     "10대": 1,
        #     "20대": 2,
        #     "30대": 3,
        #     "40대": 4,
        #     "50대+": 5,
        # }
        # age_index = age_index_map.get(prev_age, 0)
        # age_group = st.selectbox("연령대", age_options, index=age_index)
        age_group = "10~20대"
        st.caption(f"적용 프로필: {age_group}")

        col_bank, col_acc = st.columns([1, 2])
        with col_bank:
            bank = st.selectbox("수취 은행", bank_options)
        with col_acc:
            account_raw = st.text_input("수취 계좌번호 (- 없이 숫자만)", placeholder="숫자만 입력해주세요")

        amount = st.number_input("이체 금액 (원)", min_value=1000, step=1000, value=100_000)
        col1, col2 = st.columns(2)
        with col1:
            is_new = st.checkbox("처음 이체하는 계좌")
        with col2:
            is_blacklisted = st.checkbox("⚠️ 의심 계좌 (테스트용)")

        submitted = st.form_submit_button("이체 확인 →", use_container_width=True, type="primary")

    if submitted:
        st.session_state.user_age_group = age_group
        _reset_voice_state()

        if not account_raw:
            st.error("계좌번호를 입력해주세요.")
            return

        # 계좌번호 검증 및 포맷 변환
        if bank == "기타(직접입력)":
            # 기타 은행은 검증 없이 그대로 사용
            account = account_raw.strip()
            is_valid = len(''.join(filter(str.isdigit, account))) >= 8
            if not is_valid:
                st.error("❌ 계좌번호는 최소 8자리 이상이어야 합니다.")
                return
        else:
            account, is_valid = validate_and_format_account(bank, account_raw)
            if not is_valid:
                expected_len = BANKS[bank]["len"]
                st.error(f"❌ {bank} 계좌번호는 {expected_len}자리 숫자여야 합니다.")
                return

        hour = datetime.now().hour
        state.set_transfer_data(
            account=account,
            amount=amount,
            hour=hour,
            is_new=is_new,
            is_blacklisted=is_blacklisted,
        )

        # ── 로컬 CDD 위험도 계산 (서버 불필요) ────────────────────────────────
        request_payload = {
            "account_number": account,
            "amount": int(amount),
            "hour": hour,
            "is_new_account": is_new,
            "is_blacklisted": is_blacklisted,
            "repeat_attempt_count": 0,
        }

        with st.spinner("위험도를 분석하는 중..."):
            try:
                data = _fetch_risk_from_backend(request_payload)
            except Exception:
                data = _local_risk_score(int(amount), hour, is_new, is_blacklisted)
                st.caption("서버 연결 이슈로 로컬 위험도 계산으로 대체했습니다.")

        score = data["risk_score"]
        level = data["risk_level"]
        reasons = data["reason"]

        st.session_state.risk_score = score
        st.session_state.risk_level = level
        st.session_state.require_voice_after_identity = level in {"high", "medium"}
        st.session_state.voice_gate_passed = not st.session_state.require_voice_after_identity
        st.session_state.voice_gate_status = "required" if st.session_state.require_voice_after_identity else "not_required"
        st.session_state.additional_auth_source = None

        if reasons:
            reason_str = ", ".join(reasons)
            st.caption(f"📋 위험 요인: {reason_str}")

        if st.session_state.require_voice_after_identity:
            st.warning(
                f"⚠️ 위험 점수: {score}점 — 안면 인증 후 음성(LLM) 검증까지 완료해야 송금됩니다."
            )
            state.go_to("face")
        else:
            st.success(f"✅ 위험 점수: {score}점 — 안면 인증 완료 시 바로 송금됩니다.")
            state.go_to("face")
