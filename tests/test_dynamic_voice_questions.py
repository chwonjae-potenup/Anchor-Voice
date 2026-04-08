"""
tests/test_dynamic_voice_questions.py
동적 음성 질문 생성기 단위 테스트
"""

from ai.llm_engine import _keyword_based_detect, generate_next_question


def test_first_question_is_general_transfer_reason():
    result = generate_next_question([])
    assert result["done"] is False
    assert result["question_id"] == 1
    assert result["question_intent"] == "transfer_reason"
    assert "어떤 사유" in result["question_text"] or "송금하시려는지" in result["question_text"]


def test_transfer_reason_routes_to_agency_case_validation():
    log = [
        {
            "question_id": 1,
            "question": "어떤 사유로 송금하시려는지, 상대가 뭐라고 설명했는지 말씀해 주실 수 있을까요?",
            "question_intent": "transfer_reason",
            "answer_text": "범죄에 연루됐다면서 사건번호를 말하고 안전계좌로 옮기라고 했어요.",
        }
    ]
    result = generate_next_question(log, max_questions=5)
    assert result["done"] is False
    assert result["question_id"] == 2
    assert result["question_intent"] == "agency_case_detail"


def test_transfer_reason_without_clear_signal_starts_neutral_validation():
    log = [
        {
            "question_id": 1,
            "question": "어떤 사유로 송금하시려는지, 상대가 뭐라고 설명했는지 말씀해 주실 수 있을까요?",
            "question_intent": "transfer_reason",
            "answer_text": "친구한테 밥값 보내려고요.",
        }
    ]
    result = generate_next_question(log, max_questions=5)
    assert result["done"] is False
    assert result["question_id"] == 2
    assert result["question_intent"] == "relationship_check"


def test_followup_prefers_agency_probe_when_agency_signal_exists():
    log = [
        {
            "question_id": 1,
            "question": "혹시 경찰, 검찰, 금감원 같은 공공기관에서 직접 이체나 현금 전달을 지시했나요?",
            "question_intent": "agency_directive",
            "answer_text": "검찰 수사관이라고 하면서 안전계좌로 옮기라고 했어요.",
        }
    ]
    result = generate_next_question(log, max_questions=5)
    assert result["done"] is False
    assert result["question_id"] == 2
    assert result["question_intent"] in {
        "agency_case_detail",
        "cash_or_safe_account",
        "secrecy_isolation",
    }


def test_done_when_max_questions_reached():
    log = [
        {"question_id": 1, "question": "q1", "answer_text": "a1"},
        {"question_id": 2, "question": "q2", "answer_text": "a2"},
        {"question_id": 3, "question": "q3", "answer_text": "a3"},
    ]
    result = generate_next_question(log, max_questions=3)
    assert result["done"] is True


def test_youth_isolation_signal_prompts_motel_or_remote_questions():
    log = [
        {
            "question_id": 1,
            "question": "혹시 경찰, 검찰, 금감원 같은 공공기관에서 직접 이체나 현금 전달을 지시했나요?",
            "question_intent": "agency_directive",
            "answer_text": "네, 모텔 들어가서 공기계로만 연락하라고 했어요.",
        }
    ]
    result = generate_next_question(log, max_questions=5)
    assert result["done"] is False
    assert result["question_intent"] in {"motel_isolation", "remote_control", "secrecy_isolation"}


def test_age_seed_does_not_override_when_initial_signal_is_weak():
    log = [
        {
            "question_id": 1,
            "question": "어떤 사유로 송금하시려는지, 상대가 뭐라고 설명했는지 말씀해 주실 수 있을까요?",
            "question_intent": "transfer_reason",
            "answer_text": "잘 모르겠어요.",
        }
    ]
    result = generate_next_question(log, max_questions=5, age_group="50대+")
    assert result["done"] is False
    assert result["question_intent"] == "relationship_check"


def test_mule_recruitment_signal_prompts_mule_question():
    log = [
        {
            "question_id": 1,
            "question": "상대가 공공기관이라며 지시했나요?",
            "question_intent": "agency_directive",
            "answer_text": "고액 알바라며 현금 수거하고 전달하면 수당 준다고 했어요.",
        }
    ]
    result = generate_next_question(log, max_questions=5)
    assert result["done"] is False
    assert result["question_intent"] == "mule_recruitment"


def test_keyword_detect_flags_mule_pattern_as_phishing():
    log = [
        {
            "question_id": 1,
            "question": "질문",
            "answer_text": "고액 알바로 현금 수거해서 인출책 업무하라고 했어요.",
        }
    ]
    result = _keyword_based_detect(log)
    assert result["is_phishing"] is True
    assert result["phishing_type"] == "mixed"


def test_keyword_detect_flags_family_impersonation_for_50s():
    log = [
        {
            "question_id": 1,
            "question": "질문",
            "answer_text": "아들이라고 하면서 카톡으로 계좌 바꿔서 빨리 보내달라고 했어요.",
        }
    ]
    result = _keyword_based_detect(log, age_group="50대+")
    assert result["is_phishing"] is True
    assert result["phishing_type"] in {"family_fraud", "mixed"}
