"""
ai/llm_engine.py  — LLM Agent (수정)
실제 발화 텍스트를 분석하는 방식 — 버튼 클릭 bool 방식 제거
Gemini → GPT → 규칙 기반 3중 fallback
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Optional

from ai.anchor_prompts import SYSTEM_PROMPT
from ai.teammate_llm_adapter import (
    TEAMMATE_INITIAL_OPENING,
    analyze_with_teammate_llm,
    suggest_next_question_with_teammate_llm,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_VOICE_QUESTIONS = 5
FIRST_QUESTION_INTENT = "transfer_reason"
FIRST_QUESTION_TEXT = os.getenv(
    "VOICE_FIRST_QUESTION_TEXT",
    TEAMMATE_INITIAL_OPENING,
)

# 질문 의도(intent)별 템플릿
INTENT_QUESTION_BANK = {
    "transfer_reason": FIRST_QUESTION_TEXT,
    "agency_directive": "상대가 경찰·검찰·금감원 등 공공기관 직원이라고 하면서 자금 이동을 지시했나요?",
    "agency_case_detail": "사건번호, 담당자 실명, 대표번호를 직접 조회해서 다시 확인해보셨나요?",
    "forged_document": "검찰 공문·영장·수사서류 이미지를 메신저로 받아 신뢰하게 되었나요?",
    "family_impersonation": "가족·지인이라고 하며 급하게 돈을 보내 달라는 요청을 받았나요?",
    "messenger_impersonation": "전화 대신 카카오톡/문자로 계좌를 바꿔 알려주며 송금을 재촉했나요?",
    "loan_offer_origin": "저금리 대환이나 정부지원 대출을 이유로 먼저 특정 금액 입금을 요구받았나요?",
    "upfront_fee": "인지세·보증금·전산처리비처럼 선입금이 필요하다고 들으셨나요?",
    "bank_deception": "은행 직원이 물어보면 다른 이유로 말하라고 안내받으셨나요?",
    "secrecy_isolation": "가족이나 지인, 은행에는 절대 알리지 말라고 했나요?",
    "motel_isolation": "모텔·원룸 등 특정 장소로 이동해 혼자 있으라고 지시받았나요?",
    "remote_control": "앱 설치나 원격제어, 특정 링크 접속을 요구받았나요?",
    "cash_or_safe_account": "현금 전달이나 안전계좌 이체처럼 평소와 다른 방식의 거래를 지시받았나요?",
    "mule_recruitment": "고액 알바·채권 회수 업무라며 현금 수거/전달을 제안받았나요?",
    "urgency_threat": "지금 바로 하지 않으면 처벌·계좌동결·대출취소가 된다고 압박했나요?",
    "relationship_check": "돈을 보내려는 상대가 평소 실제로 거래하던 기관·담당자인지 본인이 직접 검증하셨나요?",
}


AGE_GROUP_ALIASES = {
    "10~20대": "20대",
    "10-20": "20대",
    "youth": "20대",
    "10to20": "20대",
    "10대": "10대",
    "10s": "10대",
    "teen": "10대",
    "teens": "10대",
    "20대": "20대",
    "20s": "20대",
    "30대": "30대",
    "30s": "30대",
    "40대": "40대",
    "40s": "40대",
    "50대": "50대+",
    "50대+": "50대+",
    "50+": "50대+",
    "50plus": "50대+",
    "60대": "50대+",
    "70대": "50대+",
    "unknown": "unknown",
}

AGE_TYPE_SCORE_MULTIPLIER = {
    "10대": {"agency_fraud": 1.20, "loan_fraud": 1.00, "family_fraud": 1.00, "mixed": 1.05},
    "20대": {"agency_fraud": 1.20, "loan_fraud": 1.00, "family_fraud": 1.00, "mixed": 1.05},
    "30대": {"agency_fraud": 1.00, "loan_fraud": 1.15, "family_fraud": 1.00, "mixed": 1.03},
    "40대": {"agency_fraud": 1.00, "loan_fraud": 1.15, "family_fraud": 1.00, "mixed": 1.03},
    "50대+": {"agency_fraud": 1.00, "loan_fraud": 1.00, "family_fraud": 1.25, "mixed": 1.05},
    "unknown": {"agency_fraud": 1.00, "loan_fraud": 1.00, "family_fraud": 1.00, "mixed": 1.00},
}

AGE_FIRST_INTENTS = {
    "10대": [
        "agency_case_detail",
        "forged_document",
        "motel_isolation",
        "secrecy_isolation",
        "remote_control",
    ],
    "20대": [
        "agency_case_detail",
        "forged_document",
        "motel_isolation",
        "secrecy_isolation",
        "remote_control",
    ],
    "30대": [
        "loan_offer_origin",
        "upfront_fee",
        "bank_deception",
        "urgency_threat",
    ],
    "40대": [
        "loan_offer_origin",
        "upfront_fee",
        "bank_deception",
        "urgency_threat",
    ],
    "50대+": [
        "family_impersonation",
        "messenger_impersonation",
        "relationship_check",
        "urgency_threat",
    ],
    "unknown": [],
}

ANSWER_YES_HINTS = [
    "네",
    "예",
    "맞",
    "그렇",
    "응",
    "있어요",
    "있습니다",
    "받았",
    "지시",
    "요구",
    "하라고",
    "보내라고",
    "압박",
]

ANSWER_NO_HINTS = [
    "아니요",
    "아니",
    "없어요",
    "없습니다",
    "없었",
    "받지 않았",
    "요구받지",
    "안 했",
    "안했",
]

ANSWER_UNKNOWN_HINTS = [
    "모르겠",
    "모르겠어요",
    "기억 안",
    "잘 모르",
    "애매",
]

REVERSED_RISK_INTENTS = {"agency_case_detail", "relationship_check"}

INTENT_RISK_WEIGHTS = {
    "agency_directive": 1.35,
    "agency_case_detail": 1.15,  # "확인 안 함"이 위험
    "forged_document": 1.25,
    "family_impersonation": 1.20,
    "messenger_impersonation": 1.20,
    "loan_offer_origin": 1.10,
    "upfront_fee": 1.30,
    "bank_deception": 1.20,
    "secrecy_isolation": 1.35,
    "motel_isolation": 1.45,
    "remote_control": 1.35,
    "cash_or_safe_account": 1.40,
    "mule_recruitment": 1.60,
    "urgency_threat": 1.15,
    "relationship_check": 1.25,  # "직접 검증 안 함"이 위험
}

INTENT_TO_PHISHING_TYPE = {
    "agency_directive": "agency_fraud",
    "agency_case_detail": "agency_fraud",
    "forged_document": "agency_fraud",
    "loan_offer_origin": "loan_fraud",
    "upfront_fee": "loan_fraud",
    "family_impersonation": "family_fraud",
    "messenger_impersonation": "family_fraud",
    "motel_isolation": "agency_fraud",
    "secrecy_isolation": "agency_fraud",
    "remote_control": "agency_fraud",
    "cash_or_safe_account": "agency_fraud",
    "mule_recruitment": "mixed",
    "bank_deception": "mixed",
    "urgency_threat": "mixed",
    "relationship_check": "mixed",
}

FOLLOWUP_BY_SUSPICIOUS_INTENT = {
    "agency_directive": ["agency_case_detail", "forged_document", "cash_or_safe_account", "secrecy_isolation"],
    "agency_case_detail": ["forged_document", "cash_or_safe_account", "secrecy_isolation"],
    "forged_document": ["agency_case_detail", "cash_or_safe_account", "secrecy_isolation"],
    "loan_offer_origin": ["upfront_fee", "bank_deception", "urgency_threat"],
    "upfront_fee": ["loan_offer_origin", "bank_deception", "urgency_threat"],
    "family_impersonation": ["messenger_impersonation", "relationship_check", "urgency_threat"],
    "messenger_impersonation": ["relationship_check", "urgency_threat", "bank_deception"],
    "secrecy_isolation": ["motel_isolation", "remote_control", "cash_or_safe_account"],
    "motel_isolation": ["remote_control", "secrecy_isolation", "cash_or_safe_account"],
    "remote_control": ["secrecy_isolation", "cash_or_safe_account", "bank_deception"],
    "cash_or_safe_account": ["agency_case_detail", "secrecy_isolation", "bank_deception"],
    "bank_deception": ["urgency_threat", "cash_or_safe_account", "relationship_check"],
    "urgency_threat": ["bank_deception", "cash_or_safe_account", "relationship_check"],
    "mule_recruitment": ["relationship_check", "bank_deception", "urgency_threat"],
    "relationship_check": ["urgency_threat", "bank_deception", "cash_or_safe_account"],
}

TRANSFER_REASON_FOLLOWUP_RULES: list[tuple[str, list[str], str]] = [
    (
        "mule_recruitment",
        ["고액 알바", "수거", "인출책", "현금 전달", "전달 알바", "통장 빌려", "체크카드 맡겨"],
        "초기 사유 답변에서 고액 알바·현금 전달 단서가 보여 관련 위험을 우선 확인합니다.",
    ),
    (
        "agency_case_detail",
        ["사건번호", "수사", "검찰", "경찰", "금감원", "공공기관", "범죄 연루", "명의도용", "안전계좌"],
        "초기 사유 답변에 수사기관/사건번호 단서가 있어 사건 정보 검증 여부를 먼저 확인합니다.",
    ),
    (
        "forged_document",
        ["공문", "영장", "수사서류", "압수수색", "메신저로 보낸 문서"],
        "초기 사유 답변에 공문·영장 전달 단서가 있어 문서 위조/사칭 여부를 확인합니다.",
    ),
    (
        "loan_offer_origin",
        ["대출", "저금리", "대환", "보증금", "선입금", "인지세", "한도", "전산비"],
        "초기 사유 답변에 대출·선입금 단서가 있어 대출사기 패턴을 우선 확인합니다.",
    ),
    (
        "messenger_impersonation",
        ["카톡", "카카오톡", "문자", "메신저", "번호 바뀌", "연락처 바뀌"],
        "초기 사유 답변에 메신저/문자 기반 요청 단서가 있어 계정사칭 패턴을 확인합니다.",
    ),
    (
        "family_impersonation",
        ["가족", "지인", "아들", "딸", "엄마", "아빠", "친구가 급하"],
        "초기 사유 답변에 가족·지인 사칭 단서가 있어 관련 위험을 확인합니다.",
    ),
    (
        "remote_control",
        ["앱 설치", "원격", "링크", "apk", "보안 앱", "화면공유"],
        "초기 사유 답변에 앱 설치/원격제어 단서가 있어 기기 통제 위험을 확인합니다.",
    ),
    (
        "cash_or_safe_account",
        ["현금", "무통장", "안전계좌", "전달해", "직접 가져", "인출"],
        "초기 사유 답변에 현금 전달/안전계좌 단서가 있어 비정상 이체 지시 여부를 확인합니다.",
    ),
]

CRITICAL_ADMISSION_INTENTS = {
    "agency_directive",
    "cash_or_safe_account",
    "remote_control",
    "motel_isolation",
    "mule_recruitment",
}


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("Invalid float env %s=%s; using default %.3f", name, raw, default)
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


VOICE_BLOCK_CONFIDENCE = _env_float("VOICE_BLOCK_CONFIDENCE", 0.82)
VOICE_ADDITIONAL_AUTH_CONFIDENCE = _env_float("VOICE_ADDITIONAL_AUTH_CONFIDENCE", 0.55)
VOICE_INTENT_BLOCK_SCORE = _env_float("VOICE_INTENT_BLOCK_SCORE", 3.0)
VOICE_INTENT_ADDITIONAL_SCORE = _env_float("VOICE_INTENT_ADDITIONAL_SCORE", 1.5)
VOICE_USE_TEAMMATE_LLM = _env_bool("VOICE_USE_TEAMMATE_LLM", True)
VOICE_USE_TEAMMATE_QUESTION_ROUTER = _env_bool("VOICE_USE_TEAMMATE_QUESTION_ROUTER", True)


def normalize_age_group(age_group: str | None) -> str:
    raw = (age_group or "").strip().lower().replace(" ", "")
    if not raw:
        return "unknown"
    return AGE_GROUP_ALIASES.get(raw, AGE_GROUP_ALIASES.get(age_group or "", "unknown"))


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip().lower()


def _resolve_intent(item: dict) -> str:
    raw_intent = _normalize_text(item.get("question_intent", ""))
    if raw_intent:
        return raw_intent
    return _infer_intent_from_question_text(str(item.get("question", "")))


def _classify_answer_polarity(answer_text: str) -> str:
    """
    Returns one of: "yes" | "no" | "unknown"
    """
    text = _normalize_text(answer_text)
    if not text:
        return "unknown"

    if any(kw in text for kw in ANSWER_UNKNOWN_HINTS):
        return "unknown"

    yes_hits = sum(1 for kw in ANSWER_YES_HINTS if kw in text)
    no_hits = sum(1 for kw in ANSWER_NO_HINTS if kw in text)

    # Regex backup: starts with a direct yes/no answer.
    if re.match(r"^(네|예|맞아요|맞습니다|그렇)", text):
        yes_hits += 1
    if re.match(r"^(아니|없어요|없습니다)", text):
        no_hits += 1

    if yes_hits == 0 and no_hits == 0:
        return "unknown"
    if yes_hits > no_hits:
        return "yes"
    if no_hits > yes_hits:
        return "no"
    if text.startswith("아니"):
        return "no"
    return "yes"


def _is_suspicious_answer(intent: str, answer_text: str) -> bool | None:
    polarity = _classify_answer_polarity(answer_text)
    if polarity == "unknown":
        return None
    if intent in REVERSED_RISK_INTENTS:
        return polarity == "no"
    return polarity == "yes"


def _intent_signal_from_log(conversation_log: list[dict]) -> dict:
    type_scores = {
        "agency_fraud": 0.0,
        "loan_fraud": 0.0,
        "family_fraud": 0.0,
        "mixed": 0.0,
    }
    clues: list[str] = []
    triggered_questions: list[int] = []
    risk_score = 0.0

    for item in conversation_log:
        intent = _resolve_intent(item)
        if not intent:
            continue
        suspicious = _is_suspicious_answer(intent, str(item.get("answer_text", "")))
        if suspicious is not True:
            continue

        qid = int(item.get("question_id", 0) or 0)
        weight = float(INTENT_RISK_WEIGHTS.get(intent, 0.8))
        risk_score += weight
        if qid > 0:
            triggered_questions.append(qid)

        phishing_type = INTENT_TO_PHISHING_TYPE.get(intent, "mixed")
        type_scores[phishing_type] += weight

        clue_text = INTENT_QUESTION_BANK.get(intent, intent)
        clues.append(f"Q{qid}:{clue_text}" if qid > 0 else clue_text)

    top_type = "normal"
    top_score = 0.0
    if type_scores:
        top_type = max(type_scores, key=type_scores.get)
        top_score = type_scores[top_type]
        if top_score <= 0:
            top_type = "normal"

    return {
        "risk_score": risk_score,
        "type_scores": type_scores,
        "top_type": top_type,
        "top_score": top_score,
        "triggered_questions": sorted(set(triggered_questions)),
        "clues": clues,
    }


def _pick_followup_intent_from_latest(conversation_log: list[dict], asked_intents: set[str]) -> tuple[str, str]:
    if not conversation_log:
        return "", ""

    latest = conversation_log[-1]
    latest_intent = _resolve_intent(latest)
    if not latest_intent:
        return "", ""

    if latest_intent == FIRST_QUESTION_INTENT:
        selected, reason = _pick_followup_from_transfer_reason(
            str(latest.get("answer_text", "")),
            asked_intents,
        )
        if selected:
            return selected, reason
        return "", ""

    suspicious = _is_suspicious_answer(latest_intent, str(latest.get("answer_text", "")))
    if suspicious is not True:
        return "", ""

    answer_text = _normalize_text(latest.get("answer_text", ""))

    # If the latest answer contains explicit high-signal keywords, prioritize that branch.
    answer_driven_pool: list[str] = []
    if any(kw in answer_text for kw in ["모텔", "원룸", "공기계"]):
        answer_driven_pool.extend(["motel_isolation", "remote_control", "secrecy_isolation"])
    if any(kw in answer_text for kw in ["앱 설치", "원격", "링크", "apk"]):
        answer_driven_pool.extend(["remote_control", "secrecy_isolation", "cash_or_safe_account"])
    if any(kw in answer_text for kw in ["안전계좌", "현금", "전달", "인출"]):
        answer_driven_pool.extend(["cash_or_safe_account", "agency_case_detail", "secrecy_isolation"])
    if any(kw in answer_text for kw in ["공문", "영장", "사건번호", "수사서류"]):
        answer_driven_pool.extend(["forged_document", "agency_case_detail"])

    followup_pool = answer_driven_pool + FOLLOWUP_BY_SUSPICIOUS_INTENT.get(latest_intent, [])
    selected = next((intent for intent in followup_pool if intent not in asked_intents), "")
    if not selected:
        return "", ""

    qid = int(latest.get("question_id", 0) or 0)
    reason = f"직전 답변(Q{qid})에서 의심 신호가 감지되어 추적 질문을 우선합니다."
    return selected, reason


def _pick_followup_from_transfer_reason(answer_text: str, asked_intents: set[str]) -> tuple[str, str]:
    """
    Route the second question by the user's free-form transfer reason.
    This keeps Q1 broad and avoids jumping into narrow agency probes without clues.
    """
    text = _normalize_text(answer_text)

    for intent, keywords, reason in TRANSFER_REASON_FOLLOWUP_RULES:
        if intent in asked_intents:
            continue
        if any(kw in text for kw in keywords):
            return intent, reason

    fallback_pool = ["relationship_check", "urgency_threat", "bank_deception"]
    selected = next((intent for intent in fallback_pool if intent not in asked_intents), "")
    if not selected:
        return "", ""

    return selected, "초기 사유 답변에서 특정 피싱 유형 단서가 약해 기본 검증 질문부터 진행합니다."


def analyze_conversation(conversation_log: list[dict], age_group: str = "unknown") -> dict:
    """
    실제 음성 대화 로그를 분석하여 피싱 여부 판별

    Args:
        conversation_log: [
            {
                "question_id": int,
                "question": str,    # 앵커 질문 텍스트
                "answer_text": str  # 사용자가 실제로 말한 텍스트 (STT 결과)
            },
            ...
        ]
        age_group: 연령대 문자열 (예: 20대, 50대+)

    Returns:
        {
            "is_phishing": bool,
            "confidence": float,
            "phishing_type": str,
            "summary": str,          # LLM이 생성한 판단 근거
            "triggered_questions": [int, ...]
        }
    """
    normalized_age = normalize_age_group(age_group)

    if not conversation_log:
        return _normal_result()

    # 0차: teammate LLM (voice_project sample/genai.py 정책 우선)
    if VOICE_USE_TEAMMATE_LLM:
        teammate_result = analyze_with_teammate_llm(conversation_log)
        if teammate_result:
            return _apply_age_weight_to_result(teammate_result, normalized_age)

    # 1차: Gemini
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        result = _analyze_with_gemini(conversation_log, gemini_key)
        if result:
            return _apply_age_weight_to_result(result, normalized_age)

    # 2차: GPT
    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        result = _analyze_with_gpt(conversation_log, openai_key)
        if result:
            return _apply_age_weight_to_result(result, normalized_age)

    # 3차: 키워드 기반 fallback
    logger.warning("LLM API 불가 — 키워드 기반 판별 fallback")
    return _keyword_based_detect(conversation_log, age_group=normalized_age)


def _build_conversation_text(conversation_log: list[dict]) -> str:
    """대화 로그를 LLM에 전달할 자연어 형식으로 변환"""
    lines = []
    for item in conversation_log:
        q_text = item.get("question", f"질문 {item['question_id']}")
        a_text = item.get("answer_text", "").strip() or "(무응답)"
        lines.append(f"[질문 {item['question_id']}] {q_text}\n[답변] {a_text}")
    return "\n\n".join(lines)


def _build_prompt(conversation_text: str) -> str:
    return f"""
다음은 이체 전 고객과의 안전 확인 대화입니다. 고객의 실제 발화를 분석하세요.

{conversation_text}

위 대화를 분석하여 보이스피싱 피해 가능성을 판단하세요.

판단 기준:
- 대출사기형: "지금 바로", "안 보내면 취소", "인지세/보증금 선입금", "은행에 말하지 마" 등
- 수사기관사칭형: "검사/경찰/금감원", "안전계좌", "수사 중", "절대 비밀" 등
- 가족·지인사칭형: "가족이라며 급송금", "카톡/문자로만 계좌 변경", "휴대폰 고장 핑계" 등
- 명확한 피싱 언급이 없어도 압박감/긴급함/비밀 강요 뉘앙스가 있으면 의심

반드시 아래 JSON 형식으로만 응답하세요:
{{
  "is_phishing": true/false,
  "confidence": 0.0~1.0,
  "phishing_type": "loan_fraud" | "agency_fraud" | "family_fraud" | "mixed" | "normal",
  "summary": "판단 근거를 1~2문장으로 설명",
  "triggered_questions": [의심 답변이 있었던 질문 번호 목록]
}}
"""


def _parse_llm_response(raw: str) -> Optional[dict]:
    try:
        clean = raw.strip()
        # 마크다운 코드블록 제거
        for prefix in ["```json", "```"]:
            if clean.startswith(prefix):
                clean = clean[len(prefix):]
        clean = clean.removesuffix("```").strip()
        data = json.loads(clean)
        required = {"is_phishing", "confidence", "phishing_type"}
        if required.issubset(data.keys()):
            data.setdefault("summary", "")
            data.setdefault("triggered_questions", [])
            return data
    except Exception as e:
        logger.warning(f"LLM 응답 파싱 실패: {e}")
    return None


def _analyze_with_gemini(conversation_log: list[dict], api_key: str) -> Optional[dict]:
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-1.5-flash")

        prompt = SYSTEM_PROMPT + "\n\n" + _build_prompt(_build_conversation_text(conversation_log))
        response = model.generate_content(prompt)
        result = _parse_llm_response(response.text)
        if result:
            logger.info(f"Gemini 판별: {result['phishing_type']} ({result['confidence']:.0%})")
        return result
    except Exception as e:
        logger.error(f"Gemini 오류: {e}")
        return None


def _analyze_with_gpt(conversation_log: list[dict], api_key: str) -> Optional[dict]:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        prompt = _build_prompt(_build_conversation_text(conversation_log))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        result = _parse_llm_response(response.choices[0].message.content)
        if result:
            logger.info(f"GPT 판별: {result['phishing_type']} ({result['confidence']:.0%})")
        return result
    except Exception as e:
        logger.error(f"GPT 오류: {e}")
        return None


# 키워드 기반 fallback ───────────────────────────────────────────────────────

BASE_LOAN_FRAUD_KEYWORDS = [
    "선입금", "인지세", "보증금", "지금 바로", "지금 당장", "취소", "대출", "빨리",
    "선불", "먼저 보내", "수수료",
]
BASE_AGENCY_FRAUD_KEYWORDS = [
    "검사", "검찰", "경찰", "금감원", "금융감독원", "안전계좌", "수사", "영장",
    "비밀", "말하지 마", "말하면 안", "발부",
]
PRESSURE_KEYWORDS = ["급해", "빨리", "당장", "지금", "무조건", "절대"]
SELF_ISOLATION_KEYWORDS = [
    "주변에 알리지", "절대 알리지", "비밀 유지", "발설하지", "혼자", "연락하지 마",
    "부모님에게 말하지", "통화 끊지", "모텔", "공기계", "와이파이 끄", "데이터 끄",
]
FORGED_DOC_KEYWORDS = [
    "공문", "영장", "수사서류", "검찰청 문서", "가짜 사이트", "사건번호",
]
MULE_RECRUITMENT_KEYWORDS = [
    "고액 알바", "채권 회수", "현금 수거", "수거책", "인출책", "심부름 알바",
    "현금 전달", "입금받아 전달", "통장 빌려", "체크카드 맡겨", "수당",
]
FAMILY_IMPERSONATION_KEYWORDS = [
    "엄마", "아빠", "아들", "딸", "누나", "형", "동생", "삼촌", "이모", "지인", "친구",
    "가족", "지인이라", "급하게 돈", "합의금", "병원비", "휴대폰 고장",
]
MESSENGER_IMPERSONATION_KEYWORDS = [
    "카톡", "카카오톡", "문자", "메신저", "프로필", "번호 바뀌", "계좌 바꿔",
    "통화 어려워", "문자로만", "톡으로만", "계좌 알려줄게",
]


def _merge_keywords(base: list[str], extra: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for kw in base + extra:
        k = (kw or "").strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        merged.append(k)
    return merged


def _load_external_keywords() -> tuple[list[str], list[str]]:
    """
    Optional keyword boost from weakly-labeled FSS dataset artifacts.

    Default path:
      stt_output/fss_seed_keywords.json
    Override:
      FSS_KEYWORDS_PATH env
    """
    path = Path(os.getenv("FSS_KEYWORDS_PATH", "stt_output/fss_seed_keywords.json"))
    if not path.exists():
        return [], []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        loan = [str(x).strip() for x in data.get("loan_fraud_keywords", []) if str(x).strip()]
        agency = [str(x).strip() for x in data.get("agency_fraud_keywords", []) if str(x).strip()]
        logger.info(
            "Loaded external keywords: loan=%d agency=%d (%s)",
            len(loan),
            len(agency),
            path,
        )
        return loan, agency
    except Exception as e:
        logger.warning("External keyword load failed (%s): %s", path, e)
        return [], []


_EXTERNAL_LOAN_KEYWORDS, _EXTERNAL_AGENCY_KEYWORDS = _load_external_keywords()
LOAN_FRAUD_KEYWORDS = _merge_keywords(BASE_LOAN_FRAUD_KEYWORDS, _EXTERNAL_LOAN_KEYWORDS)
AGENCY_FRAUD_KEYWORDS = _merge_keywords(BASE_AGENCY_FRAUD_KEYWORDS, _EXTERNAL_AGENCY_KEYWORDS)


def _keyword_based_detect(conversation_log: list[dict], age_group: str = "unknown") -> dict:
    normalized_age = normalize_age_group(age_group)
    all_answers = " ".join(item.get("answer_text", "") for item in conversation_log).lower()

    loan_hits = [kw for kw in LOAN_FRAUD_KEYWORDS if kw in all_answers]
    agency_hits = [kw for kw in AGENCY_FRAUD_KEYWORDS if kw in all_answers]
    pressure_hits = [kw for kw in PRESSURE_KEYWORDS if kw in all_answers]
    isolation_hits = [kw for kw in SELF_ISOLATION_KEYWORDS if kw in all_answers]
    forged_doc_hits = [kw for kw in FORGED_DOC_KEYWORDS if kw in all_answers]
    mule_hits = [kw for kw in MULE_RECRUITMENT_KEYWORDS if kw in all_answers]
    family_hits = [kw for kw in FAMILY_IMPERSONATION_KEYWORDS if kw in all_answers]
    messenger_hits = [kw for kw in MESSENGER_IMPERSONATION_KEYWORDS if kw in all_answers]

    keyword_triggered = [
        item["question_id"]
        for item in conversation_log
        if any(
            kw in item.get("answer_text", "").lower()
            for kw in (
                LOAN_FRAUD_KEYWORDS
                + AGENCY_FRAUD_KEYWORDS
                + MULE_RECRUITMENT_KEYWORDS
                + FAMILY_IMPERSONATION_KEYWORDS
                + MESSENGER_IMPERSONATION_KEYWORDS
            )
        )
    ]
    intent_signal = _intent_signal_from_log(conversation_log)
    triggered = sorted(set(keyword_triggered + intent_signal["triggered_questions"]))

    if mule_hits:
        result = {
            "is_phishing": True,
            "confidence": 0.82,
            "phishing_type": "mixed",
            "summary": f"고액알바/현금수거 가담 유도 신호 감지: {', '.join(mule_hits[:3])}",
            "triggered_questions": triggered,
        }
        return _apply_age_weight_to_result(result, normalized_age)

    keyword_score_map = {
        "agency_fraud": (
            len(agency_hits)
            + 0.7 * len(isolation_hits)
            + 0.7 * len(forged_doc_hits)
            + 0.2 * len(pressure_hits)
        ),
        "loan_fraud": len(loan_hits) + 0.35 * len(pressure_hits),
        "family_fraud": len(family_hits) + 0.9 * len(messenger_hits) + 0.3 * len(pressure_hits),
    }
    weighted_keyword_scores = _apply_age_weight_to_type_scores(keyword_score_map, normalized_age)
    combined_scores = {
        "agency_fraud": weighted_keyword_scores["agency_fraud"] + intent_signal["type_scores"]["agency_fraud"],
        "loan_fraud": weighted_keyword_scores["loan_fraud"] + intent_signal["type_scores"]["loan_fraud"],
        "family_fraud": weighted_keyword_scores["family_fraud"] + intent_signal["type_scores"]["family_fraud"],
    }
    top_type = max(combined_scores, key=combined_scores.get)
    top_score = combined_scores[top_type]

    if top_score >= 1.0:
        if top_type == "agency_fraud":
            clues = agency_hits[:2] + isolation_hits[:1] + forged_doc_hits[:1]
            summary = f"기관사칭 관련 신호 감지: {', '.join(clues[:3])}"
            base_conf = 0.70
        elif top_type == "loan_fraud":
            clues = loan_hits[:3] or pressure_hits[:2]
            summary = f"대출사기 관련 신호 감지: {', '.join(clues[:3])}"
            base_conf = 0.68
        else:
            clues = family_hits[:2] + messenger_hits[:2]
            summary = f"가족·지인 사칭 신호 감지: {', '.join(clues[:3])}"
            base_conf = 0.69

        if intent_signal["top_type"] == top_type and intent_signal["clues"]:
            summary = f"{summary} / 답변 기반 추적 신호: {', '.join(intent_signal['clues'][:2])}"
        elif not clues and intent_signal["clues"]:
            summary = f"답변 기반 의심 신호 감지: {', '.join(intent_signal['clues'][:2])}"

        confidence = min(0.95, base_conf + 0.06 * max(0.0, top_score - 1.0))
        result = {
            "is_phishing": True,
            "confidence": confidence,
            "phishing_type": top_type,
            "summary": summary,
            "triggered_questions": triggered,
        }
        return _apply_age_weight_to_result(result, normalized_age)

    if len(pressure_hits) >= 2 or intent_signal["risk_score"] >= 1.2:
        summary = f"긴급성 압박 키워드 반복 감지: {', '.join(pressure_hits[:3])}" if pressure_hits else "답변 기반 의심 신호 감지"
        if intent_signal["clues"]:
            summary = f"{summary} ({', '.join(intent_signal['clues'][:2])})"
        result = {
            "is_phishing": True,
            "confidence": min(0.78, 0.55 + 0.07 * max(0.0, intent_signal["risk_score"] - 1.0)),
            "phishing_type": "mixed",
            "summary": summary,
            "triggered_questions": triggered,
        }
        return _apply_age_weight_to_result(result, normalized_age)

    return _normal_result()


def _apply_age_weight_to_type_scores(score_map: dict[str, float], age_group: str) -> dict[str, float]:
    weights = AGE_TYPE_SCORE_MULTIPLIER.get(age_group, AGE_TYPE_SCORE_MULTIPLIER["unknown"])
    weighted = {}
    for phishing_type, score in score_map.items():
        weighted[phishing_type] = score * weights.get(phishing_type, 1.0)
    return weighted


def _apply_age_weight_to_result(result: dict, age_group: str) -> dict:
    if not result.get("is_phishing"):
        return result

    phishing_type = result.get("phishing_type", "mixed")
    weights = AGE_TYPE_SCORE_MULTIPLIER.get(age_group, AGE_TYPE_SCORE_MULTIPLIER["unknown"])
    multiplier = weights.get(phishing_type, 1.0)
    if multiplier <= 1.0:
        return result

    boosted = min(0.98, float(result.get("confidence", 0.0)) * multiplier)
    if boosted <= float(result.get("confidence", 0.0)):
        return result

    age_hint = {
        "10대": "10대는 범죄연루 사칭 대응 가중 반영",
        "20대": "20대는 범죄연루 사칭 대응 가중 반영",
        "30대": "30대는 저리대출 사칭 대응 가중 반영",
        "40대": "40대는 저리대출 사칭 대응 가중 반영",
        "50대+": "50대+는 가족·지인 사칭 대응 가중 반영",
    }.get(age_group, "")

    result["confidence"] = boosted
    if age_hint:
        summary = (result.get("summary") or "").strip()
        result["summary"] = f"{summary} ({age_hint})".strip()
    return result


def decide_voice_gate(result: dict, conversation_log: list[dict], final_step: bool) -> dict:
    """
    Convert classifier output into a real transfer gate decision.

    recommended_action:
      - block: phishing high confidence -> stealth/SOS path
      - proceed_with_caution: suspicious but not fully confirmed -> caution banner + re-check guidance
      - additional_auth: client/server fail-closed fallback path
      - proceed: final step passed
      - pending: continue asking questions
    """
    normalized = {
        "is_phishing": bool(result.get("is_phishing", False)),
        "confidence": float(result.get("confidence", 0.0)),
        "phishing_type": str(result.get("phishing_type", "normal") or "normal"),
        "summary": str(result.get("summary", "") or "").strip(),
        "triggered_questions": list(result.get("triggered_questions", [])),
    }
    normalized["confidence"] = min(1.0, max(0.0, normalized["confidence"]))

    intent_signal = _intent_signal_from_log(conversation_log)
    intent_score = float(intent_signal["risk_score"])
    inferred_type = intent_signal["top_type"]
    critical_admission = any(
        (_resolve_intent(item) in CRITICAL_ADMISSION_INTENTS)
        and (_is_suspicious_answer(_resolve_intent(item), str(item.get("answer_text", ""))) is True)
        for item in conversation_log
    )
    merged_triggered = sorted(
        {
            int(q)
            for q in [*normalized["triggered_questions"], *intent_signal["triggered_questions"]]
            if isinstance(q, int) or str(q).isdigit()
        }
    )
    normalized["triggered_questions"] = merged_triggered

    # Lift confidence floor if intent-answer signals are clearly suspicious.
    intent_conf_floor = min(0.95, 0.42 + 0.14 * intent_score)
    if intent_score >= VOICE_INTENT_ADDITIONAL_SCORE:
        normalized["confidence"] = max(normalized["confidence"], intent_conf_floor)

    high_signal = (
        (normalized["is_phishing"] and normalized["confidence"] >= VOICE_BLOCK_CONFIDENCE)
        or intent_score >= VOICE_INTENT_BLOCK_SCORE
        or critical_admission
    )
    medium_signal = (
        high_signal
        or (normalized["is_phishing"] and normalized["confidence"] >= VOICE_ADDITIONAL_AUTH_CONFIDENCE)
        or intent_score >= VOICE_INTENT_ADDITIONAL_SCORE
    )

    if high_signal:
        recommended_action = "block"
        risk_tier = "high"
        normalized["is_phishing"] = True
        if normalized["phishing_type"] in {"normal", "pending", ""} and inferred_type != "normal":
            normalized["phishing_type"] = inferred_type
    elif final_step and medium_signal:
        recommended_action = "proceed_with_caution"
        risk_tier = "medium"
        if normalized["phishing_type"] == "pending":
            normalized["phishing_type"] = "mixed"
    elif final_step:
        recommended_action = "proceed"
        risk_tier = "low"
    else:
        recommended_action = "pending"
        risk_tier = "medium" if medium_signal else "low"

    if not normalized["summary"]:
        if high_signal:
            normalized["summary"] = "답변에서 피싱 고위험 신호가 확인되어 거래를 차단합니다."
        elif medium_signal:
            normalized["summary"] = "답변에서 의심 신호가 있어 가족/상담센터 재확인 후 진행을 권고합니다."
        else:
            normalized["summary"] = "현재까지는 명확한 피싱 신호가 낮습니다."

    # Keep short clue append only when signal is meaningful.
    if medium_signal and intent_signal["clues"]:
        clues = ", ".join(intent_signal["clues"][:2])
        if clues and clues not in normalized["summary"]:
            normalized["summary"] = f"{normalized['summary']} (근거: {clues})"

    if critical_admission and "핵심 위험 답변" not in normalized["summary"]:
        normalized["summary"] = f"핵심 위험 답변이 확인되어 즉시 차단합니다. {normalized['summary']}".strip()

    normalized["recommended_action"] = recommended_action
    normalized["risk_tier"] = risk_tier
    return normalized


def generate_next_question(
    conversation_log: list[dict],
    max_questions: int = DEFAULT_MAX_VOICE_QUESTIONS,
    age_group: str = "unknown",
) -> dict:
    """
    Generate an adaptive next question from conversation history.

    Policy:
    - Q1 is always a broad transfer-reason question.
    - Q2~Qn are intent-based follow-up probes selected by risk profile.
    """
    safe_max = max(3, min(int(max_questions), 10))
    normalized_age = normalize_age_group(age_group)
    next_id = len(conversation_log) + 1

    if next_id > safe_max:
        return {
            "done": True,
            "question_id": next_id,
            "question_text": "",
            "question_intent": "",
            "reason": "최대 질문 수 도달",
            "max_questions": safe_max,
        }

    if next_id == 1:
        return {
            "done": False,
            "question_id": 1,
            "question_text": FIRST_QUESTION_TEXT,
            "question_intent": FIRST_QUESTION_INTENT,
            "reason": "첫 질문은 송금 사유를 넓게 파악한 뒤, 답변 단서로 2번 질문부터 분기합니다.",
            "max_questions": safe_max,
        }

    if VOICE_USE_TEAMMATE_LLM and VOICE_USE_TEAMMATE_QUESTION_ROUTER:
        teammate_question = suggest_next_question_with_teammate_llm(conversation_log)
        if teammate_question:
            return {
                "done": False,
                "question_id": next_id,
                "question_text": teammate_question,
                "question_intent": "",
                "reason": "동료 LLM 라우터(sample/genai.py)에서 현재 맥락 기준 다음 질문을 생성했습니다.",
                "max_questions": safe_max,
            }

    asked_intents = _collect_asked_intents(conversation_log)
    selected_intent, followup_reason = _pick_followup_intent_from_latest(conversation_log, asked_intents)
    profile = _build_risk_profile(conversation_log)

    if not selected_intent:
        intent_order = _select_intent_priority(profile, normalized_age)
        selected_intent = next(
            (intent for intent in intent_order if intent not in asked_intents),
            "relationship_check",
        )

    question_text = INTENT_QUESTION_BANK.get(
        selected_intent,
        "상대의 요구가 평소 금융기관의 정상 절차와 다르다는 느낌을 받으셨나요?",
    )

    return {
        "done": False,
        "question_id": next_id,
        "question_text": question_text,
        "question_intent": selected_intent,
        "reason": followup_reason or _explain_intent_choice(selected_intent, profile, normalized_age),
        "max_questions": safe_max,
    }


def _collect_asked_intents(conversation_log: list[dict]) -> set[str]:
    intents = set()
    for item in conversation_log:
        intent = _normalize_text(item.get("question_intent", ""))
        if intent:
            intents.add(intent)
            continue

        # backward compatibility: infer intent from historical question text.
        inferred = _infer_intent_from_question_text(str(item.get("question", "")))
        if inferred:
            intents.add(inferred)
    return intents


def _infer_intent_from_question_text(question_text: str) -> str:
    text = (question_text or "").lower()
    if any(k in text for k in ["어떤 사유", "송금하시려는지", "송금하려는 이유", "상대가 뭐라고 설명"]):
        return FIRST_QUESTION_INTENT
    if any(k in text for k in ["경찰", "검찰", "금감원", "공공기관"]):
        return "agency_directive"
    if any(k in text for k in ["공문", "영장", "수사서류", "메신저"]):
        return "forged_document"
    if any(k in text for k in ["가족", "지인", "돈을 보내", "급하게 돈"]):
        return "family_impersonation"
    if any(k in text for k in ["카톡", "카카오톡", "문자", "계좌를 바꿔"]):
        return "messenger_impersonation"
    if any(k in text for k in ["선입금", "인지세", "보증금"]):
        return "upfront_fee"
    if any(k in text for k in ["고액 알바", "채권 회수", "현금 수거", "인출"]):
        return "mule_recruitment"
    if any(k in text for k in ["말하지", "비밀", "가족", "지인"]):
        return "secrecy_isolation"
    if any(k in text for k in ["모텔", "공기계", "혼자"]):
        return "motel_isolation"
    if any(k in text for k in ["은행", "다른 이유", "창구"]):
        return "bank_deception"
    if any(k in text for k in ["앱", "원격", "링크"]):
        return "remote_control"
    return ""


def _build_risk_profile(conversation_log: list[dict]) -> dict:
    answer_text = " ".join(str(item.get("answer_text", "")) for item in conversation_log).lower()
    question_text = " ".join(str(item.get("question", "")) for item in conversation_log).lower()
    merged_text = f"{question_text} {answer_text}"

    def has_any(words: list[str]) -> bool:
        return any(word in merged_text for word in words)

    agency_hits = sum(1 for kw in AGENCY_FRAUD_KEYWORDS if kw in answer_text)
    loan_hits = sum(1 for kw in LOAN_FRAUD_KEYWORDS if kw in answer_text)
    pressure_hits = sum(1 for kw in PRESSURE_KEYWORDS if kw in answer_text)

    secrecy = has_any(["비밀", "말하지", "발설", "혼자", "통화 끊지", "통화끊지"])
    bank_deception = has_any(["은행", "창구", "다른 이유", "거짓말"])
    upfront_fee = has_any(["선입금", "인지세", "보증금", "수수료", "먼저 보내"])
    remote_control = has_any(["앱 설치", "원격", "링크", "apk", "보안 프로그램"])
    cash_or_safe = has_any(["현금 전달", "안전계좌", "현금", "인출", "전달"])
    urgency_threat = has_any(["지금 당장", "처벌", "계좌동결", "소환", "불이익", "취소"])
    forged_document = has_any(["공문", "영장", "수사서류", "사건번호"])
    motel_isolation = has_any(["모텔", "공기계", "원룸", "혼자 있으"])
    mule_recruitment = has_any(
        ["고액 알바", "채권 회수", "현금 수거", "수거책", "인출책", "통장 빌려", "체크카드 맡겨"]
    )
    family_impersonation = has_any(
        ["가족", "지인", "엄마", "아빠", "아들", "딸", "친구", "병원비", "합의금", "휴대폰 고장"]
    )
    messenger_impersonation = has_any(
        ["카톡", "카카오톡", "문자", "메신저", "프로필", "번호 바뀌", "계좌 바꿔", "통화가 안돼"]
    )

    agency_score = agency_hits + (2 if secrecy else 0) + (2 if cash_or_safe else 0) + (1 if bank_deception else 0)
    loan_score = loan_hits + (2 if upfront_fee else 0) + (1 if bank_deception else 0) + (1 if urgency_threat else 0)
    family_score = (
        (3 if family_impersonation else 0)
        + (2 if messenger_impersonation else 0)
        + (1 if urgency_threat else 0)
    )
    youth_victim_score = (
        agency_score
        + (2 if forged_document else 0)
        + (2 if motel_isolation else 0)
        + (2 if remote_control else 0)
    )
    accomplice_score = (3 if mule_recruitment else 0) + (1 if cash_or_safe else 0)

    return {
        "agency_hits": agency_hits,
        "loan_hits": loan_hits,
        "pressure_hits": pressure_hits,
        "secrecy": secrecy,
        "bank_deception": bank_deception,
        "upfront_fee": upfront_fee,
        "remote_control": remote_control,
        "cash_or_safe": cash_or_safe,
        "urgency_threat": urgency_threat,
        "forged_document": forged_document,
        "motel_isolation": motel_isolation,
        "mule_recruitment": mule_recruitment,
        "family_impersonation": family_impersonation,
        "messenger_impersonation": messenger_impersonation,
        "agency_score": agency_score,
        "loan_score": loan_score,
        "family_score": family_score,
        "youth_victim_score": youth_victim_score,
        "accomplice_score": accomplice_score,
    }


def _select_intent_priority(profile: dict, age_group: str) -> list[str]:
    has_signal = _has_material_signal(profile)
    if not has_signal:
        branch = [
            "relationship_check",
            "urgency_threat",
            "bank_deception",
            "loan_offer_origin",
            "family_impersonation",
            "agency_directive",
            "remote_control",
            "cash_or_safe_account",
        ]
    elif profile["mule_recruitment"] or profile["accomplice_score"] >= 3:
        branch = [
            "mule_recruitment",
            "relationship_check",
            "bank_deception",
            "urgency_threat",
            "secrecy_isolation",
        ]
    elif profile["family_impersonation"] or profile["messenger_impersonation"] or profile["family_score"] >= 4:
        branch = [
            "family_impersonation",
            "messenger_impersonation",
            "relationship_check",
            "urgency_threat",
            "bank_deception",
        ]
    elif profile["motel_isolation"] or (
        profile["youth_victim_score"] >= 6
        and (profile["secrecy"] or profile["remote_control"] or profile["forged_document"])
    ):
        branch = [
            "motel_isolation",
            "remote_control",
            "secrecy_isolation",
            "forged_document",
            "agency_case_detail",
            "cash_or_safe_account",
            "relationship_check",
        ]
    else:
        common_intents = [
            "urgency_threat",
            "secrecy_isolation",
            "bank_deception",
            "remote_control",
            "cash_or_safe_account",
            "relationship_check",
        ]

        if profile["agency_score"] >= profile["loan_score"] + 1:
            branch = [
                "agency_case_detail",
                "forged_document",
                "cash_or_safe_account",
                "secrecy_isolation",
                "bank_deception",
                "remote_control",
                "urgency_threat",
                "relationship_check",
            ]
        elif profile["loan_score"] >= profile["agency_score"] + 1:
            branch = [
                "loan_offer_origin",
                "upfront_fee",
                "bank_deception",
                "urgency_threat",
                "secrecy_isolation",
                "remote_control",
                "relationship_check",
            ]
        else:
            branch = [
                "cash_or_safe_account",
                "upfront_fee",
                "agency_case_detail",
                "forged_document",
                "family_impersonation",
                "loan_offer_origin",
            ] + common_intents

    age_seed = AGE_FIRST_INTENTS.get(age_group, []) if has_signal else []
    branch = age_seed + branch

    deduped: list[str] = []
    seen: set[str] = set()
    for intent in branch:
        if intent in seen:
            continue
        seen.add(intent)
        deduped.append(intent)
    return deduped


def _has_material_signal(profile: dict) -> bool:
    return any(
        [
            profile["agency_hits"] > 0,
            profile["loan_hits"] > 0,
            profile["pressure_hits"] > 0,
            profile["secrecy"],
            profile["bank_deception"],
            profile["upfront_fee"],
            profile["remote_control"],
            profile["cash_or_safe"],
            profile["urgency_threat"],
            profile["forged_document"],
            profile["motel_isolation"],
            profile["mule_recruitment"],
            profile["family_impersonation"],
            profile["messenger_impersonation"],
            profile["agency_score"] >= 2,
            profile["loan_score"] >= 2,
            profile["family_score"] >= 2,
            profile["youth_victim_score"] >= 3,
            profile["accomplice_score"] >= 2,
        ]
    )


def _explain_intent_choice(intent: str, profile: dict, age_group: str) -> str:
    if intent == "agency_case_detail":
        return "수사기관 사칭 징후를 확인하기 위해 사건 정보 검증 여부를 질문"
    if intent == "forged_document":
        return "가짜 공문/영장 위조 전송 패턴 여부 점검"
    if intent == "family_impersonation":
        return "가족·지인 사칭 송금 요청 여부 점검"
    if intent == "messenger_impersonation":
        return "메신저 계정탈취/문자 사칭 송금 패턴 점검"
    if intent == "loan_offer_origin":
        return "대출사기 징후를 확인하기 위해 대출 유도 맥락을 점검"
    if intent == "upfront_fee":
        return "선입금 요구 여부는 대출사기의 핵심 신호"
    if intent == "mule_recruitment":
        return "고액알바·현금수거형 가담 유도 위험 점검"
    if intent == "motel_isolation":
        return "셀프 감금형(격리/공기계) 고립 유도 여부 점검"
    if intent == "bank_deception":
        return "은행 응대 스크립트 강요는 피싱 고위험 신호"
    if intent == "secrecy_isolation":
        return "비밀 유지 강요는 수사기관/대출 사기 공통 패턴"
    if intent == "remote_control":
        return "원격제어·악성앱 설치 유도 여부 점검"
    if intent == "cash_or_safe_account":
        return "안전계좌·현금 전달 유도 여부 점검"
    if intent == "urgency_threat":
        return "긴급·협박성 압박 여부 점검"
    if intent == "relationship_check":
        return "최종적으로 상대방 실체 검증 여부 확인"
    return (
        f"현재 위험 프로파일 기반 추적 질문 "
        f"(agency={profile.get('agency_score', 0)}, loan={profile.get('loan_score', 0)}, "
        f"family={profile.get('family_score', 0)}, age={age_group})"
    )


def _normal_result() -> dict:
    return {
        "is_phishing": False, "confidence": 0.9,
        "phishing_type": "normal", "summary": "피싱 징후 없음",
        "triggered_questions": [],
    }
