import hashlib
from pathlib import Path

import numpy as np
import pytest

from app.rag import config_rag
from app.rag.local_store import embedder, ingest, store
from app.rag.local_store.seed_papers import identify


def fake_vec(text: str) -> np.ndarray:
    """단어 해시 기반의 결정적 가짜 임베딩 (같은 단어가 겹치면 유사)."""
    v = np.zeros(64, dtype=np.float32)
    for w in text.lower().split():
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % 64] += 1
    n = np.linalg.norm(v)
    return v / n if n else v


@pytest.fixture()
def index_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config_rag, "LOCAL_INDEX_DIR", tmp_path)
    monkeypatch.setattr(embedder, "embed_documents", lambda ts: np.array([fake_vec(t) for t in ts]))
    monkeypatch.setattr(embedder, "embed_query", fake_vec)
    store.reload()
    yield tmp_path
    store.reload()


def build(index_dir, texts_by_paper):
    chunks = []
    for pid, (title, pages) in texts_by_paper.items():
        base = {"team_id": 3, "paper_id": pid, "source": title, "type": "body", "tags": "peft", "url": "u"}
        chunks += ingest.chunk_pages(pages, base)
    vectors = embedder.embed_documents([c["text"] for c in chunks])
    return ingest.save_index(index_dir / "3", chunks, vectors, {"team_id": 3})


PAPERS = {
    1: ("LoRA paper", [(1, "lora freezes pretrained weights and trains low rank matrices"),
                       (2, "experiments on gpt3 with many tasks and metrics")]),
    2: ("Prefix paper", [(1, "prefix tuning prepends trainable continuous prompts to every layer")]),
}


def test_identify_seed_filename():
    info = identify("2106.09685v2_lora.pdf")
    assert info["paper_id"] == 4 and info["version"] == "v2" and info["url"].endswith("2106.09685")
    assert identify("unknown.pdf") is None and identify("9999.99999v1_x.pdf") is None


def test_chunks_keep_page_and_do_not_cross_pages():
    pages = [(1, "a " * 400), (2, "b " * 400)]
    chunks = ingest.chunk_pages(pages, {"paper_id": 7, "source": "t"}, chunk_size=200, chunk_overlap=20)
    assert {c["metadata"]["page"] for c in chunks} == {1, 2}
    assert all(set(c["text"].split()) <= {"a"} for c in chunks if c["metadata"]["page"] == 1)
    assert chunks[0]["metadata"]["chunk_id"] == "7:body:0"


def test_math_heuristic():
    assert ingest.has_math("W = W0 + BA, h = Wx, y = h + b") is True
    assert ingest.has_math("rank r = 4 works well") is False  # 기호 1개는 본문으로 본다
    assert ingest.has_math("plain sentence about fine-tuning") is False


def test_clean_text_joins_hyphenated_lines():
    assert ingest.clean_text("param-\neter  efficient\ntuning") == "parameter efficient tuning"


def test_clean_text_expands_ligatures():
    assert ingest.clean_text("preﬁx-tuning and ﬁne-tuning") == "prefix-tuning and fine-tuning"


def test_search_returns_best_chunk_with_contract_metadata(index_dir):
    build(index_dir, PAPERS)
    hits = store.search(3, ["pdf"], "lora low rank matrices", k=2)
    assert hits[0].metadata["source"] == "LoRA paper" and hits[0].metadata["page"] == 1
    assert hits[0].score >= hits[1].score
    assert {"paper_id", "page", "type", "has_math", "url"} <= set(hits[0].metadata)


def test_team_isolation_and_missing_index(index_dir):
    build(index_dir, PAPERS)
    assert store.search(99, ["pdf"], "lora", k=3) == []  # 다른 팀 → 빈 리스트(예외 아님)
    assert store.index_version(99) == 0


def test_source_filter(index_dir):
    build(index_dir, PAPERS)
    assert store.search(3, ["web"], "lora", k=3) == []
    assert store.search(3, ["annotation"], "lora", k=3) == []


def test_paper_ids_tags_and_min_score_filters(index_dir):
    build(index_dir, PAPERS)
    only2 = store.search(3, ["pdf"], "lora low rank", k=5, paper_ids=[2])
    assert only2 and all(h.metadata["paper_id"] == 2 for h in only2)
    assert store.search(3, ["pdf"], "lora", k=5, tags=["nothing"]) == []
    assert store.search(3, ["pdf"], "lora low rank matrices", k=5, min_score=0.99) == []


def test_min_score_keeps_the_boundary_and_drops_below(index_dir):
    build(index_dir, PAPERS)
    top = store.search(3, ["pdf"], "lora low rank", k=1)[0].score
    assert [h.score for h in store.search(3, ["pdf"], "lora low rank", k=1, min_score=top)] == [top]  # 같으면 유지
    assert store.search(3, ["pdf"], "lora low rank", k=1, min_score=top + 1e-6) == []  # 미만이면 제거


def test_chunks_of_paper_and_version(index_dir):
    meta = build(index_dir, PAPERS)
    hits = store.chunks_of_paper(3, 2, "anything", k=4)
    assert hits and all(h.metadata["paper_id"] == 2 for h in hits)
    assert store.index_version(3) == meta["index_version"] == 1
    build(index_dir, PAPERS)  # 다시 쓰면 버전 증가
    store.reload()
    assert store.index_version(3) == 2


def test_readiness_counts_loaded(index_dir):
    build(index_dir, PAPERS)
    store.search(3, ["pdf"], "x", k=1)
    assert store.readiness() == {"embedder": True, "stores_loaded": 1}


SEED = config_rag.SEED_DIR / "2106.09685v2_lora.pdf"


@pytest.mark.skipif(not SEED.exists(), reason="data/seed 에 LoRA PDF가 없음")
def test_real_pdf_pages_are_one_based_and_nonempty():
    pages = ingest.read_pages(SEED)
    assert pages[0][0] == 1 and len(pages) >= 10
    assert any("low-rank" in t.lower() for _, t in pages)


def test_strip_repeated_lines_removes_running_headers_only():
    body = "\n".join(f"sentence {j} of the page" for j in range(8))  # 실제 페이지처럼 가운데 본문이 길다
    pages = [f"My Paper Title\nbody text {i}\n{body}\nmore {i}\n{i}" for i in range(1, 6)]
    out = ingest.strip_repeated_lines(pages)
    assert all("My Paper Title" not in p for p in out)  # 매 쪽 반복되는 머리말
    assert all("sentence 4 of the page" in p for p in out)
    assert all(not p.splitlines()[-1].strip().isdigit() for p in out)  # 쪽번호(숫자만 다른 줄)


def test_find_captions_skips_inline_references():
    page = "results are summarized in\nTable 1. which shows gains\nFigure 2: Accuracy of adapters versus fine-tuning. More text\nTable 3 | Summary of datasets."
    labels = [l for l, _ in ingest.find_captions(page)]
    assert labels == ["Figure 2", "Table 3"]
    assert ingest.find_captions("Fig. 4. Copilot suggestion at the cursor.")[0][0] == "Figure 4"


def test_table_and_math_flags_are_separated():
    table = "20 newsgroups 91.1 92.8 ± 0.1 92.8 ± 0.1 91.7 ± 0.2 airline 84.5 83.6 ± 0.3"
    assert ingest.has_table(table) and not ingest.has_math(table)  # 표의 ±·숫자는 수식이 아니다
    assert ingest.has_math("h = W0 x + ∆W x = W0 x + BA x where B ∈ R")


def test_clean_text_joins_split_decimals():
    assert ingest.clean_text("score 92 .8 and 0 .4%") == "score 92.8 and 0.4%"


# ---- 서비스 적재 경로: add_paper / delete_paper / pdf_path ----
@pytest.fixture()
def service_dirs(index_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(config_rag, "PDF_DIR", tmp_path / "pdfs")

    def fake_parse(data: bytes):
        # PDF 대신 "쪽1|쪽2" 형식 bytes를 쪽 목록으로 쓴다 (추출기 없이 적재 흐름만 시험)
        raw = data.decode().split("|")
        pages = [(i, ingest.clean_text(t)) for i, t in enumerate(raw, start=1) if t.strip()]
        return ingest.ParsedPaper(pages=pages, raw=raw, references=None, page_count=len(raw))

    monkeypatch.setattr(ingest, "parse_pdf", fake_parse)
    return index_dir


def test_add_search_delete_paper(service_dirs):
    r1 = store.add_paper(3, 1, b"lora freezes pretrained weights and trains low rank matrices", {"source": "LoRA"})
    store.add_paper(3, 2, b"prefix tuning prepends trainable continuous prompts|Figure 1: prefix tuning overview", {"source": "Prefix"})
    assert r1["chunk_count"] == 1 and store.index_version(3) == 2
    assert store.search(3, ["pdf"], "lora low rank", k=1)[0].metadata["source"] == "LoRA"
    assert {h.metadata["paper_id"] for h in store.search(3, ["pdf"], "prompts", k=10)} == {1, 2}
    assert store.pdf_path(3, 1) is not None and store.pdf_path(3, 2) is not None

    assert store.delete_paper(3, 1) == 1
    assert {h.metadata["paper_id"] for h in store.search(3, ["pdf"], "lora", k=10)} == {2}
    assert store.pdf_path(3, 1) is None and store.index_version(3) == 3
    assert store.delete_paper(3, 99) == 0


def test_add_paper_duplicate_and_replace(service_dirs):
    store.add_paper(3, 1, b"old text about adapters", {"source": "A"})
    with pytest.raises(store.PaperExistsError):
        store.add_paper(3, 1, b"new text", {"source": "A"})
    store.add_paper(3, 1, b"new text about lora", {"source": "A"}, replace=True)
    texts = [h.text for h in store.search(3, ["pdf"], "text", k=10)]
    assert texts == ["new text about lora"]  # 이전 청크는 남지 않는다


def test_team_isolation_for_index_and_pdf(service_dirs):
    store.add_paper(3, 1, b"team three secret paper", {"source": "T3"})
    assert store.search(4, ["pdf"], "secret", k=5) == []
    assert store.pdf_path(4, 1) is None  # 다른 팀은 같은 paper_id라도 파일이 없다
    with pytest.raises(ValueError):
        store.search(0, ["pdf"], "x")  # 잘못된 team_id는 경로로 쓰지 않는다


def test_add_paper_rejects_mismatched_settings(service_dirs, monkeypatch):
    store.add_paper(3, 1, b"some text", {"source": "A"})
    monkeypatch.setattr(config_rag, "CHUNK_SIZE", 500)
    with pytest.raises(RuntimeError):
        store.add_paper(3, 2, b"other text", {"source": "B"})  # 다른 설정의 청크를 섞지 않는다


def test_add_paper_requires_title(service_dirs):
    with pytest.raises(ValueError):
        store.add_paper(3, 1, b"text", {})


def test_strip_references_keeps_appendix():
    refs = "\n".join(f"[{i}] A. Author. Title. In Proc. 20{10 + i % 9}." for i in range(30))
    pages = ["Intro text", "Results text\nReferences\n" + refs, refs, "A Appendix\nTable 9: extra results 1 2 3"]
    out, span = ingest.strip_references(pages)
    assert span == (2, 3)
    assert out[1] == "Results text" and out[2] == "" and out[3].startswith("A Appendix")


def test_scan_pdf_is_rejected(monkeypatch):
    monkeypatch.setattr(ingest, "read_raw_pages", lambda pdf: ["", " ", "x"])
    with pytest.raises(ingest.IngestError):
        ingest.parse_pdf(b"%PDF")


@pytest.mark.skipif(not SEED.exists(), reason="data/seed 에 LoRA PDF가 없음")
def test_real_pdf_references_removed_appendix_kept():
    parsed = ingest.parse_pdf(SEED.read_bytes())
    assert parsed.references == (13, 16)  # LoRA: 참고문헌 13~16쪽, 17쪽부터 부록
    assert any(p >= 17 for p, _ in parsed.pages)


def test_drop_team_keeps_version_increasing(service_dirs, monkeypatch):
    store.add_paper(3, 1, b"some text", {"source": "A"})
    before = store.index_version(3)
    store.drop_team(3)
    assert store.search(3, ["pdf"], "text") == [] and store.index_version(3) > before
    monkeypatch.setattr(config_rag, "CHUNK_SIZE", 500)  # 비운 뒤에는 설정을 바꿔 다시 만들 수 있다
    store.add_paper(3, 1, b"some text", {"source": "A"})
    assert store.index_version(3) > before + 1


def test_seed_meta_has_authors():
    meta = ingest.seed_meta(Path("2106.09685v2_lora.pdf"))
    assert meta["authors"].startswith("Edward J. Hu") and meta["source"].startswith("LoRA")


def test_add_paper_puts_authors_in_every_chunk(service_dirs):
    store.add_paper(3, 1, b"page one text|page two text", {"source": "A", "authors": "Kim, Lee"})
    assert {h.metadata["authors"] for h in store.search(3, ["pdf"], "text", k=10)} == {"Kim, Lee"}


def test_paper_chunk_counts(index_dir):
    assert store.paper_chunk_counts(3) == {}  # 색인 없음
    meta = build(index_dir, PAPERS)
    counts = store.paper_chunk_counts(3)
    assert set(counts) == {1, 2} and sum(counts.values()) == meta["chunk_count"]
    assert counts[1] == 2 and counts[2] == 1
    assert store.paper_chunk_counts(4) == {}  # 다른 팀은 보이지 않음


def test_paper_ids_with_meta(index_dir):
    chunks = []
    for pid, extra in ((1, {"zotero_key": "ABCD2345"}), (2, {}), (3, {"zotero_key": ""})):
        base = {"team_id": 3, "paper_id": pid, "source": f"p{pid}", "type": "body", "tags": "x", "url": "u", **extra}
        chunks += ingest.chunk_pages([(1, f"text of paper {pid}")], base)
    ingest.save_index(index_dir / "3", chunks, embedder.embed_documents([c["text"] for c in chunks]), {"team_id": 3})
    store.reload()
    assert store.paper_ids_with_meta(3, "zotero_key") == {1}  # 비어 있거나 없는 값은 제외
    assert store.paper_ids_with_meta(3, "nope") == set() and store.paper_ids_with_meta(4, "zotero_key") == set()


def test_lead_chunks_are_the_first_body_chunks_in_document_order(index_dir):
    chunks = []
    for pid, pages in {1: [(1, "title and abstract of paper one"), (2, "method of paper one"), (3, "results of paper one")],
                       2: [(1, "paper two abstract")]}.items():
        chunks += ingest.chunk_pages(pages, {"team_id": 3, "paper_id": pid, "source": f"p{pid}", "type": "body", "tags": "", "url": "u"})
    chunks[1]["metadata"]["kind"] = "caption"  # 캡션은 개요가 아니다
    ingest.save_index(index_dir / "3", chunks, embedder.embed_documents([c["text"] for c in chunks]), {"team_id": 3})
    store.reload()
    lead = store.lead_chunks(3, 1, k=2)
    assert [(h.metadata["paper_id"], h.metadata["page"]) for h in lead] == [(1, 1), (1, 3)]  # 문서 순서, 캡션(2쪽)은 건너뛴다
    assert all(h.score == 1.0 and h.metadata["source"] == "p1" for h in lead)               # 점수는 유사도가 아니라 고정값
    assert [h.metadata["paper_id"] for h in store.lead_chunks(3, 2, k=5)] == [2]            # 다른 논문의 청크는 섞이지 않는다
    assert store.lead_chunks(3, 99) == [] and store.lead_chunks(3, 1, k=0) == []
    assert store.lead_chunks(4, 1) == []                                                     # 다른 팀(색인 없음)


def test_lead_chunks_stub_has_the_same_signature():
    from app.rag import store_stub
    assert len(store_stub.lead_chunks(3, 41, k=3)) == 1 and store_stub.lead_chunks(3, 41, k=0) == []
