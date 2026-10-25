"""TTS API; registered with common-py require_team."""

import os
from time import perf_counter

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.routers.audio import AudioStorage, storage
from app.services import tts_service


class TtsRequest(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"text": "LoRA는 저랭크 행렬을 학습합니다.", "voice": "nova"}]}}

    text: str = Field(description="음성으로 변환할 텍스트")
    voice: str = Field(default_factory=lambda: os.getenv("TTS_VOICE", "nova"), description="생략 시 TTS_VOICE 환경변수, 미설정 시 nova")

    @field_validator("text", "voice")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("값을 입력해 주세요.")
        return value


class TtsResponse(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{
        "audio_id": "12345678123456781234567812345678",
        "audio_url": "/audio/12345678123456781234567812345678", "latency_ms": 850,
    }]}}

    audio_id: str
    audio_url: str
    latency_ms: int


def _synthesize_and_store(text: str, voice: str, owner: str, audio_storage: AudioStorage) -> str:
    content = tts_service.synthesize_speech(text, voice)
    return audio_storage.save(owner, content)


def create_tts_router(require_team, audio_storage: AudioStorage = storage) -> APIRouter:
    router = APIRouter(tags=["tts"])

    @router.post(
        "/tts", response_model=TtsResponse, summary="텍스트를 음성으로 변환",
        description="MP3를 생성해 요청자 소유로 10분간 저장합니다. 반환된 audio_url은 인증된 "
                    "GET 요청으로 내려받습니다. 공통 require_team으로 보호되는 API입니다.",
        responses={422: {"description": "입력 검증 실패. 공통 오류 형식으로 응답합니다."},
                   503: {"description": "NOT_READY 또는 UPSTREAM_TIMEOUT", "content": {"application/json": {"examples": {
                       "not_ready": {"value": {"detail": "음성 합성 서비스를 준비 중입니다.", "code": "NOT_READY"}},
                       "upstream": {"value": {"detail": "음성 합성 서비스에 연결할 수 없습니다. 다시 시도해 주세요.", "code": "UPSTREAM_TIMEOUT"}},
                   }}}}},
    )
    async def synthesize(payload: TtsRequest, current_user=Depends(require_team)):
        started = perf_counter()
        try:
            audio_id = await run_in_threadpool(
                _synthesize_and_store, payload.text, payload.voice, current_user.id, audio_storage,
            )
        except tts_service.TtsNotReadyError as error:
            return JSONResponse(
                status_code=503, content={"detail": str(error), "code": "NOT_READY"},
            )
        except tts_service.TtsUpstreamError as error:
            return JSONResponse(
                status_code=503, content={"detail": str(error), "code": "UPSTREAM_TIMEOUT"},
            )
        return {
            "audio_id": audio_id,
            "audio_url": f"/audio/{audio_id}",
            "latency_ms": round((perf_counter() - started) * 1000),
        }

    return router
