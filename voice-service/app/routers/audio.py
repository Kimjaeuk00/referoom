"""Protected audio storage and router; production registration needs common-py."""

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import time
from uuid import UUID, uuid4
import json
import math
import re

from fastapi import APIRouter, Depends, Path as PathParameter
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool


AUDIO_DIR = Path(__file__).resolve().parents[2] / "data" / "audio"
AUDIO_TTL_SECONDS = 10 * 60


@dataclass(frozen=True)
class AudioRecord:
    owner: str
    path: Path
    expires_at: float


class AudioStorage:
    """UUID MP3 files with persisted owner/expiry metadata."""

    def __init__(self, directory: Path = AUDIO_DIR):
        self.directory = directory
        self._lock = RLock()

    def save(self, owner: str, content: bytes) -> str:
        # Never use unvalidated identity text as a filesystem path.
        if not isinstance(owner, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", owner):
            raise ValueError("Invalid audio owner")
        audio_id = uuid4().hex
        with self._lock:
            directory = self.directory / owner
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"{audio_id}.mp3"
            metadata = directory / f"{audio_id}.json"
            try:
                path.write_bytes(content)
                metadata.write_text(
                    json.dumps({"owner": owner, "expires_at": time() + AUDIO_TTL_SECONDS}),
                    encoding="utf-8",
                )
            except Exception:
                path.unlink(missing_ok=True)
                metadata.unlink(missing_ok=True)
                raise
        return audio_id

    @staticmethod
    def _valid_id(audio_id: str) -> bool:
        try:
            return UUID(audio_id).hex == audio_id
        except (ValueError, AttributeError, TypeError):
            return False

    def _record(self, metadata: Path) -> AudioRecord | None:
        try:
            data = json.loads(metadata.read_text(encoding="utf-8"))
            owner = data["owner"]
            expires_at = float(data["expires_at"])
            if owner != metadata.parent.name or not math.isfinite(expires_at) or expires_at <= 0:
                return None
            return AudioRecord(owner, metadata.with_suffix(".mp3"), expires_at)
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def find(self, audio_id: str, owner: str) -> AudioRecord | None:
        if not self._valid_id(audio_id):
            return None
        # Locate server-created metadata, rather than constructing a path from input.
        with self._lock:
            for metadata in self.directory.glob(f"*/{audio_id}.json"):
                record = self._record(metadata)
                if record and record.owner == owner and record.expires_at > time():
                    return record if record.path.is_file() else None
        return None

    def cleanup(self) -> None:
        with self._lock:
            now = time()
            for metadata in self.directory.glob("*/*.json"):
                if not self._valid_id(metadata.stem):
                    continue
                record = self._record(metadata)
                if record and record.expires_at <= now:
                    record.path.unlink(missing_ok=True)
                    metadata.unlink(missing_ok=True)


storage = AudioStorage()


def create_audio_router(require_team, audio_storage: AudioStorage = storage) -> APIRouter:
    """The caller must supply the real common-py authentication dependency."""
    router = APIRouter(tags=["audio"])

    @router.get(
        "/audio/{audio_id}", summary="요청자 소유 음성 다운로드", response_class=FileResponse,
        description="생성 후 10분 이내의 요청자 소유 MP3를 반환합니다. 타인 소유·만료·없는 ID는 "
                    "동일한 404입니다. Bearer fetch → Blob → Object URL로 재생합니다.",
        responses={
            200: {"description": "MP3 음성", "content": {"audio/mpeg": {"schema": {"type": "string", "format": "binary"}}}},
            404: {"description": "접근 가능한 음성 없음", "content": {"application/json": {"example": {
                "detail": "음성 파일을 찾을 수 없습니다.", "code": "NOT_FOUND",
            }}}},
        },
    )
    async def download_audio(
        audio_id: str = PathParameter(description="TTS 응답의 audio_id", examples=["12345678123456781234567812345678"]),
        current_user=Depends(require_team),
    ):
        record = await run_in_threadpool(audio_storage.find, audio_id, current_user.id)
        if record is None:
            return JSONResponse(
                status_code=404,
                content={"detail": "음성 파일을 찾을 수 없습니다.", "code": "NOT_FOUND"},
            )
        return FileResponse(
            record.path, media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )

    return router
