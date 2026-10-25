"""라이브러리 저장소(repo) 테스트: 가짜 Zotero + 가짜 색인 청크 수. 실제 그룹·색인은 건드리지 않는다."""
import asyncio

import pytest

from app.data import repo
from app.data.providers.zotero import ZoteroError, pick_pdf_attachment
from app.rag import config_rag
from app.rag.errors import ApiError
from zotero_fake import FakeZotero

TEAM = 3
ID = {key: repo.paper_id_from_key(key) for key in ("V3HSB2SA", "263A8NW8", "UPLOAD01", "NOPDF001", "PENDING1", "FAILED01")}


def run(coro):
    return asyncio.run(coro)


def build_library() -> FakeZotero:
    fake = FakeZotero()
    fake.adapter()  # 직접 추가한 논문 V3HSB2SA (arXiv:1902.00751 [cs.LG], PDF 있음)
    fake.items["V3HSB2SA"]["data"].update(dateAdded="2026-10-20T01:00:00Z", tags=[{"tag": "peft"}],
                                          creators=[{"creatorType": "author", "firstName": "Neil", "lastName": "Houlsby"}], date="2019-02-02")
    fake.add("263A8NW8", itemType="preprint", title="RETA-LLM", extra="arXiv: 2306.05212\nReferoom-Version: v1",
             dateAdded="2026-10-24T01:00:00Z", url="https://arxiv.org/abs/2306.05212v1")
    fake.add("4RDQ4ID6", itemType="attachment", parentItem="263A8NW8", linkMode="imported_file", contentType="application/pdf",
             filename="2306.05212v1.pdf", md5="m1")
    fake.add("UPLOAD01", itemType="preprint", title="My Uploaded Paper", extra="Referoom-Upload", dateAdded="2026-10-23T01:00:00Z",
             tags=[{"tag": "lora"}])
    fake.add("UPATT001", itemType="attachment", parentItem="UPLOAD01", linkMode="imported_file", contentType="application/pdf",
             filename="up.pdf", md5="m2")
    fake.add("NOPDF001", itemType="journalArticle", title="No attachment", dateAdded="2026-10-22T01:00:00Z")
    fake.add("PENDING1", itemType="conferencePaper", title="Waiting for sync", dateAdded="2026-10-21T01:00:00Z")
    fake.add("PENATT01", itemType="attachment", parentItem="PENDING1", linkMode="imported_file", contentType="application/pdf",
             filename="p.pdf", md5="m3")
    fake.add("FAILED01", itemType="preprint", title="Broken scan", dateAdded="2026-10-19T01:00:00Z")
    fake.add("FAILATT1", itemType="attachment", parentItem="FAILED01", linkMode="imported_file", contentType="application/pdf",
             filename="f.pdf", md5="m4")
    return fake


@pytest.fixture()
def env(tmp_path, monkeypatch):
    fake = build_library()
    counts = {ID["V3HSB2SA"]: 40, ID["263A8NW8"]: 25, ID["UPLOAD01"]: 12}
    monkeypatch.setattr(config_rag, "LOCAL_INDEX_DIR", tmp_path)
    monkeypatch.setattr(config_rag, "ZOTERO_TEAM_ID", TEAM)
    monkeypatch.setattr(config_rag, "ZOTERO_GROUP_ID", 1)
    monkeypatch.setattr(config_rag, "ZOTERO_API_KEY", "test-key")
    monkeypatch.setattr(config_rag, "ZOTERO_CACHE_SECONDS", 30)
    monkeypatch.setattr(repo, "provider_for", lambda team_id: fake.provider())
    monkeypatch.setattr(repo.store, "paper_chunk_counts", lambda team_id: dict(counts))
    repo.reset_state()
    yield fake, counts
    repo.reset_state()


def by_key(rows):
    return {r["zotero_key"]: r for r in rows}


def test_rows_source_type_and_status(env):
    rows = by_key(run(repo.load_rows(TEAM)))
    assert set(rows) == {"V3HSB2SA", "263A8NW8", "UPLOAD01", "NOPDF001", "PENDING1", "FAILED01"}  # 첨부·메모는 행이 아니다
    assert {k: r["source_type"] for k, r in rows.items()} == {
        "V3HSB2SA": "zotero", "263A8NW8": "web", "UPLOAD01": "pdf", "NOPDF001": "zotero", "PENDING1": "zotero", "FAILED01": "zotero"}
    assert {k: r["status"] for k, r in rows.items()} == {
        "V3HSB2SA": "indexed", "263A8NW8": "indexed", "UPLOAD01": "indexed", "NOPDF001": "failed", "PENDING1": "pending", "FAILED01": "pending"}
    adapter = rows["V3HSB2SA"]
    assert adapter["id"] == ID["V3HSB2SA"] and adapter["chunk_count"] == 40 and adapter["error_msg"] is None
    assert adapter["authors"] == "Neil Houlsby" and adapter["year"] == 2019 and adapter["tags"] == ["peft"]
    assert adapter["arxiv_id"] == "1902.00751" and adapter["attachment_key"] == "8XQJP5SB" and adapter["pdf_md5"] == "abc123"
    assert rows["NOPDF001"]["error_msg"] == "PDF 첨부 없음" and rows["NOPDF001"]["chunk_count"] is None
    assert rows["PENDING1"]["chunk_count"] is None and rows["PENDING1"]["attachment_key"] == "PENATT01"


def test_status_priority_active_failure_and_indexed(env):
    _, counts = env
    repo.set_failure(TEAM, ID["FAILED01"], "텍스트 추출 불가(스캔 PDF)")
    repo.set_failure(TEAM, ID["NOPDF001"], "Zotero 저장 실패")  # PDF가 없어도 구체적인 실패 사유가 우선
    repo.set_failure(TEAM, ID["UPLOAD01"], "오래된 실패 기록")  # 색인돼 있으면 indexed
    repo.set_active(TEAM, ID["PENDING1"], True)
    repo.set_active(TEAM, ID["263A8NW8"], True)  # 다시 색인하는 중이면 indexed여도 pending
    rows = by_key(run(repo.load_rows(TEAM)))
    assert (rows["FAILED01"]["status"], rows["FAILED01"]["error_msg"]) == ("failed", "텍스트 추출 불가(스캔 PDF)")
    assert (rows["NOPDF001"]["status"], rows["NOPDF001"]["error_msg"]) == ("failed", "Zotero 저장 실패")
    assert (rows["UPLOAD01"]["status"], rows["UPLOAD01"]["error_msg"]) == ("indexed", None)
    assert rows["PENDING1"]["status"] == "pending" and rows["263A8NW8"]["status"] == "pending"
    assert rows["263A8NW8"]["chunk_count"] is None
    repo.set_active(TEAM, ID["PENDING1"], False)
    repo.set_failure(TEAM, ID["FAILED01"], None)
    rows = by_key(run(repo.load_rows(TEAM)))
    assert rows["PENDING1"]["status"] == "pending" and rows["FAILED01"]["status"] == "pending" and rows["FAILED01"]["error_msg"] is None
    counts[ID["PENDING1"]] = 7  # 색인이 끝나면 캐시와 무관하게 바로 indexed
    assert by_key(run(repo.load_rows(TEAM)))["PENDING1"]["status"] == "indexed"


def test_rows_newest_first_and_public_view(env):
    rows = run(repo.load_rows(TEAM))
    assert [r["zotero_key"] for r in rows] == ["263A8NW8", "UPLOAD01", "NOPDF001", "PENDING1", "V3HSB2SA", "FAILED01"]
    view = repo.public(rows[0])
    assert not repo.INTERNAL_FIELDS & set(view)
    assert set(view) == {"id", "title", "authors", "year", "source_type", "tags", "status", "chunk_count",
                         "error_msg", "url", "created_at", "added_by"}


def test_list_papers_filters_and_pages(env):
    rows = run(repo.load_rows(TEAM))
    assert repo.list_papers(rows)[0] == 6
    assert [r["zotero_key"] for r in repo.list_papers(rows, q="houlsby")[1]] == ["V3HSB2SA"]  # 저자도 검색
    assert [r["zotero_key"] for r in repo.list_papers(rows, q="RETA")[1]] == ["263A8NW8"]
    assert repo.list_papers(rows, source_type="web")[0] == 1
    assert [r["zotero_key"] for r in repo.list_papers(rows, tag="lora")[1]] == ["UPLOAD01"]
    assert repo.list_papers(rows, status="indexed")[0] == 3 and repo.list_papers(rows, status="failed")[0] == 1
    total, page2 = repo.list_papers(rows, page=2, size=4)
    assert total == 6 and len(page2) == 2
    assert repo.list_papers(rows, page=0, size=0)[1] == rows[:1]  # 잘못된 값은 1로 보정


def test_stats_and_last_synced(env):
    stats = run(repo.stats(TEAM))
    assert stats == {"papers": 6, "indexed": 3, "failed": 1, "chunks": {"pdf": 52, "web": 25, "annotation": 0}, "last_synced_at": None}
    repo.write_sync_state(TEAM, "2026-10-24T05:00:00Z", 15)
    assert repo.read_sync_state(TEAM) == {"last_synced_at": "2026-10-24T05:00:00Z", "library_version": 15}
    assert run(repo.stats(TEAM))["last_synced_at"] == "2026-10-24T05:00:00Z"


def test_sync_state_is_per_team_and_validated(env, tmp_path):
    repo.write_sync_state(TEAM, "t", 1)
    assert repo.read_sync_state(4) == {}
    assert not list(tmp_path.rglob("*.tmp"))
    for bad in (0, -1, "3", True):
        with pytest.raises(ValueError):
            repo.read_sync_state(bad)


def test_not_configured_is_409(monkeypatch):
    repo.reset_state()
    monkeypatch.setattr(config_rag, "ZOTERO_TEAM_ID", TEAM)
    monkeypatch.setattr(config_rag, "ZOTERO_GROUP_ID", 1)
    monkeypatch.setattr(config_rag, "ZOTERO_API_KEY", "test-key")
    with pytest.raises(ApiError) as other_team:
        run(repo.load_rows(4))
    assert (other_team.value.status, other_team.value.code) == (409, "ZOTERO_NOT_CONFIGURED")
    monkeypatch.setattr(config_rag, "ZOTERO_API_KEY", None)
    with pytest.raises(ApiError) as no_key:
        run(repo.stats(TEAM))
    assert no_key.value.code == "ZOTERO_NOT_CONFIGURED"
    monkeypatch.setattr(config_rag, "ZOTERO_API_KEY", "test-key")
    monkeypatch.setattr(config_rag, "ZOTERO_GROUP_ID", None)
    with pytest.raises(ApiError):
        repo.provider_for(TEAM)


def test_cache_invalidate_and_force(env):
    fake, _ = env

    async def go():
        await repo.load_rows(TEAM)
        await repo.load_rows(TEAM)
        await repo.stats(TEAM)
        cached_calls = fake.list_calls
        fake.add("NEWITEM1", itemType="preprint", title="Added in Zotero", dateAdded="2026-10-25T01:00:00Z")
        await repo.load_rows(TEAM)  # 캐시 안이라 새 항목이 안 보인다
        stale = len(await repo.load_rows(TEAM))
        repo.invalidate(TEAM)
        fresh = len(await repo.load_rows(TEAM))
        forced_calls = fake.list_calls
        await repo.load_rows(TEAM, force=True)
        return cached_calls, stale, fresh, forced_calls, fake.list_calls

    cached_calls, stale, fresh, forced_calls, after_force = run(go())
    assert cached_calls == 1 and stale == 6 and fresh == 7
    assert forced_calls == 2 and after_force == 3


def test_cache_expires_after_ttl(env, monkeypatch):
    fake, _ = env
    monkeypatch.setattr(config_rag, "ZOTERO_CACHE_SECONDS", 0)

    async def go():
        await repo.load_rows(TEAM)
        await repo.load_rows(TEAM)

    run(go())
    assert fake.list_calls == 2


class DownProvider:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def list_library(self):
        raise ZoteroError("Zotero 네트워크 요청에 실패했습니다.")


def test_zotero_down_uses_stale_list_or_503(env, monkeypatch):
    first = run(repo.load_rows(TEAM))
    monkeypatch.setattr(repo, "provider_for", lambda team_id: DownProvider())
    assert len(run(repo.load_rows(TEAM, force=True))) == len(first)  # 마지막 성공 목록을 쓴다
    repo.reset_state()
    with pytest.raises(ApiError) as error:
        run(repo.load_rows(TEAM))
    assert (error.value.status, error.value.code) == (503, "ZOTERO_UNAVAILABLE")
    assert "Zotero에 연결하지 못했습니다" in error.value.detail and "test-key" not in error.value.detail


def test_get_row(env):
    assert run(repo.get_row(TEAM, ID["UPLOAD01"]))["title"] == "My Uploaded Paper"
    assert run(repo.get_row(TEAM, 1)) is None


def attachment(key, filename, md5="x"):
    return {"key": key, "data": {"filename": filename, "md5": md5}}


def test_pick_pdf_attachment_prefers_managed_name_and_stored_files():
    manual, managed = attachment("A", "Human - 2019.pdf"), attachment("B", "1902.00751v2.pdf")
    assert pick_pdf_attachment([manual, managed], "1902.00751")["key"] == "B"
    assert pick_pdf_attachment([manual, managed], None)["key"] == "A"
    assert pick_pdf_attachment([manual, managed], "2106.09685")["key"] == "A"
    assert pick_pdf_attachment([attachment("C", "1902.00751v2.pdf", md5=None), manual], "1902.00751")["key"] == "A"  # 업로드 미완료는 제외
    assert pick_pdf_attachment([attachment("D", "x.pdf", md5=None)], "1902.00751") is None
    assert pick_pdf_attachment([], None) is None


def test_strict_load_does_not_fall_back_to_stale_list(env, monkeypatch):
    assert repo.cached_version(TEAM) is None
    run(repo.load_rows(TEAM))
    assert repo.cached_version(TEAM) == 7  # 가짜 서버의 라이브러리 버전
    monkeypatch.setattr(repo, "provider_for", lambda team_id: DownProvider())
    assert run(repo.load_rows(TEAM, force=True))  # 기본은 마지막 목록을 쓴다
    with pytest.raises(ApiError) as error:
        run(repo.load_rows(TEAM, force=True, strict=True))
    assert error.value.status == 503 and error.value.code == "ZOTERO_UNAVAILABLE"
