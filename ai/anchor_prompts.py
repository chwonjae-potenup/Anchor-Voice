"""
ai/anchor_prompts.py  — LLM Agent
앵커 질문 5종 + 유형별 피싱 판별 기준 + Gemini 시스템 프롬프트

근거: workflow.md §Phase 2 STT 분석 결과 기반 설계
- 대출사기형: Q②(긴급성) + Q④(은행 차단) + Q⑤(선입금) 중 2개 이상 → 피싱 의심
- 수사기관사칭형: Q①(기관 지시) + Q③(비밀 강요) + Q④(은행 차단) 중 2개 이상 → 피싱 의심
- 어느 유형이든 3개 이상 → 즉시 위험 신호
"""

# ── 5가지 앵커 질문 ───────────────────────────────────────────────────────────
ANCHOR_QUESTIONS: list[dict] = [
    {
        "id": 1,
        "text": "혹시 경찰, 검찰, 금감원 같은 공공기관에서 직접 이체나 현금 전달을 지시했나요?",
        "short": "공공기관 이체 지시",
        "target": "agency_fraud",   # 수사기관사칭형에 핵심
    },
    {
        "id": 2,
        "text": "지금 당장 보내지 않으면 법적 처벌이나 대출 취소 같은 큰 불이익이 생긴다고 했나요?",
        "short": "긴급성 압박",
        "target": "both",           # 양 유형 공통
    },
    {
        "id": 3,
        "text": "이 거래 사실을 가족이나 은행 직원에게 절대 말하지 말라는 당부를 받으셨나요?",
        "short": "비밀 강요",
        "target": "both",           # 양 유형 공통
    },
    {
        "id": 4,
        "text": "은행 창구에서 직원이 이유를 물으면 다른 이유를 대라고 미리 알려줬나요?",
        "short": "은행 창구 차단",
        "target": "both",           # 양 유형 공통
    },
    {
        "id": 5,
        "text": "대출을 받거나 문제를 해결하기 위해 먼저 돈을 보내야 한다는 말을 들으셨나요?",
        "short": "선입금 요구",
        "target": "loan_fraud",     # 대출사기형에 핵심
    },
]

# ── LLM 시스템 프롬프트 ────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
당신은 보이스피싱 탐지 전문 AI 상담원입니다.
고객이 이체를 요청할 때 피싱 여부를 파악하기 위해 5가지 앵커 질문을 순서대로 물어보세요.

[판별 기준]
- 대출사기형 탐지: Q2(긴급성) + Q4(은행 차단) + Q5(선입금) 중 2개 이상 '예' → 피싱 의심
- 수사기관사칭형 탐지: Q1(기관 지시) + Q3(비밀 강요) + Q4(은행 차단) 중 2개 이상 '예' → 피싱 의심
- 어느 유형이든 3개 이상 '예' → 즉시 위험 신호 (최고위험)

[질문 어조 원칙]
- 중립적이고 안심시키는 어조 유지 - 고객을 의심하는 것이 아니라 안전을 확인하는 것임을 전달
- "혹시 ~한 상황인가요?" 형식으로 질문
- 피해자가 이미 압박받고 있음을 고려 — 짧고 명확하게, 판단력 회복을 돕는 방향으로

[응답 형식]
대화 로그를 분석한 후 반드시 다음 JSON 형식으로 반환하세요:
{
  "is_phishing": bool,
  "confidence": float (0.0~1.0),
  "phishing_type": "loan_fraud" | "agency_fraud" | "mixed" | "normal",
  "triggered_questions": [int, ...]
}
"""

# ── 판별 함수 ─────────────────────────────────────────────────────────────────
def get_question_by_id(question_id: int) -> dict | None:
    """질문 ID로 앵커 질문 반환"""
    for q in ANCHOR_QUESTIONS:
        if q["id"] == question_id:
            return q
    return None


def rule_based_detect(answers: dict[int, bool]) -> dict:
    """
    LLM 없이 규칙 기반으로 피싱 여부를 1차 판별 (fallback용)

    Args:
        answers: {question_id: bool} — 예: {1: True, 2: False, 3: True, 4: True, 5: False}

    Returns:
        {"is_phishing": bool, "phishing_type": str, "triggered_questions": list}
    """
    q1 = answers.get(1, False)
    q2 = answers.get(2, False)
    q3 = answers.get(3, False)
    q4 = answers.get(4, False)
    q5 = answers.get(5, False)

    yes_count = sum([q1, q2, q3, q4, q5])
    triggered = [i for i, v in answers.items() if v]

    # 수사기관사칭형 패턴
    agency_score = sum([q1, q3, q4])
    # 대출사기형 패턴
    loan_score = sum([q2, q4, q5])

    if yes_count >= 3:
        phishing_type = "mixed" if agency_score >= 2 and loan_score >= 2 else (
            "agency_fraud" if agency_score > loan_score else "loan_fraud"
        )
        return {"is_phishing": True, "phishing_type": phishing_type,
                "confidence": min(0.6 + yes_count * 0.1, 1.0),
                "triggered_questions": triggered}
    elif agency_score >= 2:
        return {"is_phishing": True, "phishing_type": "agency_fraud",
                "confidence": 0.75, "triggered_questions": triggered}
    elif loan_score >= 2:
        return {"is_phishing": True, "phishing_type": "loan_fraud",
                "confidence": 0.75, "triggered_questions": triggered}
    else:
        return {"is_phishing": False, "phishing_type": "normal",
                "confidence": 0.9, "triggered_questions": []}
