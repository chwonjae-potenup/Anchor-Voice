"""
CDD-based transfer risk scorer.
"""

from dataclasses import dataclass


@dataclass
class ScoringResult:
    score: int  # 0~100
    risk_level: str  # "low" | "medium" | "high"
    decision_level: str  # "safe" | "caution" | "risk"
    reasons: list[str]
    ai_intervention_required: bool
    trigger_reasons: list[str]


WEIGHTS = {
    "blacklisted_account": 70,
    "new_account": 20,
    "high_amount": 15,  # >= 1,000,000
    "primary_high_amount": 20,  # >= 10,000,000
    "night_time": 10,  # 22:00~06:00
    "repeat_attempt": 20,  # repeat >= 2
    "recent_call": 20,
    "unusual_pattern": 15,
}

HIGH_RISK_THRESHOLD = 70
CAUTION_RISK_THRESHOLD = 35
LOW_RISK_THRESHOLD = 30

HIGH_AMOUNT_LIMIT = 1_000_000
PRIMARY_AI_AMOUNT_LIMIT = 10_000_000
NIGHT_START = 22
NIGHT_END = 6

DEFAULT_USUAL_AMOUNT = 300_000
DEFAULT_USUAL_HOUR_START = 9
DEFAULT_USUAL_HOUR_END = 21
SECONDARY_TRIGGER_MIN_COUNT = 1


def calculate_risk_score(account_info: dict, transaction_info: dict) -> int:
    score = 0

    if account_info.get("is_blacklisted", False):
        score += WEIGHTS["blacklisted_account"]

    if account_info.get("is_new_account", False):
        score += WEIGHTS["new_account"]

    amount = int(transaction_info.get("amount", 0) or 0)
    if amount >= HIGH_AMOUNT_LIMIT:
        score += WEIGHTS["high_amount"]
    if amount >= PRIMARY_AI_AMOUNT_LIMIT:
        score += WEIGHTS["primary_high_amount"]

    hour = int(transaction_info.get("hour", 12) or 12)
    if hour >= NIGHT_START or hour < NIGHT_END:
        score += WEIGHTS["night_time"]

    repeat = int(transaction_info.get("repeat_attempt_count", 0) or 0)
    if repeat >= 2:
        score += WEIGHTS["repeat_attempt"]

    if bool(transaction_info.get("recent_call_after", False)):
        score += WEIGHTS["recent_call"]

    if _is_unusual_pattern(transaction_info):
        score += WEIGHTS["unusual_pattern"]

    return min(score, 100)


def evaluate_risk(account_info: dict, transaction_info: dict) -> ScoringResult:
    score = calculate_risk_score(account_info, transaction_info)
    reasons = _get_reasons(account_info, transaction_info)
    ai_intervention_required, trigger_reasons = _detect_ai_intervention_triggers(
        account_info,
        transaction_info,
    )

    if score >= HIGH_RISK_THRESHOLD:
        risk_level = "high"
        decision_level = "risk"
    elif score >= CAUTION_RISK_THRESHOLD:
        risk_level = "medium"
        decision_level = "caution"
    elif score < LOW_RISK_THRESHOLD:
        risk_level = "low"
        decision_level = "safe"
    else:
        risk_level = "medium"
        decision_level = "caution"

    if decision_level == "risk" and not ai_intervention_required:
        ai_intervention_required = True
        trigger_reasons = [*trigger_reasons, "고위험 점수 구간"]

    return ScoringResult(
        score=score,
        risk_level=risk_level,
        decision_level=decision_level,
        reasons=reasons,
        ai_intervention_required=ai_intervention_required,
        trigger_reasons=trigger_reasons,
    )


def _get_reasons(account_info: dict, transaction_info: dict) -> list[str]:
    reasons: list[str] = []

    if account_info.get("is_blacklisted", False):
        reasons.append("블랙리스트 수취 계좌")
    if account_info.get("is_new_account", False):
        reasons.append("처음 이체하는 신규 계좌")

    amount = int(transaction_info.get("amount", 0) or 0)
    if amount >= HIGH_AMOUNT_LIMIT:
        reasons.append(f"고액 이체 ({amount:,}원)")
    if amount >= PRIMARY_AI_AMOUNT_LIMIT:
        reasons.append(f"1차 트리거 고액 송금 ({amount:,}원)")

    hour = int(transaction_info.get("hour", 12) or 12)
    if hour >= NIGHT_START or hour < NIGHT_END:
        reasons.append(f"야간 거래 ({hour}시)")

    repeat = int(transaction_info.get("repeat_attempt_count", 0) or 0)
    if repeat >= 2:
        reasons.append(f"반복 이체 시도 ({repeat}회)")

    if bool(transaction_info.get("recent_call_after", False)):
        reasons.append("최근 통화 직후 송금")

    if _is_unusual_pattern(transaction_info):
        reasons.append("평소 패턴과 다른 시간대/금액")

    return reasons


def _is_unusual_pattern(transaction_info: dict) -> bool:
    amount = int(transaction_info.get("amount", 0) or 0)
    hour = int(transaction_info.get("hour", 12) or 12)

    usual_amount = int(transaction_info.get("usual_amount", DEFAULT_USUAL_AMOUNT) or DEFAULT_USUAL_AMOUNT)
    usual_hour_start = int(
        transaction_info.get("usual_hour_start", DEFAULT_USUAL_HOUR_START) or DEFAULT_USUAL_HOUR_START
    )
    usual_hour_end = int(
        transaction_info.get("usual_hour_end", DEFAULT_USUAL_HOUR_END) or DEFAULT_USUAL_HOUR_END
    )

    amount_outlier = amount >= max(HIGH_AMOUNT_LIMIT, usual_amount * 3)
    if usual_hour_start <= usual_hour_end:
        time_outlier = hour < usual_hour_start or hour > usual_hour_end
    else:
        time_outlier = not (hour >= usual_hour_start or hour <= usual_hour_end)

    return bool(amount_outlier or time_outlier)


def _detect_ai_intervention_triggers(account_info: dict, transaction_info: dict) -> tuple[bool, list[str]]:
    amount = int(transaction_info.get("amount", 0) or 0)
    repeat = int(transaction_info.get("repeat_attempt_count", 0) or 0)
    primary_trigger = amount >= PRIMARY_AI_AMOUNT_LIMIT

    secondary_reasons: list[str] = []
    if account_info.get("is_new_account", False):
        secondary_reasons.append("처음 보내는 계좌")
    if bool(transaction_info.get("recent_call_after", False)):
        secondary_reasons.append("최근 통화 직후 송금")
    if _is_unusual_pattern(transaction_info):
        secondary_reasons.append("평소 패턴과 다른 시간대/금액")
    if repeat >= 2:
        secondary_reasons.append("짧은 시간 내 반복 이체 시도")

    trigger_reasons: list[str] = []
    if primary_trigger:
        trigger_reasons.append("1차 트리거: 고액 송금")
    trigger_reasons.extend(secondary_reasons)

    ai_required = primary_trigger or len(secondary_reasons) >= SECONDARY_TRIGGER_MIN_COUNT
    return ai_required, trigger_reasons

