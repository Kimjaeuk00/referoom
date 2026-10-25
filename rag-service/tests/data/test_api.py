"""데이터 API 테스트: 실제 FastAPI 앱 + 가짜 Zotero·색인·arXiv·임베더. 실제 그룹·모델·네트워크는 쓰지 않는다."""
import time
from types import SimpleNamespace

import httpx
import numpy as np
import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.data import ingest, repo
from app.data.ids import paper_id_from_key
from app.data.providers.arxiv import PaperCandidate
from app.data.routers import upload
from app.rag import config_rag
from app.rag.errors import ApiError
from zotero_fake import SCAN, FakeArxivProvider, FakeStore, FakeZotero, make_pdf

TEAM = 3
PAPER_FIELDS = {"id", "title", "authors", "year", "source_type", "tags", "status", "chunk_count",
                "error_msg", "url", "created_at", "added_by"}


def token(**overrides) -> dict:
    claims = {"iss": "simple-auth-server", "sub": "12", "team_id": TEAM, "role": "member", "view": "rnd",
              "exp": int(time.time()) + 3600, **overrides}
    jwt_token = jwt.encode({k: v for k, v in claims.items() if v is not None}, "test-secret", algorithm="HS256")
    return {"Authorization": f"Bearer {jwt_token}"}


MEMBER, ADMIN = token(), token(sub="1", role="team_admin")
OTHER_TEAM_ADMIN = token(sub="2", team_id=4, role="team_admin")
NO_TEAM = token(team_id=None)


def cand(arxiv_id, title, version="v1"):
    return PaperCandidate(candidate_id=arxiv_id, version=version, title=title, authors=["A. Author"], year=2023,
                          abstract=f"About {title}.", url=f"https://arxiv.org/abs/{arxiv_id}{version}",
                          pdf_url=f"https://arxiv.org/pdf/{arxiv_id}{version}")


CANDIDATES = [cand("2310.11454", "VeRA"), cand("2402.12354", "LoRA Plus"), cand("2001.08361", "Scaling Laws"),
              cand("1902.00751", "Adapter", "v2")]
RELEVANCE = {"VeRA": 0.80, "LoRA Plus": 0.50, "Scaling Laws": 0.30, "Adapter": 0.60}


@pytest.fixture()
def api(tmp_path, monkeypatch):
    fake, store, arxiv = FakeZotero(), FakeStore(), FakeArxivProvider(candidates=list(CANDIDATES))
    monkeypatch.setattr(config_rag, "LOCAL_INDEX_DIR", tmp_path)
    monkeypatch.setattr(config_rag, "STORE_BACKEND", "local")
    monkeypatch.setattr(config_rag, "ZOTERO_TEAM_ID", TEAM)
    monkeypatch.setattr(config_rag, "ZOTERO_GROUP_ID", 6731353)
    monkeypatch.setattr(config_rag, "ZOTERO_API_KEY", "test-key")
    monkeypatch.setattr(config_rag, "TOPIC_MIN_RELEVANCE", 0.45)

    def provider_for(team_id):
        if not repo.is_configured(team_id):  # 실제 코드의 연결 판정을 그대로 쓰고, Zotero 서버만 가짜로 바꾼다
            raise ApiError(409, "ZOTERO_NOT_CONFIGURED", "이 팀은 Zotero 그룹이 연결되지 않았습니다.")
        return fake.provider()

    monkeypatch.setattr(repo, "provider_for", provider_for)
    for name in ("add_paper", "delete_paper", "paper_chunk_counts", "paper_ids_with_meta"):
        monkeypatch.setattr(ingest.store, name, getattr(store, name))
    monkeypatch.setattr(ingest, "ArxivProvider", lambda: arxiv)
    monkeypatch.setattr(upload, "ArxivProvider", lambda: arxiv)

    def embed_documents(texts):
        out = []
        for text in texts:
            score = next(v for title, v in RELEVANCE.items() if text.startswith(title))
            out.append([score, (1 - score**2) ** 0.5])
        return np.array(out)

    monkeypatch.setattr(upload.embedder, "embed_query", lambda topic: np.array([1.0, 0.0]))
    monkeypatch.setattr(upload.embedder, "embed_documents", embed_documents)
    repo.reset_state()
    ingest.reset_state()
    upload.reset_cache()
    with TestClient(app_under_test()) as client:  # with를 써야 요청 사이에 백그라운드 배치가 계속 돈다
        yield SimpleNamespace(client=client, fake=fake, store=store, arxiv=arxiv)
    repo.reset_state()
    ingest.reset_state()
    upload.reset_cache()


def app_under_test():
    from app.main import app

    return app


def seed(api):
    """Adapter(직접 추가, 색인 전) + RETA-LLM(수집, 색인됨) + PDF 첨부 없는 논문."""
    fake = api.fake
    fake.adapter()
    fake.items["V3HSB2SA"]["data"].update(dateAdded="2026-10-20T01:00:00Z", tags=[{"tag": "peft"}])
    fake.files["8XQJP5SB"] = make_pdf()
    fake.add("263A8NW8", itemType="preprint", title="RETA-LLM", extra="arXiv: 2306.05212\nReferoom-Version: v1",
             dateAdded="2026-10-24T01:00:00Z")
    fake.add("4RDQ4ID6", itemType="attachment", parentItem="263A8NW8", linkMode="imported_file",
             contentType="application/pdf", filename="2306.05212v1.pdf", md5="m1")
    fake.add("NOPDF001", itemType="journalArticle", title="No attachment", dateAdded="2026-10-22T01:00:00Z")
    reta = paper_id_from_key("263A8NW8")
    api.store.counts[reta], api.store.metas[reta] = 12, {"zotero_key": "263A8NW8"}


def wait(api, headers, batch_id):
    for _ in range(100):
        body = api.client.get(f"/ingest/batches/{batch_id}", headers=headers).json()
        if body["status"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError("배치가 끝나지 않았습니다")


# ---- 인증·설정 ----
def test_endpoints_require_login_then_team(api):
    calls = [("get", "/papers"), ("get", "/papers/1"), ("delete", "/papers/1"), ("get", "/library/stats"),
             ("get", "/ingest/batches/1"), ("post", "/search-topic"), ("post", "/upload-topic"), ("post", "/upload-paper"),
             ("get", "/zotero/config"), ("post", "/zotero/sync")]
    for method, path in calls:
        no_token = getattr(api.client, method)(path)
        assert (no_token.status_code, no_token.json()["code"]) == (401, "UNAUTHORIZED"), path
        no_team = getattr(api.client, method)(path, headers=NO_TEAM)
        assert (no_team.status_code, no_team.json()["code"]) == (403, "NO_TEAM"), path


def test_not_ready_when_store_is_not_local(api, monkeypatch):
    monkeypatch.setattr(config_rag, "STORE_BACKEND", "stub")
    response = api.client.get("/papers", headers=MEMBER)
    assert (response.status_code, response.json()["code"]) == (503, "NOT_READY")
    assert api.client.get("/papers").status_code == 401  # 인증 오류가 먼저다


def test_other_team_cannot_use_the_zotero_library(api):
    seed(api)
    for path in ("/papers", "/library/stats"):
        response = api.client.get(path, headers=OTHER_TEAM_ADMIN)
        assert (response.status_code, response.json()["code"]) == (409, "ZOTERO_NOT_CONFIGURED")
    assert api.client.get(f"/papers/{paper_id_from_key('263A8NW8')}", headers=OTHER_TEAM_ADMIN).status_code == 409


# ---- 라이브러리 ----
def test_list_papers_contract_and_filters(api):
    seed(api)
    body = api.client.get("/papers", headers=MEMBER).json()
    assert body["total"] == 3 and [i["title"] for i in body["items"]][0] == "RETA-LLM"  # 최근 추가순
    assert all(set(item) == PAPER_FIELDS for item in body["items"])  # zotero_key·arxiv_id 같은 내부 값은 없다
    get = lambda **q: api.client.get("/papers", params=q, headers=MEMBER).json()  # noqa: E731
    assert [i["title"] for i in get(status="indexed")["items"]] == ["RETA-LLM"]
    assert get(status="failed")["total"] == 1 and get(source_type="web")["total"] == 1 and get(tag="peft")["total"] == 1
    assert get(q="고친")["items"][0]["status"] == "pending"
    page = get(page=2, size=2)
    assert page["total"] == 3 and len(page["items"]) == 1
    assert get(size=200)["total"] == 3  # 프론트가 size=200으로 전체 목록을 받는다
    for bad in ({"size": 201}, {"page": 0}, {"status": "nope"}, {"source_type": "x"}):
        response = api.client.get("/papers", params=bad, headers=MEMBER)
        assert (response.status_code, response.json()["code"]) == (422, "VALIDATION_ERROR")


def test_paper_detail_and_stats(api):
    seed(api)
    reta = paper_id_from_key("263A8NW8")
    detail = api.client.get(f"/papers/{reta}", headers=MEMBER)
    assert detail.status_code == 200 and set(detail.json()) == PAPER_FIELDS and detail.json()["chunk_count"] == 12
    missing = api.client.get("/papers/1", headers=MEMBER)
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")
    stats = api.client.get("/library/stats", headers=MEMBER).json()
    assert stats == {"papers": 3, "indexed": 1, "failed": 1, "chunks": {"pdf": 0, "web": 12, "annotation": 0}, "last_synced_at": None}


def test_delete_requires_admin_and_moves_to_zotero_trash(api):
    seed(api)
    reta = paper_id_from_key("263A8NW8")
    denied = api.client.delete(f"/papers/{reta}", headers=MEMBER)
    assert (denied.status_code, denied.json()["code"]) == (403, "FORBIDDEN")
    assert api.store.deleted == [] and "deleted" not in api.fake.items["263A8NW8"]["data"]
    deleted = api.client.delete(f"/papers/{reta}", headers=ADMIN)
    assert deleted.status_code == 204 and deleted.content == b""
    assert api.fake.items["263A8NW8"]["data"]["deleted"] == 1 and api.store.deleted == [reta]
    assert api.client.get(f"/papers/{reta}", headers=MEMBER).status_code == 404
    assert api.client.delete(f"/papers/{reta}", headers=ADMIN).status_code == 404


def test_delete_reports_zotero_failure_and_keeps_index(api):
    seed(api)
    reta = paper_id_from_key("263A8NW8")
    api.client.get("/papers", headers=MEMBER)  # 목록 캐시에 올려 둔다
    del api.fake.items["263A8NW8"]  # 그 사이 Zotero에서 사라진 상황
    response = api.client.delete(f"/papers/{reta}", headers=ADMIN)
    assert (response.status_code, response.json()["code"]) == (503, "ZOTERO_UNAVAILABLE")
    assert api.store.deleted == [] and reta in api.store.counts and "test-key" not in response.text


# ---- 업로드 ----
def test_upload_paper_end_to_end(api):
    pdf = make_pdf()
    accepted = api.client.post("/upload-paper", headers=MEMBER, files={"file": ("my-paper.pdf", pdf, "application/pdf")},
                               data={"tags": "peft, lora, peft"})
    assert accepted.status_code == 202
    body = accepted.json()
    assert body["paper_id"] is None and body["status"] == "pending"
    batch = wait(api, MEMBER, body["batch_id"])
    assert (batch["kind"], batch["status"], batch["indexed"]) == ("upload_pdf", "done", 1)
    listed = api.client.get("/papers", headers=MEMBER).json()["items"][0]
    assert (listed["title"], listed["source_type"], listed["status"], listed["tags"]) == ("my-paper", "pdf", "indexed", ["peft", "lora"])
    assert listed["id"] == batch["papers"][0]["paper_id"]


def test_upload_paper_rejections(api):
    post = lambda name, data, **kw: api.client.post("/upload-paper", headers=MEMBER, files={"file": (name, data, "application/pdf")}, **kw)  # noqa: E731
    cases = [(post("notes.txt", b"hello"), 422, "VALIDATION_ERROR"), (post("fake.pdf", b"not a pdf"), 422, "VALIDATION_ERROR"),
             (post("big.pdf", b"%PDF-" + b"0" * (21 * 1024 * 1024)), 413, "PAYLOAD_TOO_LARGE"), (post("long.pdf", make_pdf(81)), 422, "VALIDATION_ERROR")]
    for response, status, code in cases:
        assert (response.status_code, response.json()["code"]) == (status, code)
    missing = api.client.post("/upload-paper", headers=MEMBER)
    assert (missing.status_code, missing.json()["code"]) == (422, "VALIDATION_ERROR")
    assert api.fake.items == {}  # 거절된 파일은 Zotero에 아무것도 만들지 않는다


def test_upload_paper_duplicate_is_409_with_existing_id(api):
    pdf = make_pdf()
    first = api.client.post("/upload-paper", headers=MEMBER, files={"file": ("a.pdf", pdf, "application/pdf")}).json()
    existing = wait(api, MEMBER, first["batch_id"])["papers"][0]["paper_id"]
    again = api.client.post("/upload-paper", headers=MEMBER, files={"file": ("renamed.pdf", pdf, "application/pdf")})
    assert again.status_code == 409 and again.json() == {"detail": "이미 등록된 논문입니다.", "code": "CONFLICT", "paper_id": existing}


def test_upload_scan_pdf_reports_reason(api):
    batch_id = api.client.post("/upload-paper", headers=MEMBER, files={"file": ("scan.pdf", SCAN, "application/pdf")}).json()["batch_id"]
    batch = wait(api, MEMBER, batch_id)
    assert batch["status"] == "failed" and batch["papers"][0]["error_msg"] == "텍스트 추출 불가(스캔 PDF)"


# ---- 주제 검색·수집 ----
def test_search_topic_ranks_and_flags_candidates(api):
    seed(api)
    response = api.client.post("/search-topic", headers=MEMBER, json={"topic": "  parameter   efficient ", "max_results": 10, "provider": "arxiv"})
    assert response.status_code == 200
    body = response.json()
    assert body["topic"] == "parameter efficient"
    assert [(c["title"], c["relevance"]) for c in body["candidates"]] == [("VeRA", 0.8), ("Adapter", 0.6), ("LoRA Plus", 0.5), ("Scaling Laws", 0.3)]
    flags = {c["title"]: (c["low_relevance"], c["already_in_library"]) for c in body["candidates"]}
    assert flags == {"VeRA": (False, False), "Adapter": (False, True), "LoRA Plus": (False, False), "Scaling Laws": (True, False)}
    assert set(body["candidates"][0]) == {"candidate_id", "title", "authors", "year", "abstract", "url", "pdf_url",
                                         "relevance", "low_relevance", "already_in_library"}
    assert api.arxiv.downloads == [] and api.fake.uploads == []  # 검색은 내려받거나 색인하지 않는다


def test_search_topic_edge_cases(api, monkeypatch):
    seed(api)
    assert api.client.post("/search-topic", headers=MEMBER, json={"topic": "x"}).status_code == 422
    assert api.client.post("/search-topic", headers=MEMBER, json={"topic": "ok", "max_results": 21}).status_code == 422
    api.arxiv.candidates = []
    assert api.client.post("/search-topic", headers=MEMBER, json={"topic": "zzz zzz"}).json()["candidates"] == []
    api.arxiv.search_error = httpx.ConnectError("down")
    down = api.client.post("/search-topic", headers=MEMBER, json={"topic": "lora"})
    assert (down.status_code, down.json()["code"]) == (503, "ARXIV_UNAVAILABLE")
    api.arxiv.search_error, api.arxiv.candidates = None, list(CANDIDATES)
    monkeypatch.setattr(upload.embedder, "embed_query", lambda topic: (_ for _ in ()).throw(OSError("model missing")))
    broken = api.client.post("/search-topic", headers=MEMBER, json={"topic": "lora"})
    assert (broken.status_code, broken.json()["code"]) == (503, "NOT_READY") and "model missing" not in broken.text


def test_upload_topic_collects_only_selected_and_new_papers(api):
    seed(api)
    api.client.post("/search-topic", headers=MEMBER, json={"topic": "peft"})
    accepted = api.client.post("/upload-topic", headers=MEMBER, json={"topic": "peft", "selected": ["2310.11454", "2402.12354", "1902.00751"]})
    assert accepted.status_code == 202 and accepted.json()["requested"] == 2  # 이미 있는 Adapter는 제외
    batch = wait(api, MEMBER, accepted.json()["batch_id"])
    assert (batch["kind"], batch["status"], batch["indexed"], batch["failed"]) == ("topic", "done", 2, 0)
    assert sorted(api.arxiv.downloads) == ["2310.11454", "2402.12354"]
    papers = {p["title"]: p for p in api.client.get("/papers", headers=MEMBER).json()["items"]}
    assert papers["VeRA"]["source_type"] == "web" and papers["VeRA"]["status"] == "indexed"
    assert "Scaling Laws" not in papers  # 고르지 않은 논문은 라이브러리에 없다


def test_upload_topic_validation(api):
    seed(api)
    post = lambda **body: api.client.post("/upload-topic", headers=MEMBER, json={"topic": "peft", **body})  # noqa: E731
    assert post(selected=[]).status_code == 422 and post().status_code == 422
    assert post(selected=[f"2301.{n:05d}" for n in range(11)]).status_code == 422  # 한 번에 최대 10편
    assert api.client.post("/upload-topic", headers=MEMBER, json={"topic": "x", "selected": ["2310.11454"]}).status_code == 422
    api.client.post("/search-topic", headers=MEMBER, json={"topic": "peft"})
    all_known = post(selected=["1902.00751"])
    assert (all_known.status_code, all_known.json()["code"]) == (422, "VALIDATION_ERROR") and "이미" in all_known.json()["detail"]
    unknown = post(selected=["9999.99999"])
    assert unknown.status_code == 422 and "찾을 수 없습니다" in unknown.json()["detail"]


def test_upload_topic_searches_again_when_cache_is_gone(api):
    seed(api)
    assert api.arxiv.searches == []
    accepted = api.client.post("/upload-topic", headers=MEMBER, json={"topic": "peft", "selected": ["2310.11454"]})  # 사전 검색 없이 (재시작 뒤 상황)
    assert accepted.status_code == 202 and api.arxiv.searches == ["peft"]
    assert wait(api, MEMBER, accepted.json()["batch_id"])["indexed"] == 1


def test_upload_topic_cache_expires(api, monkeypatch):
    seed(api)
    monkeypatch.setattr(config_rag, "TOPIC_CACHE_SECONDS", 0)
    api.client.post("/search-topic", headers=MEMBER, json={"topic": "peft"})
    api.client.post("/upload-topic", headers=MEMBER, json={"topic": "peft", "selected": ["2310.11454"]})
    assert len(api.arxiv.searches) == 2  # 보관 시간이 0이면 매번 다시 검색한다


# ---- 배치 ----
def test_batch_is_team_scoped(api):
    batch_id = api.client.post("/upload-paper", headers=MEMBER, files={"file": ("a.pdf", make_pdf(), "application/pdf")}).json()["batch_id"]
    body = wait(api, MEMBER, batch_id)
    assert set(body) == {"id", "kind", "status", "requested", "indexed", "skipped", "failed", "removed", "error_msg", "papers"}
    for headers, batch in ((OTHER_TEAM_ADMIN, batch_id), (MEMBER, 9999)):
        response = api.client.get(f"/ingest/batches/{batch}", headers=headers)
        assert (response.status_code, response.json()["code"]) == (404, "NOT_FOUND")


# ---- Zotero ----
def test_zotero_config_and_sync(api):
    seed(api)
    denied = api.client.get("/zotero/config", headers=MEMBER)
    assert (denied.status_code, denied.json()["code"]) == (403, "FORBIDDEN")
    assert api.client.get("/zotero/config", headers=ADMIN).json() == {"configured": True, "group_id": 6731353, "last_synced_at": None}
    assert api.client.get("/zotero/config", headers=OTHER_TEAM_ADMIN).json() == {"configured": False, "group_id": None, "last_synced_at": None}
    assert api.client.post("/zotero/sync", headers=MEMBER).status_code == 403
    unconfigured = api.client.post("/zotero/sync", headers=OTHER_TEAM_ADMIN)
    assert (unconfigured.status_code, unconfigured.json()["code"]) == (409, "ZOTERO_NOT_CONFIGURED")
    accepted = api.client.post("/zotero/sync", headers=ADMIN)
    assert accepted.status_code == 202
    batch = wait(api, ADMIN, accepted.json()["batch_id"])
    assert (batch["kind"], batch["status"], batch["requested"], batch["indexed"]) == ("zotero_sync", "done", 1, 1)  # 색인 전이던 Adapter만
    synced = api.client.get("/zotero/config", headers=ADMIN).json()["last_synced_at"]
    assert synced and synced.endswith("Z")
    assert api.client.get("/library/stats", headers=MEMBER).json()["last_synced_at"] == synced
    assert api.client.get("/papers", params={"status": "indexed"}, headers=MEMBER).json()["total"] == 2


def test_zotero_config_cannot_be_changed_from_the_api(api):
    for method in ("post", "delete"):
        response = getattr(api.client, method)("/zotero/config", headers=ADMIN, **({"json": {"group_id": 1, "api_key": "k" * 20}} if method == "post" else {}))
        assert (response.status_code, response.json()["code"]) == (405, "NOT_SUPPORTED")
        assert getattr(api.client, method)("/zotero/config", headers=MEMBER).status_code == 403


def test_all_data_endpoints_are_documented(api):
    paths = api.client.get("/openapi.json").json()["paths"]
    expected = {"/papers", "/papers/{paper_id}", "/library/stats", "/upload-paper", "/search-topic", "/upload-topic",
                "/ingest/batches/{batch_id}", "/zotero/config", "/zotero/sync", "/rag-query", "/health"}
    assert expected <= set(paths)


def test_upload_reads_at_most_the_size_limit_plus_one_byte(api, monkeypatch):
    """한도를 넘는 파일을 끝까지 메모리에 올리지 않는다 (거절 결과만 봐서는 구분되지 않는 보호 장치)."""
    from starlette.datastructures import UploadFile

    sizes = []
    original = UploadFile.read

    async def spy(self, size=-1):
        sizes.append(size)
        return await original(self, size)

    monkeypatch.setattr(UploadFile, "read", spy)
    big = b"%PDF-" + b"0" * (21 * 1024 * 1024)
    response = api.client.post("/upload-paper", headers=MEMBER, files={"file": ("big.pdf", big, "application/pdf")})
    assert response.status_code == 413 and sizes == [ingest.MAX_PDF_BYTES + 1]
