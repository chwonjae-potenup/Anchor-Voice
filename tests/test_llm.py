"""
tests/test_llm.py  — Tester Agent
LLM 앵커 판별 단위 테스트 (규칙 기반 fallback 검증)
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai.anchor_prompts import rule_based_detect, ANCHOR_QUESTIONS, get_question_by_id


class TestAnchorPrompts:

    def test_all_questions_defined(self):
        """5개 앵커 질문이 모두 정의되어 있어야 함"""
        assert len(ANCHOR_QUESTIONS) == 5
        for q in ANCHOR_QUESTIONS:
            assert "id" in q
            assert "text" in q
            assert len(q["text"]) > 10

    def test_get_question_by_id(self):
        for i in range(1, 6):
            q = get_question_by_id(i)
            assert q is not None
            assert q["id"] == i

    def test_normal_scenario_not_phishing(self):
        """정상 시나리오 — 모두 아니요 → 피싱 아님"""
        answers = {1: False, 2: False, 3: False, 4: False, 5: False}
        result = rule_based_detect(answers)
        assert result["is_phishing"] is False
        assert result["phishing_type"] == "normal"

    def test_loan_fraud_detection(self):
        """대출사기형 시나리오 — Q2+Q4+Q5 모두 예 → loan_fraud"""
        answers = {1: False, 2: True, 3: True, 4: True, 5: True}
        result = rule_based_detect(answers)
        assert result["is_phishing"] is True
        assert result["phishing_type"] in ["loan_fraud", "mixed"]
        assert result["confidence"] >= 0.75

    def test_agency_fraud_detection(self):
        """수사기관사칭형 시나리오 — Q1+Q2+Q3+Q4 모두 예 → agency_fraud"""
        answers = {1: True, 2: True, 3: True, 4: True, 5: False}
        result = rule_based_detect(answers)
        assert result["is_phishing"] is True
        assert result["phishing_type"] in ["agency_fraud", "mixed"]
        assert result["confidence"] >= 0.75

    def test_three_yes_triggers_phishing(self):
        """어느 유형이든 3개 이상 예 → 피싱 탐지"""
        answers = {1: True, 2: True, 3: True, 4: False, 5: False}
        result = rule_based_detect(answers)
        assert result["is_phishing"] is True
