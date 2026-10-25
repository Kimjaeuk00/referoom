"""Voice API: common authentication, local STT and owner-scoped audio."""
import asyncio
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

# Process environment wins over service-local values. Keep legacy env loading only.
APP_DIR = Path(__file__).resolve().parent
load_dotenv(APP_DIR.parent / ".env")
load_dotenv(APP_DIR / ".env")

from referoom_common import (
    RequestLoggingMiddleware, get_settings, register_error_handlers, require_team,
)
from app.routers.audio import (
    AUDIO_TTL_SECONDS, AudioStorage, create_audio_router, storage as default_storage,
)
from app.routers.stt import create_stt_router
from app.routers.tts import create_tts_router
from app.routers.voice_qa import create_voice_qa_router
from app.services.rag_client import RagClient
from app.services import stt_service

logger = logging.getLogger(__name__)


async def load_whisper():
    try:
        await run_in_threadpool(stt_service.initialize_model)
    except Exception:
        logger.error("Whisper initialization failed; check model availability and restart.")


async def cleanup_audio(storage):
    while True:
        await asyncio.sleep(AUDIO_TTL_SECONDS)
        await run_in_threadpool(storage.cleanup)


@asynccontextmanager
async def lifespan(app):
    await run_in_threadpool(app.state.audio_storage.cleanup)
    loading_task = asyncio.create_task(load_whisper())
    cleanup_task = asyncio.create_task(cleanup_audio(app.state.audio_storage))
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        await loading_task


def create_app(audio_storage: AudioStorage | None = None, rag_client: RagClient | None = None) -> FastAPI:
    # Fail at startup if shared JWT settings are absent or invalid.
    settings = get_settings()
    app = FastAPI(title="Referoom Voice Service", lifespan=lifespan)
    app.state.audio_storage = default_storage if audio_storage is None else audio_storage
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
    )

    @app.get("/health", tags=["health"], summary="Whisper 모델 준비 상태",
             responses={503: {"description": "Whisper 모델 준비 전"}})
    async def health():
        if stt_service.model_status() != "ready":
            return JSONResponse(status_code=503, content={
                "detail": "음성 인식 모델이 준비되지 않았습니다.", "code": "NOT_READY",
            })
        return {"whisper": "ready"}

    app.include_router(create_stt_router(require_team))
    app.include_router(create_tts_router(require_team, app.state.audio_storage))
    app.include_router(create_audio_router(require_team, app.state.audio_storage))
    app.include_router(create_voice_qa_router(require_team, app.state.audio_storage,
                                              rag_client if rag_client is not None else RagClient()))
    # Outermost user middleware: logs OPTIONS too, sets response request ID.
    app.add_middleware(RequestLoggingMiddleware)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8008)
