"""
Adapter to run teammate LLM policy (voice_project/sample/genai.py) inside Anchor-Voice.

This module mirrors teammate's system instruction and output schema shape, then maps
the result into Anchor-Voice's internal phishing analysis contract.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

TEAMMATE_PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "teammate_system_instruction.txt"
TEAMMATE_INITIAL_OPENING = "잠시만! 입금 전에 하나 확인하려고 해. 지금 큰 금액을 입금하는데 어디에 입금하는 거야?"

TEAMMATE_TO_INTERNAL_TYPE = {
    "수사기관 사칭형-직접 기관 사칭": "agency_fraud",
    "수사기관 사칭형-4단계 릴레이": "agency_fraud",
    "금융기관 사칭형-저금리·대환·거래실적형": "loan_fraud",
    "금융기관 사칭형-악성앱·오픈뱅킹 편취형": "loan_fraud",
    "가족·지인 사칭형-메신저 피싱": "family_fraud",
    "스미싱-문자 링크·악성앱형": "mixed",
    "투자사기형-리딩방·가상자산·고수익형": "mixed",
    "로맨스 스캠형": "mixed",
    "영상유포 협박형": "mixed",
    "인출책 모집형": "mixed",
}

TEAMMATE_RISK_TO_TIER = {
    "낮음": "low",
    "주의": "medium",
    "높음": "medium",
    "매우 높음": "high",
    "확정에 준하는 고위험": "high",
}


def _load_teammate_instruction() -> str:
    try:
        return TEAMMATE_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except Exception as e:
        logger.warning("Failed to load teammate prompt: %s", e)
        return ""


TEAMMATE_SYSTEM_INSTRUCTION = _load_teammate_instruction()


def _clamp_score(value: object) -> int:
    try:
        return max(0, min(100, int(value)))
    except Exception:
        return 0


def _build_history_summary(conversation_log: list[dict]) -> str:
    if not conversation_log:
        return "(대화 이력 없음)"

    lines: list[str] = []
    for item in conversation_log[-10:]:
        qid = int(item.get("question_id", 0) or 0)
        question = str(item.get("question", "") or "").strip()
        answer = str(item.get("answer_text", "") or "").strip()
        q_label = f"Q{qid}" if qid > 0 else "Q?"
        if question:
            lines.append(f"- {q_label}: {question}")
        if answer:
            lines.append(f"  A: {answer}")
        else:
            lines.append("  A: (무응답)")
    return "\n".join(lines)


def _latest_user_message(conversation_log: list[dict]) -> str:
    for item in reversed(conversation_log):
        answer = str(item.get("answer_text", "") or "").strip()
        if answer:
            return answer
    return ""


def _build_teammate_user_prompt(conversation_log: list[dict]) -> str:
    return (
        "아래 플레이스홀더를 채워 teammate 규칙대로 JSON만 반환해.\n\n"
        f"CONVERSATION_HISTORY_SUMMARY:\n{_build_history_summary(conversation_log)}\n\n"
        f"LATEST_USER_MESSAGE:\n{_latest_user_message(conversation_log)}\n\n"
        "INITIAL_OPENING_ALREADY_SENT: true\n"
        f'INITIAL_OPENING_TEXT: "{TEAMMATE_INITIAL_OPENING}"\n\n'
        "주의: 출력은 반드시 JSON 객체 하나만 반환해."
    )


def _parse_json_text(raw: str) -> Optional[dict]:
    text = str(raw or "").strip()
    if not text:
        return None

    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except Exception:
                return None
    return None


def _call_teammate_with_gemini(conversation_log: list[dict], api_key: str) -> Optional[dict]:
    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model_name = os.getenv("TEAMMATE_LLM_GEMINI_MODEL", "gemini-1.5-flash")
        model = genai.GenerativeModel(model_name)
        prompt = f"{TEAMMATE_SYSTEM_INSTRUCTION}\n\n{_build_teammate_user_prompt(conversation_log)}"
        response = model.generate_content(prompt)
        parsed = _parse_json_text(getattr(response, "text", ""))
        if parsed:
            return parsed
    except Exception as e:
        logger.warning("Teammate Gemini call failed: %s", e)
    return None


def _call_teammate_with_openai(conversation_log: list[dict], api_key: str) -> Optional[dict]:
    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        model_name = os.getenv("TEAMMATE_LLM_OPENAI_MODEL", "gpt-4o-mini")
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": TEAMMATE_SYSTEM_INSTRUCTION},
                {"role": "user", "content": _build_teammate_user_prompt(conversation_log)},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        raw = response.choices[0].message.content if response.choices else ""
        parsed = _parse_json_text(raw)
        if parsed:
            return parsed
    except Exception as e:
        logger.warning("Teammate OpenAI call failed: %s", e)
    return None


def _call_teammate_raw(conversation_log: list[dict]) -> Optional[dict]:
    if not TEAMMATE_SYSTEM_INSTRUCTION:
        return None

    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        result = _call_teammate_with_gemini(conversation_log, gemini_key)
        if result:
            return result

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if openai_key:
        result = _call_teammate_with_openai(conversation_log, openai_key)
        if result:
            return result

    return None


def _summarize_evidence(data: dict) -> str:
    key_evidence = [str(x).strip() for x in data.get("key_evidence", []) if str(x).strip()]
    actions = [str(x).strip() for x in data.get("immediate_action", []) if str(x).strip()]
    system_message = str(data.get("system_message", "") or "").strip()

    chunks: list[str] = []
    if key_evidence:
        chunks.append("근거: " + "; ".join(key_evidence[:3]))
    if actions:
        chunks.append("권고: " + "; ".join(actions[:2]))
    if not chunks and system_message:
        chunks.append(system_message)
    return " ".join(chunks).strip() or "동료 LLM 분석 결과"


def _map_recommended_action(data: dict, risk_score: int) -> str:
    status = str(data.get("conversation_status", "in_progress") or "in_progress").strip().lower()
    reason = str(data.get("termination_reason", "") or "").strip().lower()

    if reason == "risk_detected" or risk_score >= 60:
        return "block"
    if status == "terminated" and reason == "safe_confirmed":
        if risk_score >= 45:
            return "additional_auth"
        if risk_score >= 25:
            return "proceed_with_caution"
        return "proceed"
    if risk_score >= 45:
        return "additional_auth"
    if risk_score >= 25:
        return "proceed_with_caution"
    return "pending" if status == "in_progress" else "proceed"


def normalize_teammate_output(raw_data: dict, conversation_log: list[dict]) -> dict:
    risk_score = _clamp_score(raw_data.get("risk_score", 0))
    risk_level = str(raw_data.get("risk_level", "낮음") or "낮음").strip()
    risk_tier = TEAMMATE_RISK_TO_TIER.get(risk_level, "medium")

    suspected_types = raw_data.get("suspected_types", [])
    top_type = ""
    if isinstance(suspected_types, list) and suspected_types:
        top_type = str(suspected_types[0].get("type", "") or "").strip()
    phishing_type = TEAMMATE_TO_INTERNAL_TYPE.get(top_type, "mixed" if top_type else "normal")

    recommended_action = _map_recommended_action(raw_data, risk_score)
    is_phishing = recommended_action in {"block", "additional_auth"} or risk_score >= 45
    if recommended_action in {"proceed", "pending"} and risk_score < 45:
        is_phishing = False

    triggered_questions = sorted(
        {
            int(item.get("question_id", 0) or 0)
            for item in conversation_log
            if int(item.get("question_id", 0) or 0) > 0
        }
    )

    return {
        "is_phishing": bool(is_phishing),
        "confidence": min(0.99, max(0.01, risk_score / 100.0)),
        "phishing_type": phishing_type,
        "summary": _summarize_evidence(raw_data),
        "triggered_questions": triggered_questions,
        "recommended_action": recommended_action,
        "risk_tier": risk_tier,
        "teammate_system_message": str(raw_data.get("system_message", "") or "").strip(),
        "teammate_conversation_status": str(raw_data.get("conversation_status", "in_progress") or "in_progress"),
        "teammate_termination_reason": str(raw_data.get("termination_reason", "") or ""),
    }


def analyze_with_teammate_llm(conversation_log: list[dict]) -> Optional[dict]:
    raw = _call_teammate_raw(conversation_log)
    if not raw:
        return None
    normalized = normalize_teammate_output(raw, conversation_log)
    logger.info(
        "Teammate LLM applied: action=%s risk=%s score=%.0f%%",
        normalized.get("recommended_action"),
        normalized.get("risk_tier"),
        float(normalized.get("confidence", 0.0)) * 100,
    )
    return normalized


def suggest_next_question_with_teammate_llm(conversation_log: list[dict]) -> Optional[str]:
    raw = _call_teammate_raw(conversation_log)
    if not raw:
        return None

    status = str(raw.get("conversation_status", "in_progress") or "in_progress").strip().lower()
    if status != "in_progress":
        return None

    text = str(raw.get("system_message", "") or "").strip()
    if not text:
        return None

    # teammate rule says system_message should contain one question while in_progress.
    # still guard against accidental non-question responses.
    if "?" not in text and "요?" not in text and "나요?" not in text:
        return None
    return text

