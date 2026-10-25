"""STT API; registered with common-py require_team."""

from time import perf_counter

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from app.services import stt_service
from app.utils.audio_utils import AudioInputError


class SttResponse(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{
        "text": "LoRA는 어떤 파라미터를 학습해?", "language": "ko",
        "duration_s": 4.2, "latency_ms": 1200,
    }]}}

    text: str
    language: str
    duration_s: float
    latency_ms: int


def create_stt_router(require_team) -> APIRouter:
    router = APIRouter(tags=["stt"])

    @router.post(
        "/stt", summary="음성을 텍스트로 변환", response_model=SttResponse,
        description="multipart 파일을 인식합니다. 최대 10MB·60초이며 결과가 비면 STT_EMPTY입니다. "
                    "공통 require_team으로 보호되는 API입니다.",
        responses={413: {"description": "10MB 초과", "content": {"application/json": {"example": {
                       "detail": "오디오 파일은 10MB 이하여야 합니다.", "code": "PAYLOAD_TOO_LARGE"}}}},
                   422: {"description": "입력 검증 실패 또는 STT_EMPTY. 공통 오류 형식으로 응답합니다.",
                         "content": {"application/json": {"examples": {
                             "empty": {"value": {"detail": "음성을 인식하지 못했어요. 다시 말씀해 주세요.", "code": "STT_EMPTY"}},
                             "invalid": {"value": {"detail": "지원하지 않는 오디오 형식입니다.", "code": "VALIDATION_ERROR"}},
                         }}}},
                   503: {"description": "음성 인식 모델 또는 변환 도구 미준비", "content": {"application/json": {"example": {
                       "detail": "음성 인식 서비스를 준비 중입니다.", "code": "NOT_READY"}}}}},
    )
    async def transcribe(
        audio: UploadFile = File(..., description="10MB·60초 이하의 webm/ogg/mp4/m4a/wav 파일"),
        language: str = Form("ko", description="ko: 한국어, en: 영어, auto: 자동 감지", examples=["ko", "en", "auto"]),
        current_user=Depends(require_team),
    ):
        started = perf_counter()
        try:
            result = await run_in_threadpool(
                stt_service.transcribe_upload, audio.file, audio.filename, language,
            )
            return {**result, "latency_ms": round((perf_counter() - started) * 1000)}
        except AudioInputError as error:
            return JSONResponse(
                status_code=error.status_code,
                content={"detail": str(error), "code": error.code},
            )
        except stt_service.EmptyTranscriptionError as error:
            return JSONResponse(
                status_code=422, content={"detail": str(error), "code": "STT_EMPTY"},
            )
        except (stt_service.ModelNotReadyError, FileNotFoundError):
            return JSONResponse(
                status_code=503,
                content={"detail": "음성 인식 서비스를 준비 중입니다.", "code": "NOT_READY"},
            )
        finally:
            await audio.close()

    return router
