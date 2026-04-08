"""
FastAPI routes for transfer risk checks, face auth, voice auth, TTS/STT, and SOS.
"""
from __future__ import annotations

import io
import logging
import re

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.schemas import (
    FaceAuthResponse,
    PhishingAnalysisResponse,
    RiskCheckResponse,
    SosResponse,
    SosTriggerRequest,
    SttResponse,
    TransferRequest,
    TtsRequest,
    VoiceAnswerRequest,
    VoiceNextQuestionRequest,
    VoiceNextQuestionResponse,
    VoiceStartResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _is_agency_directive_admission_fallback(answer_text: str) -> bool:
    """
    Extra robust fallback for STT variations where polarity parser may miss.
    Examples to catch:
    - "직접 이체하라 했어요"
    - "현금 전달 지시 받았어요"
    """
    text = str(answer_text or "").strip().lower()
    if not text:
        return False

    compact = re.sub(r"\s+", "", text)
    has_negative = any(k in compact for k in ["아니", "없", "안받", "받지않", "아닙"])
    if has_negative:
        return False

    directive_keywords = [
        "지시",
        "요구",
        "이체하라",
        "현금전달",
        "현금전달하라",
        "보내라고",
        "옮기라고",
        "안전계좌",
        "국가안전계좌",
    ]
    if any(k in compact for k in directive_keywords):
        return True

    return False


@router.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0", "service": "Anchor-Voice"}


@router.post("/api/transfer/risk-check", response_model=RiskCheckResponse)
async def risk_check(req: TransferRequest):
    from ai.cdd_scorer import evaluate_risk

    result = evaluate_risk(
        {"is_blacklisted": req.is_blacklisted, "is_new_account": req.is_new_account},
        {
            "amount": req.amount,
            "hour": req.hour,
            "repeat_attempt_count": req.repeat_attempt_count,
        },
    )
    return RiskCheckResponse(
        risk_score=result.score,
        risk_level=result.risk_level,
        reason=result.reasons,
    )


@router.post("/api/auth/face", response_model=FaceAuthResponse)
async def face_auth(file: UploadFile = File(...)):
    from ai.deepface_auth import verify_face_from_bytes

    image_bytes = await file.read()
    result = verify_face_from_bytes(image_bytes)
    return FaceAuthResponse(**result)


@router.post("/api/auth/face/register", response_model=FaceAuthResponse)
async def face_register(file: UploadFile = File(...)):
    from ai.deepface_auth import register_face

    image_bytes = await file.read()
    success = register_face(image_bytes)
    return FaceAuthResponse(
        verified=success,
        message="얼굴 등록 완료" if success else "등록 실패",
        fallback=not success,
    )


@router.get("/api/auth/face/challenge")
async def face_challenge():
    from ai.action_challenge import generate_challenge

    return generate_challenge()


@router.post("/api/auth/face/action")
async def face_action(action_id: str = Form(...), file: UploadFile = File(...)):
    from ai.action_challenge import detect_action_from_frame

    frame_bytes = await file.read()
    return detect_action_from_frame(frame_bytes, action_id)


@router.post("/api/auth/face/sequence-frames")
async def face_sequence_frames(
    action1_id: str = Form(...),
    action2_id: str = Form(...),
    files: list[UploadFile] = File(...),
):
    from ai.action_challenge import detect_sequence_from_frames

    frames_bytes = [await f.read() for f in files]
    return detect_sequence_from_frames(frames_bytes, action1_id, action2_id)


@router.post("/api/tts/speak")
async def tts_speak(req: TtsRequest):
    from ai.gtts_tts import get_last_tts_error, synthesize_speech

    audio_bytes = synthesize_speech(req.text, req.lang)
    if not audio_bytes:
        detail = get_last_tts_error() or "TTS conversion failed"
        raise HTTPException(status_code=503, detail=detail)

    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=question.mp3"},
    )


@router.post("/api/stt/transcribe", response_model=SttResponse)
async def stt_transcribe(file: UploadFile = File(...), lang: str = Form("ko")):
    from ai.whisper_stt import get_last_stt_error, transcribe_realtime

    audio_bytes = await file.read()
    text = transcribe_realtime(audio_bytes, lang=lang)
    stt_error = get_last_stt_error()
    if stt_error:
        raise HTTPException(status_code=503, detail=stt_error)
    return SttResponse(text=text)


@router.post("/api/auth/voice/start", response_model=VoiceStartResponse)
async def voice_start():
    from ai.llm_engine import generate_next_question

    first_q = generate_next_question([])
    return VoiceStartResponse(question_id=first_q["question_id"], question_text=first_q["question_text"])


@router.post("/api/auth/voice/next-question", response_model=VoiceNextQuestionResponse)
async def voice_next_question(req: VoiceNextQuestionRequest):
    from ai.llm_engine import generate_next_question

    result = generate_next_question(
        req.conversation_log,
        max_questions=req.max_questions,
        age_group=req.age_group,
    )
    return VoiceNextQuestionResponse(**result)


@router.post("/api/auth/voice/answer", response_model=PhishingAnalysisResponse)
async def voice_answer(req: VoiceAnswerRequest):
    from ai.anchor_prompts import ANCHOR_QUESTIONS
    from ai.llm_engine import _is_suspicious_answer, _keyword_based_detect, analyze_conversation, decide_voice_gate

    q = next((q for q in ANCHOR_QUESTIONS if q["id"] == req.question_id), None)
    asked_question_text = req.question_text or (q["text"] if q else "")
    updated_log = req.conversation_log + [
        {
            "question_id": req.question_id,
            "question": asked_question_text,
            "question_intent": req.question_intent,
            "answer_text": req.answer_text,
        }
    ]

    # Hard-stop rule: direct admission to agency transfer/cash directive must never proceed.
    intent = (req.question_intent or "").strip().lower()
    is_agency_anchor = intent == "agency_directive" or (
        req.question_id == 1 and any(k in asked_question_text for k in ["공공기관", "경찰", "검찰", "금감원"])
    )
    suspicious_answer = _is_suspicious_answer("agency_directive", req.answer_text)
    fallback_admission = _is_agency_directive_admission_fallback(req.answer_text)
    if is_agency_anchor and (suspicious_answer is True or fallback_admission):
        logger.warning(
            "Voice hard-stop: qid=%s intent=%s suspicious=%s fallback=%s answer=%r",
            req.question_id,
            intent or "inferred_agency_anchor",
            suspicious_answer,
            fallback_admission,
            req.answer_text[:120],
        )
        return PhishingAnalysisResponse(
            is_phishing=True,
            confidence=0.98,
            phishing_type="agency_fraud",
            summary="기관 이체/현금 지시를 직접 인정하여 즉시 차단합니다.",
            triggered_questions=[req.question_id],
            recommended_action="block",
            risk_tier="high",
        )

    is_last = req.question_id >= req.max_questions
    if is_last:
        raw_result = analyze_conversation(updated_log, age_group=req.age_group)
        result = decide_voice_gate(raw_result, updated_log, final_step=True)
        logger.info(
            "Final gate: action=%s type=%s (%.0f%%)",
            result["recommended_action"],
            result["phishing_type"],
            result["confidence"] * 100,
        )
        return PhishingAnalysisResponse(**result)

    quick_raw = _keyword_based_detect(updated_log, age_group=req.age_group)
    quick_gate = decide_voice_gate(quick_raw, updated_log, final_step=False)
    if quick_gate["recommended_action"] == "block":
        logger.warning("Early phishing block: %s", quick_gate["phishing_type"])
        return PhishingAnalysisResponse(**quick_gate)

    logger.info(
        "Voice pending: qid=%s intent=%s quick_action=%s risk=%s answer=%r",
        req.question_id,
        req.question_intent,
        quick_gate.get("recommended_action"),
        quick_gate.get("risk_tier"),
        req.answer_text[:120],
    )
    return PhishingAnalysisResponse(
        is_phishing=False,
        confidence=quick_gate["confidence"],
        phishing_type="pending",
        summary=(
            "의심 신호가 감지되어 확인 질문을 이어갑니다."
            if quick_gate["risk_tier"] == "medium"
            else "대화 진행 중"
        ),
        triggered_questions=quick_gate["triggered_questions"],
        recommended_action="pending",
        risk_tier=quick_gate["risk_tier"],
    )


@router.post("/api/sos/trigger", response_model=SosResponse)
async def sos_trigger(req: SosTriggerRequest):
    from backend.stealth_sos import trigger_stealth_sos

    result = await trigger_stealth_sos(
        transfer_info=req.transfer_info.model_dump(),
        phishing_evidence=req.phishing_evidence.model_dump(),
    )
    return SosResponse(**result)
