"""Authenticated voice tutor: local STT -> tutor RAG -> optional TTS."""
import logging
from time import perf_counter
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.concurrency import run_in_threadpool
from referoom_common import ApiError

from app.routers.tts import _synthesize_and_store
from app.services import stt_service
from app.services.rag_client import RagClient, RagQuestion, Scope
from app.services.speech_text import make_speech_text
from app.utils.audio_utils import AudioInputError

logger = logging.getLogger(__name__)


class Latency(BaseModel):
    stt: int
    rag: int
    tts: int
    total: int


class VoiceAnswer(BaseModel):
    model_config = ConfigDict(extra="allow")
    stt_text: str
    answer: str
    sources: list[str]
    source_details: list[dict]
    needs_review: bool
    handoff: bool
    level: Literal["L1", "L2", "L3"]
    speech_text: str
    audio_id: str | None
    audio_url: str | None
    latency_ms: Latency


def elapsed(started):
    return round((perf_counter()-started)*1000)


def create_voice_qa_router(require_team, storage, rag_client: RagClient):
    router = APIRouter(tags=["voice-qa"])

    @router.post("/voice-qa", response_model=VoiceAnswer, summary="음성 논문 튜터",
                 description="STT→튜터 RAG→선택 TTS. TTS 실패에도 답변·출처를 보존하고 audio 필드는 null입니다. 자동 재시도는 하지 않습니다.")
    async def voice_qa(
        request: Request, audio: UploadFile = File(...),
        scope: str | None = Form(None), speak: Literal["true", "false"] = Form("true"),
        language: Literal["ko", "en", "auto"] = Form("ko"),
        level: Literal["L1", "L2", "L3"] | None = Form(None),
        user=Depends(require_team),
    ):
        started = perf_counter()
        try:
            # require_team has already validated auth, but only a caller Bearer is forwarded.
            authorization = request.headers.get("authorization")
            if not authorization:
                raise ApiError(401, "UNAUTHORIZED", "음성 튜터에는 Bearer 인증이 필요합니다.")
            try:
                parsed_scope = Scope.model_validate_json(scope) if scope is not None else Scope()
            except ValidationError:
                raise ApiError(422, "VALIDATION_ERROR", "검색 범위 형식이 올바르지 않습니다.") from None
            tick = perf_counter()
            try:
                result = await run_in_threadpool(stt_service.transcribe_upload, audio.file, audio.filename, language)
            except AudioInputError as exc:
                raise ApiError(exc.status_code, exc.code, str(exc)) from None
            except stt_service.EmptyTranscriptionError:
                raise ApiError(422, "STT_EMPTY", "음성을 인식하지 못했어요. 다시 말씀해 주세요.") from None
            except (stt_service.ModelNotReadyError, FileNotFoundError):
                raise ApiError(503, "NOT_READY", "음성 인식 서비스를 준비 중입니다.") from None
            stt_ms = elapsed(tick)
            text = result["text"].strip()
            if not text:
                raise ApiError(422, "STT_EMPTY", "음성을 인식하지 못했어요. 다시 말씀해 주세요.")
            try:
                question = RagQuestion(question=text, scope=parsed_scope, level=level)
            except ValidationError:
                raise ApiError(422, "VALIDATION_ERROR", "인식한 질문은 2~1000자여야 합니다.") from None
            tick = perf_counter()
            rag = await rag_client.query(question, authorization, request.state.request_id)
            rag_ms = elapsed(tick)
            speech = make_speech_text(rag.answer, rag.handoff)
            audio_id = None
            tts_ms = 0
            if speak == "true":
                tick = perf_counter()
                try:
                    audio_id = await run_in_threadpool(_synthesize_and_store, speech, None, user.id, storage)
                except Exception:
                    # Answer and citations survive synthesis/storage failures. Never retry here.
                    logger.warning("Voice synthesis unavailable; answer and citations preserved.")
                tts_ms = elapsed(tick)
            return {
                **rag.model_dump(), "stt_text": text, "speech_text": speech,
                "audio_id": audio_id, "audio_url": f"/audio/{audio_id}" if audio_id else None,
                "latency_ms": {"stt": stt_ms, "rag": rag_ms, "tts": tts_ms, "total": elapsed(started)},
            }
        finally:
            await audio.close()

    return router
