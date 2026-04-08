from fastapi.testclient import TestClient

from backend.main import app


def test_voice_answer_hard_stop_on_agency_directive_yes():
    client = TestClient(app)
    payload = {
        "question_id": 1,
        "question_text": "혹시 경찰, 검찰, 금감원 같은 공공기관에서 직접 이체나 현금 전달을 지시했나요?",
        "question_intent": "agency_directive",
        "answer_text": "네 직접 지시했습니다",
        "max_questions": 5,
        "age_group": "10~20대",
        "conversation_log": [],
    }
    resp = client.post("/api/auth/voice/answer", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommended_action"] == "block"
    assert body["risk_tier"] == "high"
    assert body["is_phishing"] is True
    assert body["phishing_type"] == "agency_fraud"


def test_voice_answer_hard_stop_on_directive_phrase_even_without_explicit_yes():
    client = TestClient(app)
    payload = {
        "question_id": 1,
        "question_text": "혹시 경찰, 검찰, 금감원 같은 공공기관에서 직접 이체나 현금 전달을 지시했나요?",
        "question_intent": "agency_directive",
        "answer_text": "직접 이체하라 했어요",
        "max_questions": 5,
        "age_group": "10~20대",
        "conversation_log": [],
    }
    resp = client.post("/api/auth/voice/answer", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["recommended_action"] == "block"
    assert body["risk_tier"] == "high"
    assert body["is_phishing"] is True
