from ai.llm_engine import _keyword_based_detect, decide_voice_gate, generate_next_question


def test_yes_on_agency_anchor_is_blocked():
    log = [
        {
            "question_id": 1,
            "question": "혹시 경찰, 검찰, 금감원 같은 공공기관에서 직접 이체나 현금 전달을 지시했나요?",
            "question_intent": "agency_directive",
            "answer_text": "네",
        }
    ]

    raw = _keyword_based_detect(log)
    gate = decide_voice_gate(raw, log, final_step=True)

    assert raw["is_phishing"] is True
    assert gate["recommended_action"] == "block"
    assert gate["risk_tier"] == "high"


def test_high_intent_signal_blocks_even_before_last_question():
    log = [
        {
            "question_id": 1,
            "question": "기관에서 지시했나요?",
            "question_intent": "agency_directive",
            "answer_text": "네, 검찰 수사라고 하면서 안전계좌로 이체하라고 했어요.",
        },
        {
            "question_id": 2,
            "question": "가족에게 알리지 말라고 했나요?",
            "question_intent": "secrecy_isolation",
            "answer_text": "네, 부모님에게도 절대 말하지 말라고 했어요.",
        },
        {
            "question_id": 3,
            "question": "앱 설치나 원격제어를 요구했나요?",
            "question_intent": "remote_control",
            "answer_text": "네, 원격 앱도 깔라고 했어요.",
        },
    ]

    raw = _keyword_based_detect(log)
    gate = decide_voice_gate(raw, log, final_step=False)

    assert gate["recommended_action"] == "block"
    assert gate["risk_tier"] == "high"
    assert gate["is_phishing"] is True


def test_suspicious_answer_triggers_tail_followup_question():
    log = [
        {
            "question_id": 1,
            "question": "혹시 경찰, 검찰, 금감원 같은 공공기관에서 직접 이체나 현금 전달을 지시했나요?",
            "question_intent": "agency_directive",
            "answer_text": "네",
        }
    ]

    next_q = generate_next_question(log, max_questions=5)
    assert next_q["question_intent"] in {
        "agency_case_detail",
        "forged_document",
        "cash_or_safe_account",
        "secrecy_isolation",
    }
    assert "직전 답변" in next_q["reason"]
