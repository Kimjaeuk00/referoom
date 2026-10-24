"""라이브러리 저장소: Zotero 그룹의 논문 목록 + local_store 색인 상태 → 프론트 계약의 논문 행·통계.

논문 목록의 원천은 Zotero다. 별도 카탈로그 파일은 없고 아래 셋을 합쳐 행을 만든다.
- Zotero 항목(제목·저자·태그·PDF 첨부): 팀별 메모리 캐시(ZOTERO_CACHE_SECONDS). 쓰기 뒤에는 invalidate로 비운다
- 색인 상태: local_store 색인의 논문별 청크 수 (매 호출마다 새로 계산하므로 캐시와 무관하게 바로 반영된다)
- 진행 중 작업·최근 실패 사유: 메모리 (ingest가 갱신, 서버를 재시작하면 사라진다)
마지막 동기화 시각만 {LOCAL_INDEX_DIR}/{team_id}/zotero_sync.json에 남긴다.
"""
import json
import logging
import os
import re
import time
from pathlib import Path

import httpx

from app.data.ids import paper_id_from_key
from app.data.providers.zotero import ZoteroError, ZoteroProvider, arxiv_id_of, parse_paper, pick_pdf_attachment
from app.rag import config_rag
from app.rag.errors import ApiError
from app.rag.local_store import store

logger = logging.getLogger("rag")

# 내부에서만 쓰는 필드. 프론트 응답에는 싣지 않는다 (목업의 publicPaper와 같다)
INTERNAL_FIELDS = {"zotero_key", "arxiv_id", "attachment_key", "pdf_md5"}

_cache: dict[int, tuple[float, list[dict], dict[str, list[dict]], int]] = {}
_active: dict[int, set[int]] = {}
_failures: dict[int, dict[int, str]] = {}


# ---- Zotero 연결 ----
def is_configured(team_id: int) -> bool:
    """이 팀에 Zotero 그룹이 연결돼 있는가. 그룹은 ZOTERO_TEAM_ID 한 팀에만 연결된다."""
    return team_id == config_rag.ZOTERO_TEAM_ID and config_rag.ZOTERO_GROUP_ID is not None and bool(config_rag.ZOTERO_API_KEY)


def provider_for(team_id: int) -> ZoteroProvider:
    """팀의 Zotero 연결. 호출 측이 async with로 쓴다. 연결이 없으면 409."""
    if not is_configured(team_id):
        raise ApiError(409, "ZOTERO_NOT_CONFIGURED", "이 팀은 Zotero 그룹이 연결되지 않았습니다.")
    return ZoteroProvider(config_rag.ZOTERO_GROUP_ID, config_rag.ZOTERO_API_KEY)


# ---- 진행 중 작업·실패 사유 (ingest가 갱신) ----
def set_active(team_id: int, paper_id: int, on: bool) -> None:
    jobs = _active.setdefault(team_id, set())
    jobs.add(paper_id) if on else jobs.discard(paper_id)


def set_failure(team_id: int, paper_id: int, message: str | None) -> None:
    """message가 None이면 실패 기록을 지운다."""
    failures = _failures.setdefault(team_id, {})
    if message is None:
        failures.pop(paper_id, None)
    else:
        failures[paper_id] = message


def reset_state(team_id: int | None = None) -> None:
    """캐시와 진행 상태를 비운다 (team_id가 없으면 전체). 테스트와 재시작 정리용."""
    for state in (_cache, _active, _failures):
        state.clear() if team_id is None else state.pop(team_id, None)


def invalidate(team_id: int | None = None) -> None:
    """Zotero 목록 캐시만 비운다. 쓰기(업로드·삭제·등록) 직후에 부른다."""
    _cache.clear() if team_id is None else _cache.pop(team_id, None)


# ---- 마지막 동기화 상태 ----
def _sync_path(team_id: int) -> Path:
    if type(team_id) is not int or team_id <= 0:  # 경로에 쓰이므로 JWT에서 온 양의 정수만 받는다
        raise ValueError("유효한 team_id가 필요합니다.")
    return Path(config_rag.LOCAL_INDEX_DIR) / str(team_id) / "zotero_sync.json"


def read_sync_state(team_id: int) -> dict:
    path = _sync_path(team_id)  # team_id 검증 오류는 아래 except에 삼켜지지 않게 먼저 만든다
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # 파일이 없거나 깨졌으면 아직 동기화한 적 없는 것으로 본다
        return {}


def write_sync_state(team_id: int, last_synced_at: str, library_version: int) -> None:
    path = _sync_path(team_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps({"last_synced_at": last_synced_at, "library_version": library_version}), encoding="utf-8")
    os.replace(tmp, path)


# ---- 행 만들기 ----
def _source_type(extra: str) -> str:
    """pdf: 서비스에서 직접 올림 / web: 서비스가 arXiv에서 수집 / zotero: Zotero 앱에서 추가."""
    lines = extra.splitlines()
    if "Referoom-Upload" in lines:
        return "pdf"
    # 서비스가 붙이는 표기는 'arXiv: ID'(콜론 뒤 공백). Zotero 앱의 'arXiv:ID [분류]'와 구분된다
    if any(line.startswith("Referoom-Version:") or re.fullmatch(r"arXiv: \S+", line) for line in lines):
        return "web"
    return "zotero"


def _row(team_id: int, item: dict, attachments: list[dict], counts: dict[int, int]) -> dict | None:
    paper = parse_paper(item)
    try:
        paper_id = paper_id_from_key(item["key"])
    except ValueError:
        logger.warning("skip zotero item with unexpected key")
        return None
    if paper is None:
        return None
    data = item["data"]
    arxiv_id = arxiv_id_of(data)
    pdf = pick_pdf_attachment(attachments, arxiv_id)
    chunk_count = counts.get(paper_id)
    error = _failures.get(team_id, {}).get(paper_id)
    if paper_id in _active.get(team_id, ()):
        status, error = "pending", None
    elif chunk_count:
        status, error = "indexed", None
    elif error:
        status = "failed"
    elif pdf is None:
        status, error = "failed", "PDF 첨부 없음"
    else:
        status = "pending"  # Zotero에는 있지만 아직 색인 전. 동기화하면 색인된다
    return {
        "id": paper_id,
        "title": paper.title.strip() or "(제목 없음)",
        "authors": ", ".join(paper.authors),
        "year": paper.year,
        "source_type": _source_type(data.get("extra", "")),
        "tags": paper.tags,
        "status": status,
        "chunk_count": chunk_count if status == "indexed" else None,
        "error_msg": error,
        "url": paper.url,
        "created_at": data.get("dateAdded"),
        "added_by": None,  # Zotero 항목에는 서비스 사용자 정보가 없다
        "zotero_key": item["key"],
        "arxiv_id": arxiv_id,
        "attachment_key": pdf["key"] if pdf else None,
        "pdf_md5": pdf["data"].get("md5") if pdf else None,
    }


async def load_rows(team_id: int, force: bool = False, strict: bool = False) -> list[dict]:
    """팀의 논문 행 (최근 추가순). INTERNAL_FIELDS를 포함하므로 응답에는 public()을 거친다.

    Zotero 조회가 실패하면 마지막으로 성공한 목록을 쓰고, 그것도 없으면 503이다.
    strict=True면 마지막 목록을 쓰지 않고 바로 503이다 (동기화처럼 최신 목록이 꼭 필요한 곳).
    """
    cached = _cache.get(team_id)
    if force or cached is None or time.monotonic() - cached[0] >= config_rag.ZOTERO_CACHE_SECONDS:
        try:
            async with provider_for(team_id) as provider:
                papers, attachments, version = await provider.list_library()
            cached = _cache[team_id] = (time.monotonic(), papers, attachments, version)
        except ApiError:
            raise
        except (ZoteroError, httpx.HTTPError, OSError) as error:
            logger.warning("zotero library fetch failed: %s", type(error).__name__)  # 메시지에는 URL이 담길 수 있어 기록하지 않는다
            if cached is None or strict:
                raise ApiError(503, "ZOTERO_UNAVAILABLE", "Zotero에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.") from None
            # 이전 목록을 캐시 시간만큼 더 쓴다. 안 그러면 요청마다 Zotero 재시도 대기가 쌓인다
            cached = _cache[team_id] = (time.monotonic(), *cached[1:])
    _, papers, attachments, _ = cached
    counts = store.paper_chunk_counts(team_id)
    rows = (_row(team_id, item, attachments.get(item["key"], []), counts) for item in papers)
    return sorted((r for r in rows if r), key=lambda r: (r["created_at"] or "", r["id"]), reverse=True)


def cached_version(team_id: int) -> int | None:
    """마지막으로 조회한 Zotero 라이브러리 버전 (조회한 적이 없으면 None)."""
    cached = _cache.get(team_id)
    return cached[3] if cached else None


def public(row: dict) -> dict:
    return {k: v for k, v in row.items() if k not in INTERNAL_FIELDS}


def list_papers(rows: list[dict], *, q: str | None = None, source_type: str | None = None, tag: str | None = None,
                status: str | None = None, page: int = 1, size: int = 20) -> tuple[int, list[dict]]:
    """필터와 페이지를 적용한다. 반환: (필터 후 전체 개수, 이번 페이지 행)."""
    needle = (q or "").strip().lower()
    matched = [
        r for r in rows
        if (not needle or needle in r["title"].lower() or needle in r["authors"].lower())
        and (not source_type or r["source_type"] == source_type)
        and (not tag or tag in r["tags"])
        and (not status or r["status"] == status)
    ]
    page, size = max(1, page), max(1, size)
    return len(matched), matched[(page - 1) * size: page * size]


async def get_row(team_id: int, paper_id: int) -> dict | None:
    return next((r for r in await load_rows(team_id) if r["id"] == paper_id), None)


async def stats(team_id: int) -> dict:
    rows = await load_rows(team_id)
    chunks = {"pdf": 0, "web": 0, "annotation": 0}
    for r in rows:
        if r["status"] == "indexed":
            chunks["web" if r["source_type"] == "web" else "pdf"] += r["chunk_count"] or 0
    return {
        "papers": len(rows),
        "indexed": sum(r["status"] == "indexed" for r in rows),
        "failed": sum(r["status"] == "failed" for r in rows),
        "chunks": chunks,
        "last_synced_at": read_sync_state(team_id).get("last_synced_at"),
    }
