from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from app.rag import pipeline
from app.rag.deps import CurrentUser, require_team, store
from app.rag.errors import ApiError
from app.rag.schemas import RagRequest, RagResponse

router = APIRouter()


@router.post("/rag-query", response_model=RagResponse, summary="팀 논문 근거 기반 질의응답", tags=["질의 응답"])
async def rag_query(request: Request, req: RagRequest, user: CurrentUser = Depends(require_team)) -> RagResponse:
    if not store.readiness().get("embedder"):
        raise ApiError(503, "NOT_READY", "검색 준비 중입니다. 잠시 후 다시 시도해 주세요.")
    usage: dict = {}
    resp = await run_in_threadpool(pipeline.run, req, user, usage)
    # 백엔드 로깅 미들웨어가 JSON 로그로 남긴다 (DEV_04 3.7절)
    request.state.in_tok = usage.get("in_tok", 0)
    request.state.out_tok = usage.get("out_tok", 0)
    return resp


@router.get("/health", summary="상태 확인", tags=["상태"])
async def health() -> dict:
    return {"status": "ok", **store.readiness()}
