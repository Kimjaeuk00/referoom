"""/rag-query 요청·응답 스키마 (DEV_04 2절)와 v0.2 모드(주제·검증·요약)의 요청·응답.

새 모드의 응답 형식은 프론트(frontend/src/api/mock/index.js, components/qa)가 읽는 필드와 같다.
"""
from typing import Literal

from pydantic import BaseModel, Field, StrictInt, field_validator, model_serializer

Level = Literal["L1", "L2", "L3"]
View = Literal["dev", "rnd"]
Mode = Literal["tutor", "prior"]  # /rag-query의 모드. 주제·검증은 전용 경로(/topic-suggest, /verify)를 쓴다


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
    mode: Mode = "tutor"  # prior면 논문별 정리표(table)를 더해 답한다. 생략하면 지금까지와 같은 튜터


class AnswerDraft(BaseModel):
    """LLM 구조화 출력 (DEV_04 3.4절)."""
    found: bool = Field(description="근거로 답할 수 있는가")
    answer: str = Field(description="[S#] 라벨을 포함한 본문")
    cited: list[str] = Field(default_factory=list, description="실제 인용한 라벨 예: ['S1','S3']")


class PriorCell(BaseModel):
    """선행연구 정리표의 한 칸. 근거에 없으면 value와 label 모두 null."""
    key: Literal["problem", "method", "dataset", "metric", "result", "limitation"]
    value: str | None = Field(default=None, description="근거에 있는 내용. 없으면 null")
    label: str | None = Field(default=None, description="값의 근거가 된 블록의 라벨 하나. 예: S2")


class PriorRowDraft(BaseModel):
    """LLM 구조화 출력: 논문 한 편의 정리표 행 (칸 6개)."""
    cells: list[PriorCell] = Field(default_factory=list)


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
    table: list[dict] | None = None  # mode=prior일 때만. 논문별 행 {paper_id, title, problem, method, dataset, metric, result, limitation, labels}

    @model_serializer(mode="wrap")
    def _omit_empty_table(self, handler):
        # 튜터 응답의 키 집합은 예전과 같게 유지한다(table은 값이 있을 때만 응답에 나온다)
        data = handler(self)
        if data.get("table") is None:
            data.pop("table", None)
        return data


# ---- 주제 모드: POST /topic-suggest ----
Perspective = Literal["limitation_fix", "combine", "extend", "efficiency", "evaluation"]
Verdict = Literal["match", "mismatch", "condition_differs", "not_found", "own_result"]


class TopicRequest(BaseModel):
    paper_ids: list[StrictInt] = Field(min_length=1, max_length=10)  # 대상 논문 1~10편 (MAX_COLLECT와 같다)
    hint: str = Field(default="", max_length=1000)  # 원하는 방향(비워도 된다)
    n: int = Field(default=4, ge=1, le=4)
    view: View | None = None


class Limitation(BaseModel):
    label: str
    paper_id: int | None = None
    title: str
    page: int | None = None
    summary: str


class Experiment(BaseModel):
    datasets: list[str] = Field(default_factory=list)
    baselines: list[str] = Field(default_factory=list)
    metrics: list[str] = Field(default_factory=list)


class SimilarPaper(BaseModel):
    paper_id: int
    title: str
    score: float


class TopicCandidate(BaseModel):
    perspective: Perspective
    title: str
    question: str
    approach: str
    experiment: Experiment = Field(default_factory=Experiment)
    based_on: list[str] = Field(default_factory=list)  # 근거가 된 한계의 라벨
    similar_papers: list[SimilarPaper] = Field(default_factory=list)
    ai_generated: bool = True


class TopicResponse(BaseModel):
    limitations: list[Limitation] = Field(default_factory=list)
    topics: list[TopicCandidate] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    source_details: list[SourceDetail] = Field(default_factory=list)
    needs_review: bool = True  # 후보는 항상 사람이 검토한다
    handoff: bool = False
    view: View
    latency_ms: int


# ---- 검증 모드: POST /verify ----
class VerifyRequest(BaseModel):
    text: str = Field(max_length=3000)  # 원고. 로그·예외·색인에 남기지 않는다
    paper_ids: list[StrictInt] | None = Field(default=None, max_length=50)  # 없으면 팀 전체
    view: View | None = None

    @field_validator("text")
    @classmethod
    def _at_least_ten_chars(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise ValueError("too short")  # 메시지에 입력을 담지 않는다
        return value


class Delta(BaseModel):
    vs: str | None = None
    value: float


class Claim(BaseModel):
    sentence: str
    subject: str | None = None
    metric: str | None = None
    claimed_value: str | None = None
    dataset: str | None = None
    found_value: str | None = None
    condition: str | None = None
    verdict: Verdict = "not_found"
    labels: list[str] = Field(default_factory=list)
    delta: Delta | None = None


class VerifyResponse(BaseModel):
    claims: list[Claim] = Field(default_factory=list)
    draft: str = ""
    warnings: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    source_details: list[SourceDetail] = Field(default_factory=list)
    needs_review: bool = True  # 수치를 다루므로 항상 검토한다
    handoff: bool = False
    view: View
    latency_ms: int


# ---- 논문 요약: POST /summary ----
class SummaryRequest(BaseModel):
    paper_id: StrictInt
    view: View | None = None


class SummarySection(BaseModel):
    key: str
    title: str
    text: str
    sources: list[str] = Field(default_factory=list)  # '제목 p.4' 문자열


class SummaryResponse(BaseModel):
    paper_id: int
    title: str
    view: View
    sections: list[SummarySection] = Field(default_factory=list)
    needs_review: bool = True
    latency_ms: int
