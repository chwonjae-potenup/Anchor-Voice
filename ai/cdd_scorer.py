"""
ai/cdd_scorer.py  — Vision Agent
CDD (Customer Due Diligence) 기반 이체 위험도 스코어링 엔진
"""
from dataclasses import dataclass


@dataclass
class ScoringResult:
    score: int          # 0~100
    risk_level: str     # "low" | "high"
    reasons: list[str]


# 위험 가중치 정의
WEIGHTS = {
    "blacklisted_account": 70,  # 블랙리스트 계좌: 단독으로도 즉시 고위험
    "new_account": 20,          # 처음 이체하는 계좌
    "high_amount": 15,          # 100만 원 이상 고액
    "night_time": 10,           # 22:00~06:00 야간 거래
    "repeat_attempt": 20,       # 짧은 시간 내 반복 시도
}


HIGH_RISK_THRESHOLD = 70
LOW_RISK_THRESHOLD = 30
HIGH_AMOUNT_LIMIT = 1_000_000  # 100만 원
NIGHT_START = 22
NIGHT_END = 6


def calculate_risk_score(account_info: dict, transaction_info: dict) -> int:
    """
    CDD 기반 위험도 점수 산출 (0~100)

    Args:
        account_info: {
            "is_blacklisted": bool,
            "is_new_account": bool,
        }
        transaction_info: {
            "amount": int,
            "hour": int (0~23),
            "repeat_attempt_count": int,
        }

    Returns:
        int: 0~100 위험 점수 (≥70 = 고위험, <30 = 저위험)
    """
    score = 0
    reasons = []

    if account_info.get("is_blacklisted", False):
        score += WEIGHTS["blacklisted_account"]
        reasons.append("블랙리스트 수취 계좌")

    if account_info.get("is_new_account", False):
        score += WEIGHTS["new_account"]
        reasons.append("처음 이체하는 신규 계좌")

    amount = transaction_info.get("amount", 0)
    if amount >= HIGH_AMOUNT_LIMIT:
        score += WEIGHTS["high_amount"]
        reasons.append(f"고액 이체 ({amount:,}원)")

    hour = transaction_info.get("hour", 12)
    if hour >= NIGHT_START or hour < NIGHT_END:
        score += WEIGHTS["night_time"]
        reasons.append(f"야간 거래 ({hour}시)")

    repeat = transaction_info.get("repeat_attempt_count", 0)
    if repeat >= 2:
        score += WEIGHTS["repeat_attempt"]
        reasons.append(f"반복 이체 시도 ({repeat}회)")

    return min(score, 100)


def evaluate_risk(account_info: dict, transaction_info: dict) -> ScoringResult:
    """위험도 점수와 등급을 함께 반환"""
    score = calculate_risk_score(account_info, transaction_info)
    reasons = _get_reasons(account_info, transaction_info)

    if score >= HIGH_RISK_THRESHOLD:
        risk_level = "high"
    elif score < LOW_RISK_THRESHOLD:
        risk_level = "low"
    else:
        risk_level = "medium"

    return ScoringResult(score=score, risk_level=risk_level, reasons=reasons)


def _get_reasons(account_info: dict, transaction_info: dict) -> list[str]:
    reasons = []
    if account_info.get("is_blacklisted"):
        reasons.append("블랙리스트 수취 계좌")
    if account_info.get("is_new_account"):
        reasons.append("처음 이체하는 신규 계좌")
    amount = transaction_info.get("amount", 0)
    if amount >= HIGH_AMOUNT_LIMIT:
        reasons.append(f"고액 이체 ({amount:,}원)")
    hour = transaction_info.get("hour", 12)
    if hour >= NIGHT_START or hour < NIGHT_END:
        reasons.append(f"야간 거래 ({hour}시)")
    repeat = transaction_info.get("repeat_attempt_count", 0)
    if repeat >= 2:
        reasons.append(f"반복 이체 시도 ({repeat}회)")
    return reasons


if __name__ == "__main__":
    # 빠른 동작 확인
    result = evaluate_risk(
        {"is_blacklisted": True, "is_new_account": True},
        {"amount": 2_000_000, "hour": 2, "repeat_attempt_count": 3},
    )
    print(f"Score: {result.score}, Level: {result.risk_level}")
    print("Reasons:", result.reasons)
