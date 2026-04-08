"""
backend/main.py  — Backend Agent
FastAPI 앱 엔트리포인트
"""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.router import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Anchor-Voice API",
    description="보이스피싱 방지 AI 뱅킹 에이전트",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

logger.info("Anchor-Voice Backend 서버 시작")


@app.on_event("startup")
async def warmup_models() -> None:
    from backend.config import settings

    if settings.PRELOAD_WHISPER:
        try:
            from ai.whisper_stt import prewarm_model as prewarm_whisper

            if prewarm_whisper():
                logger.info("Whisper prewarm: ok")
            else:
                logger.warning("Whisper prewarm: failed")
        except Exception as e:
            logger.warning("Whisper prewarm error: %s", e)

    if settings.PRELOAD_DEEPFACE:
        try:
            from ai.deepface_auth import prewarm_model as prewarm_deepface

            if prewarm_deepface():
                logger.info("DeepFace prewarm: ok")
            else:
                logger.warning("DeepFace prewarm: failed")
        except Exception as e:
            logger.warning("DeepFace prewarm error: %s", e)


if __name__ == "__main__":
    import uvicorn
    from backend.config import settings
    uvicorn.run("backend.main:app", host=settings.BACKEND_HOST,
                port=settings.BACKEND_PORT, reload=True)
