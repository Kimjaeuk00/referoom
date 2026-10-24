"""데이터 API 요청·응답 모델. 필드는 프론트 목업(frontend/src/api/mock/index.js)의 계약과 같다."""
from typing import Literal

from pydantic import BaseModel, Field

SourceType = Literal["pdf", "web", "zotero"]
PaperStatus = Literal["pending", "indexed", "failed"]


class PaperOut(BaseModel):
    id: int
    title: str
    authors: str
    year: int | None
    source_type: SourceType
    tags: list[str]
    status: PaperStatus
    chunk_count: int | None
    error_msg: str | None
    url: str | None
    created_at: str | None
    added_by: str | None


class PaperList(BaseModel):
    total: int
    items: list[PaperOut]


class LibraryStats(BaseModel):
    papers: int
    indexed: int
    failed: int
    chunks: dict[str, int]
    last_synced_at: str | None


class SearchTopicRequest(BaseModel):
    # 프론트가 보내는 provider 등 정의되지 않은 필드는 무시한다
    topic: str = Field(min_length=2, max_length=200)
    max_results: int = Field(default=10, ge=1, le=20)


class Candidate(BaseModel):
    candidate_id: str
    title: str
    authors: list[str]
    year: int
    abstract: str
    url: str
    pdf_url: str
    relevance: float
    low_relevance: bool
    already_in_library: bool


class SearchTopicResponse(BaseModel):
    topic: str
    candidates: list[Candidate]


class UploadTopicRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=200)
    selected: list[str] = Field(min_length=1, max_length=10)  # 사용자가 고른 candidate_id만 수집한다


class UploadTopicResponse(BaseModel):
    batch_id: int
    requested: int


class UploadPaperResponse(BaseModel):
    batch_id: int
    paper_id: int | None  # Zotero 항목이 만들어진 뒤에 정해지므로 접수 시점에는 없다
    status: Literal["pending"]


class BatchPaper(BaseModel):
    paper_id: int | None
    title: str
    status: Literal["pending", "indexed", "failed", "skipped"]
    chunk_count: int | None
    error_msg: str | None


class BatchOut(BaseModel):
    id: int
    kind: Literal["upload_pdf", "topic", "zotero_sync"]
    status: Literal["running", "done", "failed"]
    requested: int
    indexed: int
    skipped: int
    failed: int
    removed: int
    error_msg: str | None
    papers: list[BatchPaper]


class ZoteroConfig(BaseModel):
    configured: bool
    group_id: int | None
    last_synced_at: str | None


class SyncResponse(BaseModel):
    batch_id: int
