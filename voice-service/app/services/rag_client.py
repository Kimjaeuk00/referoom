"""One-shot, bearer-preserving calls to the existing tutor RAG contract."""
import os
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from referoom_common import ApiError


class Scope(BaseModel):
    type: Literal["all", "paper", "tag"] = "all"
    ids: list[int] | None = None
    tags: list[str] | None = None


class RagQuestion(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    source: Literal["pdf", "web", "all"] = "all"
    scope: Scope = Field(default_factory=Scope)
    view: Literal["dev", "rnd"]
    level: Literal["L1", "L2", "L3"] | None = None


class SourceDetail(BaseModel):
    model_config = ConfigDict(extra="allow")
    label: str
    title: str
    paper_id: int | None = None
    page: int | None = None
    url: str | None = None
    snippet: str = Field(default="", max_length=200)


class RagAnswer(BaseModel):
    model_config = ConfigDict(extra="allow")
    answer: str = Field(min_length=1)
    sources: list[str]
    source_details: list[SourceDetail]
    needs_review: bool
    handoff: bool
    level: Literal["L1", "L2", "L3"]
    view: Literal["dev", "rnd"]
    latency_ms: int = Field(ge=0)


ERROR_CODES = {"UNAUTHORIZED", "TOKEN_EXPIRED", "NO_TEAM", "FORBIDDEN", "NOT_FOUND",
               "VALIDATION_ERROR", "PAYLOAD_TOO_LARGE", "TOO_MANY_REQUESTS", "NOT_READY",
               "UPSTREAM_TIMEOUT", "INTERNAL_ERROR"}


class RagClient:
    def __init__(self, base_url=None, transport=None):
        self.base_url = (base_url if base_url is not None else os.getenv("RAG_URL", "http://localhost:8001")).rstrip("/")
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("RAG_URL must be an HTTP(S) service URL without credentials/query/fragment")
        self.transport = transport

    async def query(self, question: RagQuestion, authorization: str, request_id: str):
        # httpx has no automatic request retries here. Never follow redirects with JWT.
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=5.0), transport=self.transport,
                follow_redirects=False, trust_env=False,
            ) as client:
                response = await client.post(
                    self.base_url + "/rag-query",
                    json=question.model_dump(exclude_none=True),
                    headers={"Authorization": authorization, "X-Request-Id": request_id},
                )
        except httpx.TimeoutException:
            raise ApiError(503, "UPSTREAM_TIMEOUT", "답변 응답을 기다리는 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.") from None
        except httpx.RequestError:
            raise ApiError(503, "NOT_READY", "답변 서비스에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.") from None
        if response.status_code != 200:
            status = response.status_code if 400 <= response.status_code <= 599 else 502
            try:
                code = response.json().get("code")
            except (ValueError, AttributeError):
                code = None
            defaults = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 422: "VALIDATION_ERROR", 429: "TOO_MANY_REQUESTS", 503: "NOT_READY", 504: "UPSTREAM_TIMEOUT"}
            code = code if isinstance(code, str) and code in ERROR_CODES else defaults.get(status, "UPSTREAM_ERROR")
            # Preserve status/code; never forward provider or validation input details.
            raise ApiError(status, code, "답변 요청을 처리하지 못했습니다. 인증 또는 서비스 상태를 확인해 주세요.")
        try:
            result = RagAnswer.model_validate(response.json())
            if not result.answer.strip():
                raise ValueError("Empty answer")
            return result
        except (ValidationError, ValueError):
            raise ApiError(502, "UPSTREAM_ERROR", "답변 서비스의 응답 형식을 확인할 수 없습니다.") from None
