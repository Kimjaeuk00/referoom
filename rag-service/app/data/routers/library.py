"""논문 라이브러리: 목록·상세·삭제·통계. 논문의 원천은 Zotero 그룹이다 (app/data/repo.py)."""
from typing import Literal

from fastapi import APIRouter, Depends, Query, Response

from app.data import ingest, repo
from app.data.deps import require_admin, require_library
from app.data.providers.zotero import ZoteroError
from app.data.schemas import LibraryStats, PaperList, PaperOut, PaperStatus, SourceType
from app.rag.deps import CurrentUser
from app.rag.errors import ApiError

router = APIRouter(tags=["라이브러리"])

NOT_FOUND = ApiError(404, "NOT_FOUND", "논문을 찾을 수 없습니다.")


@router.get("/library/stats", response_model=LibraryStats, summary="라이브러리 통계")
async def library_stats(user: CurrentUser = Depends(require_library)) -> dict:
    return await repo.stats(user.team_id)


@router.get("/papers", response_model=PaperList, summary="논문 목록")
async def list_papers(
    q: str | None = Query(None, max_length=200, description="제목·저자 검색"),
    source_type: SourceType | None = None,
    tag: str | None = Query(None, max_length=100),
    status: PaperStatus | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    user: CurrentUser = Depends(require_library),
) -> dict:
    rows = await repo.load_rows(user.team_id)
    total, items = repo.list_papers(rows, q=q, source_type=source_type, tag=tag, status=status, page=page, size=size)
    return {"total": total, "items": [repo.public(r) for r in items]}


@router.get("/papers/{paper_id}", response_model=PaperOut, summary="논문 상세")
async def get_paper(paper_id: int, user: CurrentUser = Depends(require_library)) -> dict:
    row = await repo.get_row(user.team_id, paper_id)
    if row is None:
        raise NOT_FOUND
    return repo.public(row)


@router.delete("/papers/{paper_id}", status_code=204, summary="논문 삭제 (Zotero 휴지통으로 이동)")
async def delete_paper(paper_id: int, user: CurrentUser = Depends(require_admin)) -> Response:
    if await repo.get_row(user.team_id, paper_id) is None:
        raise NOT_FOUND
    try:
        await ingest.delete_paper(user.team_id, paper_id)
    except (ZoteroError, ValueError):
        raise ApiError(503, "ZOTERO_UNAVAILABLE", "Zotero에서 삭제하지 못했습니다. 잠시 후 다시 시도해 주세요.") from None
    return Response(status_code=204)
