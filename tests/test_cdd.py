"""
tests/test_cdd.py  — Tester Agent
CDD 위험도 스코어링 단위 테스트
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.cdd_scorer import calculate_risk_score, evaluate_risk


class TestCddScorer:

    def test_normal_transfer_low_risk(self):
        """정상 이체 → 저위험"""
        score = calculate_risk_score(
            account_info={"is_blacklisted": False, "is_new_account": False},
            transaction_info={"amount": 50_000, "hour": 14, "repeat_attempt_count": 0},
        )
        assert score < 30, f"정상 이체는 30점 미만이어야 함. 실제: {score}"

    def test_blacklisted_account_high_risk(self):
        """블랙리스트 계좌 → 즉시 고위험"""
        score = calculate_risk_score(
            account_info={"is_blacklisted": True, "is_new_account": False},
            transaction_info={"amount": 10_000, "hour": 12, "repeat_attempt_count": 0},
        )
        assert score >= 70, f"블랙리스트 계좌는 70점 이상이어야 함. 실제: {score}"

    def test_multiple_risk_factors_medium_to_high(self):
        """야간 + 고액 + 신규 계좌 + 반복 + 패턴이탈 → 고위험"""
        score = calculate_risk_score(
            account_info={"is_blacklisted": False, "is_new_account": True},
            transaction_info={"amount": 2_000_000, "hour": 2, "repeat_attempt_count": 3},
        )
        # 20(신규) + 15(고액) + 10(야간) + 20(반복) + 15(패턴이탈) = 80점
        assert score >= 80, f"복합 위험 요소는 80점 이상이어야 함. 실제: {score}"
        assert score == 80, f"정확한 합산 : 80점 기대. 실제: {score}"


    def test_max_score_clamp(self):
        """점수 최대값 100 초과 불가"""
        score = calculate_risk_score(
            account_info={"is_blacklisted": True, "is_new_account": True},
            transaction_info={"amount": 10_000_000, "hour": 3, "repeat_attempt_count": 10},
        )
        assert score <= 100, f"점수는 100을 초과할 수 없음. 실제: {score}"

    def test_evaluate_risk_returns_correct_level(self):
        """evaluate_risk가 올바른 risk_level 반환"""
        result = evaluate_risk(
            {"is_blacklisted": True, "is_new_account": False},
            {"amount": 0, "hour": 12, "repeat_attempt_count": 0},
        )
        assert result.risk_level == "high"
        assert result.decision_level == "risk"
        assert result.ai_intervention_required is True
        assert "고위험 점수 구간" in result.trigger_reasons
        assert len(result.reasons) > 0

    def test_primary_high_amount_trigger_sets_ai_intervention(self):
        result = evaluate_risk(
            {"is_blacklisted": False, "is_new_account": False},
            {"amount": 11_000_000, "hour": 14, "repeat_attempt_count": 0},
        )
        assert result.ai_intervention_required is True
        assert "1차 트리거: 고액 송금" in result.trigger_reasons
