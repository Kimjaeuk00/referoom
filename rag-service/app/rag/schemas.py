"""/rag-query 요청·응답 스키마 (DEV_04 2절)."""
from typing import Literal

from pydantic import BaseModel, Field

Level = Literal["L1", "L2", "L3"]
View = Literal["dev", "rnd"]


class Scope(BaseModel):
    type: Literal["all", "paper", "tag"] = "all"
    ids: list[int] | None = None
    tags: list[str] | None = None


class RagRequest(BaseModel):
    # team_id 등 정의되지 않은 필드는 무시한다 (team_id는 JWT에서만 읽음)
    question: str = Field(min_length=2, max_length=1000)
    source: Literal["pdf", "web", "all"] = "all"
    scope: Scope = Field(default_factory=Scope)
    level: Level | None = None  # 이번 질문의 설명 깊이. '더 쉽게'=L1, '더 깊게'=L3, 생략하면 기본 깊이(L2 규칙)
    view: View | None = None
    top_k: int = Field(default=5, ge=1, le=10)


class AnswerDraft(BaseModel):
    """LLM 구조화 출력 (DEV_04 3.4절)."""
    found: bool = Field(description="근거로 답할 수 있는가")
    answer: str = Field(description="[S#] 라벨을 포함한 본문")
    cited: list[str] = Field(default_factory=list, description="실제 인용한 라벨 예: ['S1','S3']")


class SourceDetail(BaseModel):
    label: str
    paper_id: int | None = None
    title: str
    page: int | None = None
    url: str | None = None
    snippet: str = Field(default="", max_length=200)


class RagResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)
    source_details: list[SourceDetail] = Field(default_factory=list)
    needs_review: bool = False
    handoff: bool = False
    level: Level
    view: View
    latency_ms: int
