"""색인·배치 실행기: PDF 업로드, arXiv 수집, Zotero 동기화를 백그라운드로 돌려 local_store에 색인한다.

요청은 배치를 만들고 바로 돌아간다(202). 실제 일은 asyncio 작업으로 돌고, 진행 상황은 메모리의 배치(get_batch)로 본다.
- 색인은 모두 local_store.store.add_paper를 스레드풀에서 호출한다 (추출·임베딩이 느려서 이벤트 루프를 막지 않는다)
- 팀마다 한 번에 하나의 배치만 돈다 (임베딩 과부하와 Zotero 쓰기 경합을 막는다)
- 서버를 재시작하면 배치 기록이 사라진다. 색인과 Zotero는 그대로이고 색인 전 논문은 '동기화 필요'로 보인다
- 실패 사유는 repo.set_failure로 목록에도 남긴다. 질문·원고·PDF 내용은 기록하지 않는다
"""
import asyncio
import hashlib
import itertools
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx
from starlette.concurrency import run_in_threadpool

from app.data import repo
from app.data.ids import key_from_paper_id, paper_id_from_key
from app.data.providers.arxiv import ArxivProvider
from app.data.providers.zotero import MAX_PAGES, ZoteroError, page_count
from app.rag.errors import ApiError
from app.rag.local_store import store
from app.rag.local_store.ingest import IngestError

logger = logging.getLogger("rag")

MAX_PDF_BYTES = 20 * 1024 * 1024
_KEEP_BATCHES = 200

_batches: dict[int, dict] = {}
_seq = itertools.count(1)
_tasks: set[asyncio.Task] = set()
_locks: dict[int, asyncio.Lock] = {}


class PdfRejected(ValueError):
    """올릴 수 없는 PDF. 메시지는 사용자에게 그대로 보여 줄 수 있고, status는 HTTP 상태다 (422 | 413)."""

    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


class DuplicateError(Exception):
    """같은 PDF가 이미 라이브러리에 있다."""

    def __init__(self, paper_id: int):
        super().__init__("이미 등록된 논문입니다.")
        self.paper_id = paper_id


async def validate_pdf(data: bytes) -> None:
    """형식·크기·쪽수 검사. 통과하면 None, 아니면 PdfRejected."""
    if not data.startswith(b"%PDF-"):
        raise PdfRejected("PDF 파일만 올릴 수 있습니다.")
    if len(data) > MAX_PDF_BYTES:
        raise PdfRejected("20MB를 넘었습니다.", status=413)
    try:
        pages = await asyncio.to_thread(page_count, data)
    except ValueError as error:
        raise PdfRejected(str(error)) from None
    if pages > MAX_PAGES:
        raise PdfRejected(f"PDF는 최대 {MAX_PAGES}페이지까지 올릴 수 있습니다.")


# ---- 배치 ----
def _lock(team_id: int) -> asyncio.Lock:
    return _locks.setdefault(team_id, asyncio.Lock())


def _new_batch(team_id: int, kind: str, items: list[dict], query: str | None = None) -> dict:
    batch = {"id": next(_seq), "team_id": team_id, "kind": kind, "query": query, "status": "running",
             "items": items, "removed": 0, "error_msg": None}
    _batches[batch["id"]] = batch
    for old in [b["id"] for b in _batches.values() if b["status"] != "running"][: max(0, len(_batches) - _KEEP_BATCHES)]:
        del _batches[old]
    return batch


def _item(title: str, paper_id: int | None = None) -> dict:
    return {"paper_id": paper_id, "title": title, "status": "pending", "chunk_count": None, "error_msg": None}


def _finish(batch: dict) -> None:
    items = batch["items"]
    failed = batch["error_msg"] is not None or (items and all(i["status"] == "failed" for i in items))
    batch["status"] = "failed" if failed else "done"


def batch_view(batch: dict) -> dict:
    items = batch["items"]
    count = lambda status: sum(i["status"] == status for i in items)  # noqa: E731
    return {
        "id": batch["id"], "kind": batch["kind"], "status": batch["status"], "requested": len(items),
        "indexed": count("indexed"), "skipped": count("skipped"), "failed": count("failed"),
        "removed": batch["removed"], "error_msg": batch["error_msg"],
        "papers": [dict(i) for i in items],
    }


def get_batch(team_id: int, batch_id: int) -> dict | None:
    """다른 팀의 배치는 없는 것과 같다."""
    batch = _batches.get(batch_id)
    return batch_view(batch) if batch and batch["team_id"] == team_id else None


def _spawn(coro) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _tasks.add(task)  # 참조를 잡아 두지 않으면 실행 중에 사라질 수 있다
    task.add_done_callback(_tasks.discard)


async def drain() -> None:
    """돌고 있는 배치가 모두 끝날 때까지 기다린다 (테스트·종료용)."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


def reset_state() -> None:
    _batches.clear()
    _locks.clear()


def _message(error: Exception, default: str) -> str:
    """사용자에게 보여 줄 실패 사유. 모르는 오류는 내용을 숨기고 서버 로그에만 남긴다."""
    if isinstance(error, (IngestError, PdfRejected, ZoteroError)):  # 이 메시지들은 키·본문을 담지 않는다
        return str(error)
    if not isinstance(error, httpx.HTTPError):
        logger.error("ingest step failed: %s", type(error).__name__)
    return default


def _fail(team_id: int, item: dict, message: str) -> None:
    item.update(status="failed", error_msg=message)
    if item["paper_id"] is not None:
        repo.set_failure(team_id, item["paper_id"], message)


# ---- 색인 ----
def _meta(title: str, source_type: str, key: str, *, authors: str = "", year: int | None = None, url: str | None = None,
          arxiv_id: str | None = None, version: str | None = None, tags: list[str] | None = None) -> dict:
    meta = {"source": title, "authors": authors, "year": year, "url": url, "arxiv_id": arxiv_id, "version": version,
            "tags": ",".join(tags or []), "source_type": source_type, "zotero_key": key, "license": "unknown"}
    return {k: v for k, v in meta.items() if v not in (None, "")}


async def _index(team_id: int, item: dict, key: str, pdf: bytes, meta: dict) -> None:
    """PDF 한 편을 색인하고 item과 목록 상태에 결과를 남긴다. 실패해도 예외를 던지지 않는다."""
    paper_id = item["paper_id"] = paper_id_from_key(key)
    repo.set_active(team_id, paper_id, True)
    try:
        result = await run_in_threadpool(store.add_paper, team_id, paper_id, pdf, meta, True)
    except Exception as error:  # noqa: BLE001  항목 하나의 실패가 배치 전체를 멈추지 않게 한다
        _fail(team_id, item, _message(error, "색인 실패"))
    else:
        item.update(status="indexed", chunk_count=result["chunk_count"], error_msg=None)
        repo.set_failure(team_id, paper_id, None)
    finally:
        repo.set_active(team_id, paper_id, False)


async def _guard(batch: dict, work) -> None:
    """작업이 예상 밖으로 죽어도 배치가 running으로 남지 않게 한다."""
    try:
        await work
    except Exception as error:  # noqa: BLE001
        logger.error("ingest batch crashed: %s", type(error).__name__)
        batch["error_msg"] = "처리 중 오류가 발생했습니다."
        for item in batch["items"]:
            if item["status"] == "pending":
                item.update(status="failed", error_msg=batch["error_msg"])
    finally:
        _finish(batch)


# ---- PDF 업로드 ----
async def start_upload(team_id: int, filename: str, data: bytes, tags: list[str]) -> int:
    """PDF를 Zotero에 새 논문으로 등록하고 색인한다. 반환: batch_id.

    검사에 걸리면 PdfRejected(422|413), 같은 PDF가 이미 있으면 DuplicateError. 그 뒤 일은 백그라운드로 돈다.
    """
    await validate_pdf(data)
    digest = hashlib.md5(data).hexdigest()  # Zotero가 첨부 파일에 기록하는 md5와 같은 값이다
    duplicate = next((r for r in await repo.load_rows(team_id) if r["pdf_md5"] == digest), None)
    if duplicate:
        raise DuplicateError(duplicate["id"])
    title = Path(filename).name[:-4] if Path(filename).name.lower().endswith(".pdf") else Path(filename).name
    batch = _new_batch(team_id, "upload_pdf", [_item(title)])
    _spawn(_guard(batch, _run_upload(team_id, batch, filename, data, tags)))
    return batch["id"]


async def _run_upload(team_id: int, batch: dict, filename: str, data: bytes, tags: list[str]) -> None:
    item = batch["items"][0]
    async with _lock(team_id):
        try:
            async with repo.provider_for(team_id) as provider:
                saved = await provider.save_pdf(data, filename, tags=tags)
        except Exception as error:  # noqa: BLE001
            _fail(team_id, item, _message(error, "Zotero 저장 실패"))
            return
        repo.invalidate(team_id)  # Zotero에 새 항목이 생겼다
        await _index(team_id, item, saved["paper_key"], data, _meta(item["title"], "pdf", saved["paper_key"], tags=tags))


# ---- arXiv 수집 ----
async def start_topic(team_id: int, topic: str, candidates: list) -> int:
    """사용자가 고른 arXiv 후보를 Zotero에 등록하고 색인한다. 반환: batch_id."""
    batch = _new_batch(team_id, "topic", [_item(c.title) for c in candidates], query=topic)
    _spawn(_guard(batch, _run_topic(team_id, batch, candidates)))
    return batch["id"]


async def _run_topic(team_id: int, batch: dict, candidates: list) -> None:
    arxiv = ArxivProvider()
    async with _lock(team_id):
        try:
            provider_context = repo.provider_for(team_id)
        except ApiError as error:
            batch["error_msg"] = error.detail
            for item in batch["items"]:
                item.update(status="failed", error_msg=error.detail)
            return
        async with provider_context as provider:
            for candidate, item in zip(candidates, batch["items"]):
                try:
                    saved = await provider.save_arxiv_paper(candidate, arxiv)
                except Exception as error:  # noqa: BLE001
                    default = "PDF 다운로드 실패" if isinstance(error, httpx.HTTPError) else "Zotero 저장 실패"
                    _fail(team_id, item, _message(error, default))
                    continue
                repo.invalidate(team_id)
                item["paper_id"] = paper_id_from_key(saved["paper_key"])
                if saved["status"] == "kept":
                    item.update(status="skipped", error_msg="이미 라이브러리에 있습니다.")
                    continue
                meta = _meta(candidate.title, "web", saved["paper_key"], authors=", ".join(candidate.authors), year=candidate.year,
                             url=candidate.url, arxiv_id=candidate.candidate_id, version=candidate.version)
                await _index(team_id, item, saved["paper_key"], saved["pdf"], meta)


# ---- Zotero 동기화 ----
async def start_sync(team_id: int) -> int:
    """Zotero 그룹과 색인을 맞춘다: 색인 전 PDF는 색인하고, Zotero에서 사라진 논문은 색인에서 지운다."""
    running = next((b for b in _batches.values() if b["team_id"] == team_id and b["kind"] == "zotero_sync"
                    and b["status"] == "running"), None)
    if running:  # 버튼을 여러 번 눌러도 동기화 배치는 하나만 돈다
        return running["id"]
    batch = _new_batch(team_id, "zotero_sync", [])
    _spawn(_guard(batch, _run_sync(team_id, batch)))
    return batch["id"]


async def _run_sync(team_id: int, batch: dict) -> None:
    async with _lock(team_id):
        try:
            rows = await repo.load_rows(team_id, force=True, strict=True)  # 오래된 목록으로 동기화하지 않는다
        except ApiError as error:
            batch["error_msg"] = error.detail
            return
        todo = [r for r in rows if r["status"] in ("pending", "failed") and r["attachment_key"]]
        batch["items"] = [_item(r["title"], r["id"]) for r in todo]
        if todo:
            async with repo.provider_for(team_id) as provider:
                for row, item in zip(todo, batch["items"]):
                    try:
                        pdf = await provider.download_pdf(row["attachment_key"])
                        await validate_pdf(pdf)
                    except Exception as error:  # noqa: BLE001
                        _fail(team_id, item, _message(error, "PDF 다운로드 실패"))
                        continue
                    meta = _meta(row["title"], row["source_type"], row["zotero_key"], authors=row["authors"], year=row["year"],
                                 url=row["url"], arxiv_id=row["arxiv_id"], tags=row["tags"])
                    await _index(team_id, item, row["zotero_key"], pdf, meta)
        batch["removed"] = await _remove_orphans(team_id, rows)
        repo.write_sync_state(team_id, datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                              repo.cached_version(team_id) or 0)


async def _remove_orphans(team_id: int, rows: list[dict]) -> int:
    """Zotero에서 사라진 논문을 색인에서 지운다. 반환: 지운 논문 수.

    Zotero 동기화로 색인한 논문(청크에 zotero_key가 있는 것)만 대상이다. 시드처럼 다른 경로로 색인한 논문은 건드리지 않는다.
    Zotero가 논문을 하나도 돌려주지 않는데 색인이 있으면, 일시적 오류일 수 있어 지우지 않는다.
    """
    orphans = await run_in_threadpool(store.paper_ids_with_meta, team_id, "zotero_key") - {r["id"] for r in rows}
    if orphans and not rows:
        logger.warning("zotero returned no papers; skip removing %d indexed papers", len(orphans))
        return 0
    for paper_id in orphans:
        await run_in_threadpool(store.delete_paper, team_id, paper_id)
        repo.set_failure(team_id, paper_id, None)
    return len(orphans)


# ---- 삭제 ----
async def delete_paper(team_id: int, paper_id: int) -> None:
    """논문을 Zotero 휴지통으로 옮기고(복구 가능) 색인에서 지운다.

    Zotero 쪽이 실패하면 색인은 그대로 둔다. 키 형식이 아니면 ValueError, Zotero에 없으면 ZoteroError.
    """
    key = key_from_paper_id(paper_id)
    async with repo.provider_for(team_id) as provider:
        await provider.trash_item(key)
    await run_in_threadpool(store.delete_paper, team_id, paper_id)
    repo.set_failure(team_id, paper_id, None)
    repo.invalidate(team_id)
