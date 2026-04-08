"""
backend/stealth_sos.py  — Backend Agent
스텔스 SOS: 이체 실제 차단 + 위장 UI 신호 전송 + 백그라운드 로그
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def trigger_stealth_sos(transfer_info: dict, phishing_evidence: dict) -> dict:
    """
    피싱 탐지 시 비밀 개입 메커니즘

    동작:
    1. 이체 실제 차단 (백그라운드)
    2. 프론트에 '이체 완료' 위장 UI 신호 반환
    3. 경고 로그 기록 (추후 신고 연동 지점)

    Returns:
        {"ui_mode": "stealth_complete", "blocked": True, "fake_amount": int, "fake_account": str}
    """

    # Step 1: 이체 차단 (실제 이체 시스템 연동 지점 — 현재는 로그로 대체)
    await _block_transfer(transfer_info)

    # Step 2: 위험 증거 로그
    _log_phishing_incident(transfer_info, phishing_evidence)

    # Step 3: 위장 UI 신호 반환
    return {
        "ui_mode": "stealth_complete",
        "blocked": True,
        "fake_amount": transfer_info.get("amount", 0),
        "fake_account": transfer_info.get("account_number", "***-***-****"),
    }


async def _block_transfer(transfer_info: dict) -> None:
    """이체 차단 로직 (실제 뱅킹 API 연동 지점)"""
    logger.warning(
        f"[STEALTH SOS] 이체 차단 실행 | "
        f"계좌: {transfer_info.get('account_number')} | "
        f"금액: {transfer_info.get('amount', 0):,}원 | "
        f"시각: {datetime.now().isoformat()}"
    )
    # TODO: 실제 은행 API 연동 시 여기에 차단 요청 삽입


def _log_phishing_incident(transfer_info: dict, phishing_evidence: dict) -> None:
    """피싱 증거 로그 기록"""
    logger.critical(
        f"[PHISHING DETECTED] "
        f"유형: {phishing_evidence.get('phishing_type')} | "
        f"신뢰도: {phishing_evidence.get('confidence', 0):.0%} | "
        f"트리거 질문: {phishing_evidence.get('triggered_questions')} | "
        f"차단 금액: {transfer_info.get('amount', 0):,}원"
    )
