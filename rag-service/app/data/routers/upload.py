"""논문 추가: PDF 업로드와 arXiv 주제 검색·수집. 모두 Zotero에 등록한 뒤 색인하며, 실제 일은 배치로 돈다."""
import logging
import time

import httpx
from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.data import ingest, repo
from app.data.deps import require_library
from app.data.providers.arxiv import ArxivProvider, PaperCandidate
from app.data.schemas import (Candidate, SearchTopicRequest, SearchTopicResponse, UploadPaperResponse,
                              UploadTopicRequest, UploadTopicResponse)
from app.rag import config_rag
from app.rag.deps import CurrentUser
from app.rag.errors import ApiError
from app.rag.local_store import embedder

logger = logging.getLogger("rag")
router = APIRouter(tags=["논문 추가"])

_MAX_TAGS = 20
_MAX_CACHED = 500
# 검색한 후보를 /upload-topic이 다시 쓰도록 잠깐 보관한다: {(team_id, candidate_id): (만료 시각, 후보)}
_candidates: dict[tuple[int, str], tuple[float, PaperCandidate]] = {}


def reset_cache() -> None:
    _candidates.clear()


def _remember(team_id: int, found: list[PaperCandidate]) -> None:
    now = time.monotonic()
    for key in [k for k, (expires, _) in _candidates.items() if expires <= now]:
        del _candidates[key]
    while len(_candidates) + len(found) > _MAX_CACHED and _candidates:
        del _candidates[next(iter(_candidates))]
    for candidate in found:
        _candidates[(team_id, candidate.candidate_id)] = (now + config_rag.TOPIC_CACHE_SECONDS, candidate)


def _recall(team_id: int, candidate_id: str) -> PaperCandidate | None:
    hit = _candidates.get((team_id, candidate_id))
    return hit[1] if hit and hit[0] > time.monotonic() else None


async def _search_arxiv(topic: str, max_results: int) -> list[PaperCandidate]:
    try:
        return await ArxivProvider().search(topic, max_results)
    except (httpx.HTTPError, RuntimeError):
        raise ApiError(503, "ARXIV_UNAVAILABLE", "arXiv에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.") from None
    except ValueError:
        raise ApiError(422, "VALIDATION_ERROR", "주제를 확인해 주세요.") from None


def _relevance(topic: str, found: list[PaperCandidate]) -> list[float]:
    """주제 질의와 '제목. 초록'의 코사인 유사도 (임베딩은 L2 정규화되어 내적과 같다)."""
    query = embedder.embed_query(topic)
    documents = embedder.embed_documents([f"{c.title}. {c.abstract}" for c in found])
    return [float(score) for score in documents @ query]


@router.post("/upload-paper", status_code=202, response_model=UploadPaperResponse, summary="PDF 업로드")
async def upload_paper(file: UploadFile = File(...), tags: str = Form(""), user: CurrentUser = Depends(require_library)):
    name = file.filename or ""
    if not name.lower().endswith(".pdf"):
        raise ApiError(422, "VALIDATION_ERROR", "PDF 파일만 올릴 수 있습니다.")
    data = await file.read(ingest.MAX_PDF_BYTES + 1)  # 한도를 넘는 파일을 끝까지 읽지 않는다
    tag_list = list(dict.fromkeys(t.strip()[:50] for t in tags.split(",") if t.strip()))[:_MAX_TAGS]
    try:
        batch_id = await ingest.start_upload(user.team_id, name, data, tag_list)
    except ingest.PdfRejected as rejected:
        raise ApiError(rejected.status, "PAYLOAD_TOO_LARGE" if rejected.status == 413 else "VALIDATION_ERROR", str(rejected)) from None
    except ingest.DuplicateError as duplicate:
        return JSONResponse(status_code=409, content={"detail": str(duplicate), "code": "CONFLICT", "paper_id": duplicate.paper_id})
    return {"batch_id": batch_id, "paper_id": None, "status": "pending"}


@router.post("/search-topic", response_model=SearchTopicResponse, summary="arXiv 후보 검색 (색인하지 않음)")
async def search_topic(req: SearchTopicRequest, user: CurrentUser = Depends(require_library)) -> dict:
    topic = " ".join(req.topic.split())
    in_library = {r["arxiv_id"] for r in await repo.load_rows(user.team_id) if r["arxiv_id"]}
    found = await _search_arxiv(topic, req.max_results)
    scores: list[float] = []
    if found:
        try:
            scores = await run_in_threadpool(_relevance, topic, found)
        except Exception as error:  # noqa: BLE001  모델 로딩 실패 등
            logger.error("topic relevance failed: %s", type(error).__name__)
            raise ApiError(503, "NOT_READY", "검색 준비 중입니다. 잠시 후 다시 시도해 주세요.") from None
        _remember(user.team_id, found)
    ranked = sorted(zip(found, scores), key=lambda pair: -pair[1])
    return {"topic": topic, "candidates": [
        Candidate(candidate_id=c.candidate_id, title=c.title, authors=c.authors, year=c.year, abstract=c.abstract,
                  url=c.url, pdf_url=c.pdf_url, relevance=round(score, 2), low_relevance=score < config_rag.TOPIC_MIN_RELEVANCE,
                  already_in_library=c.candidate_id in in_library)
        for c, score in ranked]}


@router.post("/upload-topic", status_code=202, response_model=UploadTopicResponse, summary="고른 arXiv 논문 수집")
async def upload_topic(req: UploadTopicRequest, user: CurrentUser = Depends(require_library)) -> dict:
    ids = list(dict.fromkeys(req.selected))
    picked = [_recall(user.team_id, i) for i in ids]
    if None in picked:  # 보관 시간이 지났거나 서버가 재시작된 경우: 같은 주제로 다시 검색해 찾는다
        _remember(user.team_id, await _search_arxiv(" ".join(req.topic.split()), 20))
        picked = [_recall(user.team_id, i) for i in ids]
    if None in picked:
        raise ApiError(422, "VALIDATION_ERROR", "선택한 논문을 찾을 수 없습니다. 다시 검색해 주세요.")
    in_library = {r["arxiv_id"] for r in await repo.load_rows(user.team_id) if r["arxiv_id"]}
    picked = [c for c in picked if c.candidate_id not in in_library]
    if not picked:
        raise ApiError(422, "VALIDATION_ERROR", "선택한 논문이 이미 모두 라이브러리에 있습니다.")
    return {"batch_id": await ingest.start_topic(user.team_id, req.topic.strip(), picked), "requested": len(picked)}
