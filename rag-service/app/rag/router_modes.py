"""v0.2 모드 전용 경로: 주제 제안(/topic-suggest), 원고 검증(/verify). 요약(/summary)도 이 파일에 더한다.

/rag-query는 router.py에 두고, 모드별 요청·응답 형식이 따로인 경로만 여기에 둔다.
"""
from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.rag import topic, verify
from app.rag.deps import CurrentUser, require_team, store
from app.rag.errors import ApiError
from app.rag.schemas import TopicRequest, TopicResponse, VerifyRequest, VerifyResponse

router = APIRouter()


def _ready() -> None:
    if not store.readiness().get("embedder"):
        raise ApiError(503, "NOT_READY", "검색 준비 중입니다. 잠시 후 다시 시도해 주세요.")


def _record_tokens(request: Request, usage: dict) -> None:
    # 공통 요청 로그가 JSON 로그로 남긴다. 호출 중 실패한 경우는 기록하지 않아 '알 수 없음'(null)으로 남는다
    request.state.in_tok = usage.get("in_tok", 0)
    request.state.out_tok = usage.get("out_tok", 0)


@router.post("/topic-suggest", response_model=TopicResponse, summary="선택한 논문의 한계로 연구 주제 후보 제안", tags=["주제 제안"])
async def topic_suggest(request: Request, req: TopicRequest, user: CurrentUser = Depends(require_team)) -> TopicResponse:
    _ready()
    usage: dict = {}
    resp = await run_in_threadpool(topic.run, req, user, usage)
    _record_tokens(request, usage)
    return resp


@router.post("/verify", response_model=VerifyResponse, summary="원고의 수치를 선행연구 근거와 대조", tags=["원고 검증"])
async def verify_manuscript(request: Request, req: VerifyRequest, user: CurrentUser = Depends(require_team)) -> VerifyResponse:
    _ready()
    usage: dict = {}
    resp = await run_in_threadpool(verify.run, req, user, usage)
    _record_tokens(request, usage)
    return resp
