"""
backend/schemas.py  — 인터페이스 계약 (전 에이전트 공유)
음성 텍스트 기반 분석 및 이미지 bytes 전달 방식 반영
"""
from pydantic import BaseModel, Field
from typing import Optional


# ── 이체 위험도 체크 ──────────────────────────────────────────────────────────

class TransferRequest(BaseModel):
    account_number: str = Field(..., description="수취 계좌번호")
    amount: int = Field(..., gt=0, description="이체 금액 (원)")
    hour: int = Field(..., ge=0, le=23, description="이체 시각 (0~23시)")
    is_new_account: bool = Field(False, description="처음 이체하는 계좌 여부")
    is_blacklisted: bool = Field(False, description="블랙리스트 계좌 여부")
    repeat_attempt_count: int = Field(0, description="짧은 시간 내 반복 시도 횟수")

class RiskCheckResponse(BaseModel):
    risk_score: int = Field(..., ge=0, le=100, description="위험도 점수 0~100")
    risk_level: str = Field(..., description="'low' | 'high'")
    reason: list[str] = Field(default_factory=list, description="위험 요소 목록")


# ── 안면 인식 (브라우저 웹캠 → bytes 전달) ───────────────────────────────────

class FaceAuthResponse(BaseModel):
    verified: bool
    distance: Optional[float] = None
    threshold: Optional[float] = None
    time_ms: Optional[int] = None
    fallback: bool = False
    message: str = ""


# ── TTS (텍스트 → 음성) ────────────────────────────────────────────────────────

class TtsRequest(BaseModel):
    text: str = Field(..., description="음성으로 변환할 텍스트")
    lang: str = Field("ko", description="언어 코드")

# TTS 응답은 audio/mpeg StreamingResponse 사용


# ── STT (음성 → 텍스트) ───────────────────────────────────────────────────────

class SttResponse(BaseModel):
    text: str = Field(..., description="변환된 텍스트")
    duration_seconds: Optional[float] = None


# ── Anchor Voice 대화 (음성 텍스트 기반) ──────────────────────────────────────

class VoiceStartResponse(BaseModel):
    question_id: int = Field(1)
    question_text: str = Field(..., description="TTS로 읽어줄 질문 텍스트")


class VoiceNextQuestionRequest(BaseModel):
    conversation_log: list[dict] = Field(
        default_factory=list,
        description="누적 대화 로그",
    )
    max_questions: int = Field(5, ge=3, le=10, description="최대 질문 수")
    age_group: str = Field("10~20대", description="연령대 (현재 고정 프로필: 10~20대)")


class VoiceNextQuestionResponse(BaseModel):
    done: bool = Field(False, description="질문 종료 여부")
    question_id: int = Field(1, ge=1, le=20, description="다음 질문 ID")
    question_text: str = Field("", description="다음 질문 텍스트")
    question_intent: str = Field("", description="질문 의도(intent)")
    reason: str = Field("", description="질문 선택 근거")
    max_questions: int = Field(5, ge=3, le=10, description="최대 질문 수")


class VoiceAnswerRequest(BaseModel):
    question_id: int = Field(..., ge=1, le=20)
    question_text: str = Field("", description="실제로 물어본 질문 텍스트")
    question_intent: str = Field("", description="질문 의도(intent)")
    answer_text: str = Field(..., description="사용자가 실제로 말한 텍스트 (STT 결과)")
    max_questions: int = Field(5, ge=3, le=10)
    age_group: str = Field("10~20대", description="연령대 (현재 고정 프로필: 10~20대)")
    conversation_log: list[dict] = Field(
        default_factory=list,
        description="누적 대화 로그 [{'question_id': int, 'question': str, 'answer_text': str, 'question_intent': str}, ...]"
    )

class PhishingAnalysisResponse(BaseModel):
    is_phishing: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    phishing_type: str = Field(..., description="'loan_fraud' | 'agency_fraud' | 'family_fraud' | 'mixed' | 'normal' | 'pending'")
    summary: str = Field("", description="LLM이 생성한 판단 근거 요약")
    triggered_questions: list[int] = Field(default_factory=list)
    recommended_action: str = Field(
        "pending",
        description="'pending' | 'block' | 'additional_auth' | 'proceed'",
    )
    risk_tier: str = Field("low", description="'low' | 'medium' | 'high'")


# ── 스텔스 SOS ───────────────────────────────────────────────────────────────

class SosTriggerRequest(BaseModel):
    transfer_info: TransferRequest
    phishing_evidence: PhishingAnalysisResponse

class SosResponse(BaseModel):
    ui_mode: str = Field("stealth_complete")
    blocked: bool = True
    fake_amount: int = Field(..., description="위장 화면에 표시할 이체 금액")
    fake_account: str = Field(..., description="위장 화면에 표시할 계좌번호")
