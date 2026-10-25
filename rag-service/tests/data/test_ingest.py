"""색인·배치 실행기(ingest) 테스트. 가짜 Zotero 서버·가짜 색인 저장소·가짜 arXiv만 쓴다 (실제 그룹·모델 사용 안 함)."""
import asyncio

import httpx
import pytest

from app.data import ingest, repo
from app.data.ids import paper_id_from_key
from app.data.providers.arxiv import PaperCandidate
from app.data.providers.zotero import ZoteroError
from app.rag import config_rag
from app.rag.errors import ApiError
from zotero_fake import SCAN, FakeArxivProvider, FakeStore, FakeZotero, make_pdf

TEAM = 3
REAL_PROVIDER_FOR = repo.provider_for


@pytest.fixture()
def env(tmp_path, monkeypatch):
    fake, fake_store, arxiv = FakeZotero(), FakeStore(), FakeArxivProvider()
    monkeypatch.setattr(config_rag, "LOCAL_INDEX_DIR", tmp_path)
    monkeypatch.setattr(config_rag, "ZOTERO_TEAM_ID", TEAM)
    monkeypatch.setattr(config_rag, "ZOTERO_GROUP_ID", 1)
    monkeypatch.setattr(config_rag, "ZOTERO_API_KEY", "test-key")
    monkeypatch.setattr(repo, "provider_for", lambda team_id: fake.provider())
    for name in ("add_paper", "delete_paper", "paper_chunk_counts", "paper_ids_with_meta"):
        monkeypatch.setattr(ingest.store, name, getattr(fake_store, name))
    monkeypatch.setattr(ingest, "ArxivProvider", lambda: arxiv)
    repo.reset_state()
    ingest.reset_state()
    yield fake, fake_store, arxiv
    repo.reset_state()
    ingest.reset_state()


def run(coro):
    return asyncio.run(coro)


def candidate(arxiv_id="2306.05212", version="v1", title="RETA-LLM"):
    return PaperCandidate(candidate_id=arxiv_id, version=version, title=title, authors=["A. Author", "B. Author"], year=2023,
                          abstract="Abstract", url=f"https://arxiv.org/abs/{arxiv_id}{version}",
                          pdf_url=f"https://arxiv.org/pdf/{arxiv_id}{version}")


async def finish(batch_id):
    await ingest.drain()
    return ingest.get_batch(TEAM, batch_id)


# ---- 업로드 ----
def test_upload_registers_in_zotero_and_indexes(env):
    fake, store, _ = env
    pdf = make_pdf()

    async def go():
        batch_id = await ingest.start_upload(TEAM, "my-paper.pdf", pdf, ["peft"])
        before = ingest.get_batch(TEAM, batch_id)
        view = await finish(batch_id)
        return before, view, await repo.load_rows(TEAM)

    before, view, rows = run(go())
    assert before["status"] == "running" and before["papers"][0]["status"] == "pending"  # 요청은 바로 돌아온다
    item = view["papers"][0]
    assert (view["status"], view["requested"], view["indexed"], view["failed"]) == ("done", 1, 1, 0)
    assert item["status"] == "indexed" and item["chunk_count"] == 3 and item["title"] == "my-paper"
    zotero_item = next(i for i in fake.items.values() if i["data"].get("extra") == "Referoom-Upload")
    assert paper_id_from_key(zotero_item["key"]) == item["paper_id"]
    meta = store.metas[item["paper_id"]]
    assert (meta["source"], meta["source_type"], meta["tags"], meta["zotero_key"]) == ("my-paper", "pdf", "peft", zotero_item["key"])
    assert store.calls == [(TEAM, item["paper_id"], True)]
    assert [(r["status"], r["source_type"], r["chunk_count"]) for r in rows] == [("indexed", "pdf", 3)]


def test_upload_validation_and_duplicate(env):
    async def go():
        for data, status, text in ((b"hello", 422, "PDF 파일만"), (b"%PDF-" + b"0" * (21 * 1024 * 1024), 413, "20MB"),
                                   (make_pdf(81), 422, "80페이지"), (b"%PDF-1.4 broken", 422, "읽을 수 없습니다")):
            with pytest.raises(ingest.PdfRejected) as rejected:
                await ingest.start_upload(TEAM, "a.pdf", data, [])
            assert rejected.value.status == status and text in str(rejected.value)
        first = await finish(await ingest.start_upload(TEAM, "a.pdf", make_pdf(), []))
        with pytest.raises(ingest.DuplicateError) as duplicate:
            await ingest.start_upload(TEAM, "same-content-other-name.pdf", make_pdf(), [])
        return first, duplicate.value

    first, duplicate = run(go())
    assert duplicate.paper_id == first["papers"][0]["paper_id"]


def test_upload_scan_pdf_fails_with_reason_but_stays_in_zotero(env):
    fake, store, _ = env

    async def go():
        view = await finish(await ingest.start_upload(TEAM, "scan.pdf", SCAN, []))
        return view, await repo.load_rows(TEAM)

    view, rows = run(go())
    assert (view["status"], view["failed"]) == ("failed", 1)
    assert view["papers"][0]["error_msg"] == "텍스트 추출 불가(스캔 PDF)"
    assert [(r["status"], r["error_msg"]) for r in rows] == [("failed", "텍스트 추출 불가(스캔 PDF)")]  # 목록에도 사유가 보인다
    assert any(i["data"].get("extra") == "Referoom-Upload" for i in fake.items.values())


def test_upload_zotero_failure_is_reported_and_nothing_is_indexed(env):
    fake, store, _ = env
    fake.storage_fail = True

    async def go():
        return await finish(await ingest.start_upload(TEAM, "x.pdf", make_pdf(), []))

    view = run(go())
    assert view["status"] == "failed" and "저장소" in view["papers"][0]["error_msg"] and "test-key" not in str(view)
    assert store.calls == []


# ---- arXiv 수집 ----
def test_topic_registers_indexes_and_skips_existing(env):
    fake, store, arxiv = env
    fake.adapter()  # Zotero 앱에서 직접 넣은 논문 (PDF 있음) -> kept

    async def go():
        batch_id = await ingest.start_topic(TEAM, "peft", [candidate("1902.00751", "v2", "Adapter"), candidate()])
        return await finish(batch_id)

    view = run(go())
    assert (view["status"], view["requested"], view["indexed"], view["skipped"], view["failed"]) == ("done", 2, 1, 1, 0)
    skipped, indexed = view["papers"]
    assert skipped["status"] == "skipped" and skipped["paper_id"] == paper_id_from_key("V3HSB2SA")
    assert skipped["error_msg"] == "이미 라이브러리에 있습니다."
    meta = store.metas[indexed["paper_id"]]
    assert (meta["source_type"], meta["arxiv_id"], meta["version"], meta["year"]) == ("web", "2306.05212", "v1", 2023)
    assert meta["authors"] == "A. Author, B. Author" and meta["url"].startswith("https://arxiv.org/abs/2306.05212")
    assert arxiv.downloads == ["2306.05212"]  # 이미 있는 논문은 다시 받지 않는다
    assert [c[1] for c in store.calls] == [indexed["paper_id"]]


def test_topic_download_failure_is_reported(env):
    fake, store, arxiv = env
    arxiv.error = httpx.ConnectError("boom")

    async def go():
        return await finish(await ingest.start_topic(TEAM, "peft", [candidate(), candidate("2106.09685", "v2", "LoRA")]))

    view = run(go())
    assert (view["status"], view["failed"]) == ("failed", 2)
    assert {p["error_msg"] for p in view["papers"]} == {"PDF 다운로드 실패"} and store.calls == []


def test_topic_for_unconfigured_team_fails_cleanly(env, monkeypatch):
    monkeypatch.setattr(repo, "provider_for", REAL_PROVIDER_FOR)

    async def go():
        batch_id = await ingest.start_topic(4, "peft", [candidate()])
        await ingest.drain()
        return ingest.get_batch(4, batch_id)

    view = run(go())
    assert view["status"] == "failed" and "연결되지 않았습니다" in view["error_msg"]
    assert view["papers"][0]["status"] == "failed"


# ---- 동기화 ----
def seed_zotero(fake):
    fake.adapter()
    fake.files["8XQJP5SB"] = make_pdf()
    fake.add("263A8NW8", itemType="preprint", title="RETA-LLM", extra="arXiv: 2306.05212\nReferoom-Version: v1")
    fake.add("4RDQ4ID6", itemType="attachment", parentItem="263A8NW8", linkMode="imported_file", contentType="application/pdf",
             filename="2306.05212v1.pdf", md5="m1")
    fake.files["4RDQ4ID6"] = make_pdf()
    fake.add("NOPDF001", itemType="journalArticle", title="No attachment")


def test_sync_indexes_only_unindexed_papers_and_records_time(env):
    fake, store, _ = env
    seed_zotero(fake)
    reta = paper_id_from_key("263A8NW8")
    store.counts[reta], store.metas[reta] = 9, {"zotero_key": "263A8NW8"}  # 이미 색인된 논문

    async def go():
        view = await finish(await ingest.start_sync(TEAM))
        return view, await repo.load_rows(TEAM)

    view, rows = run(go())
    adapter = paper_id_from_key("V3HSB2SA")
    assert (view["kind"], view["status"], view["requested"], view["indexed"], view["removed"]) == ("zotero_sync", "done", 1, 1, 0)
    assert view["papers"][0]["paper_id"] == adapter and store.calls == [(TEAM, adapter, True)]
    meta = store.metas[adapter]
    assert (meta["source_type"], meta["arxiv_id"], meta["zotero_key"]) == ("zotero", "1902.00751", "V3HSB2SA")
    assert {r["zotero_key"]: r["status"] for r in rows} == {"V3HSB2SA": "indexed", "263A8NW8": "indexed", "NOPDF001": "failed"}
    state = repo.read_sync_state(TEAM)
    assert state["last_synced_at"].endswith("Z") and state["library_version"] == 7


def test_sync_removes_only_zotero_indexed_orphans(env):
    fake, store, _ = env
    seed_zotero(fake)
    for pid, meta in ((4, {}), (paper_id_from_key("GONE0001"), {"zotero_key": "GONE0001"})):  # 4: 예전 시드, GONE: Zotero에서 지운 논문
        store.counts[pid], store.metas[pid] = 5, meta

    async def go():
        return await finish(await ingest.start_sync(TEAM))

    view = run(go())
    assert view["removed"] == 1 and store.deleted == [paper_id_from_key("GONE0001")]
    assert 4 in store.counts  # zotero_key가 없는 기존 색인은 건드리지 않는다


def test_sync_does_not_wipe_index_when_zotero_returns_nothing(env):
    fake, store, _ = env  # 비어 있는 라이브러리
    pid = paper_id_from_key("GONE0001")
    store.counts[pid], store.metas[pid] = 5, {"zotero_key": "GONE0001"}

    async def go():
        return await finish(await ingest.start_sync(TEAM))

    view = run(go())
    assert (view["status"], view["removed"]) == ("done", 0) and store.deleted == [] and pid in store.counts


class DownProvider:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def list_library(self):
        raise ZoteroError("Zotero 네트워크 요청에 실패했습니다.")


def test_sync_fails_without_touching_state_when_zotero_is_down(env, monkeypatch):
    fake, store, _ = env
    seed_zotero(fake)

    async def go():
        await repo.load_rows(TEAM)  # 마지막 성공 목록이 캐시에 있어도 동기화는 그것을 쓰지 않는다
        monkeypatch.setattr(repo, "provider_for", lambda team_id: DownProvider())
        return await finish(await ingest.start_sync(TEAM))

    view = run(go())
    assert view["status"] == "failed" and "Zotero에 연결하지 못했습니다" in view["error_msg"]
    assert store.calls == [] and repo.read_sync_state(TEAM) == {}


def test_sync_retries_failed_papers(env):
    fake, store, _ = env
    seed_zotero(fake)
    fake.files["8XQJP5SB"] = SCAN

    async def go():
        first = await finish(await ingest.start_sync(TEAM))
        rows_after_first = await repo.load_rows(TEAM)
        store.reject_scans = False  # 스캔 PDF를 고쳤다고 치고 다시 동기화
        second = await finish(await ingest.start_sync(TEAM))
        return first, rows_after_first, second

    first, rows_after_first, second = run(go())
    assert first["failed"] == 1 and first["indexed"] == 1 and first["status"] == "done"
    adapter = next(r for r in rows_after_first if r["zotero_key"] == "V3HSB2SA")
    assert (adapter["status"], adapter["error_msg"]) == ("failed", "텍스트 추출 불가(스캔 PDF)")
    assert (second["requested"], second["indexed"]) == (1, 1)  # 실패한 것만 다시 시도한다


# ---- 삭제·배치 ----
def test_delete_moves_to_zotero_trash_and_removes_index(env):
    fake, store, _ = env
    seed_zotero(fake)
    pid = paper_id_from_key("263A8NW8")
    store.counts[pid], store.metas[pid] = 9, {"zotero_key": "263A8NW8"}

    async def go():
        await repo.load_rows(TEAM)
        await ingest.delete_paper(TEAM, pid)
        return await repo.load_rows(TEAM)

    rows = run(go())
    assert fake.items["263A8NW8"]["data"]["deleted"] == 1 and store.deleted == [pid]
    assert "263A8NW8" not in {r["zotero_key"] for r in rows}  # 캐시가 비워져 바로 사라진다


def test_delete_keeps_index_when_zotero_fails(env):
    fake, store, _ = env
    pid = paper_id_from_key("MISSING1")
    store.counts[pid] = 4

    async def go():
        await ingest.delete_paper(TEAM, pid)

    with pytest.raises(ZoteroError):
        run(go())
    assert store.deleted == [] and pid in store.counts
    with pytest.raises(ValueError):
        run(ingest.delete_paper(TEAM, 0))


def test_batches_are_team_scoped_and_have_contract_shape(env):
    async def go():
        batch_id = await ingest.start_upload(TEAM, "a.pdf", make_pdf(), [])
        view = await finish(batch_id)
        return batch_id, view

    batch_id, view = run(go())
    assert set(view) == {"id", "kind", "status", "requested", "indexed", "skipped", "failed", "removed", "error_msg", "papers"}
    assert set(view["papers"][0]) == {"paper_id", "title", "status", "chunk_count", "error_msg"}
    assert ingest.get_batch(4, batch_id) is None and ingest.get_batch(TEAM, 999) is None


def test_team_runs_one_batch_at_a_time(env):
    fake, store, _ = env

    async def go():
        ids = [await ingest.start_upload(TEAM, f"p{n}.pdf", make_pdf(n + 3), []) for n in range(3)]
        await ingest.drain()
        return [ingest.get_batch(TEAM, i)["status"] for i in ids]

    assert run(go()) == ["done", "done", "done"]
    assert len(store.calls) == 3 and store.max_running == 1
