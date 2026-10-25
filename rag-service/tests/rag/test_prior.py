"""선행연구 모드(mode=prior): 논문별 정리표와 비교 문단. 실제 LLM·색인 없이 가짜로 확인한다."""
import threading

import pytest

from app.rag import config_rag, pipeline, prior
from app.rag.deps import CurrentUser
from app.rag.prompts import PRIOR_EVIDENCE_QUERIES
from app.rag.errors import ApiError
from app.rag.schemas import AnswerDraft, PriorCell, PriorRowDraft, RagRequest
from app.rag.store_stub import Hit

USER = CurrentUser(user_id=12, username="tester", role="member", team_id=3, team_type="dev", view="dev")
TITLES = {41: "LoRA: Low-Rank Adaptation", 42: "QLoRA: Efficient Finetuning", 43: "VeRA: Vector-based Adaptation"}


def req(**kw):
    base = {"question": "파라미터 효율적 미세조정 방법을 비교해줘", "mode": "prior", "scope": {"type": "paper", "ids": [41, 42]}}
    return RagRequest(**{**base, **kw})


def chunk(paper_id, page, text, score=0.8):
    return Hit(text=text, score=score, metadata={"paper_id": paper_id, "source": TITLES[paper_id], "page": page, "type": "body"})


@pytest.fixture()
def lib(monkeypatch):
    """색인이 있는 논문 {41, 42, 43}. 논문마다 쪽 1~3의 청크 3개를 돌려준다."""
    counts = {41: 3, 42: 3, 43: 3}
    monkeypatch.setattr(prior.store, "paper_chunk_counts", lambda team_id: dict(counts))
    monkeypatch.setattr(prior.store, "chunks_of_paper",
                        lambda team_id, pid, query, k=4: [chunk(pid, p, f"{TITLES[pid]} 본문 {p}쪽") for p in (1, 2, 3)][:k])  # 질의와 무관하게 같은 청크(중복 제거 확인)
    monkeypatch.setattr(prior.store, "search", lambda *a, **k: [chunk(41, 1, "a", .9), chunk(42, 2, "b", .8), chunk(41, 3, "c", .7)])
    monkeypatch.setattr(prior.store, "lead_chunks", lambda team_id, pid, k=3: [])  # 앞쪽 청크는 아래 별도 시험에서 켠다
    return counts


def row_draft(**cells):
    """cells: key=(값, 지역 라벨)"""
    return PriorRowDraft(cells=[PriorCell(key=k, value=v, label=lab) for k, (v, lab) in cells.items()])


def prepare(fake_llm, rows: dict, compare=None):
    """rows: {제목 앞부분: PriorRowDraft}. compare: 비교 문단 AnswerDraft."""
    def extract(system, user):
        title = user.split("[논문]\n", 1)[1]
        for prefix, draft in rows.items():
            if title.startswith(prefix):
                if isinstance(draft, Exception):
                    raise draft
                return draft
        raise AssertionError(f"준비하지 않은 논문: {title}")

    fake_llm.state["structured"][PriorRowDraft] = extract
    fake_llm.state["structured"][AnswerDraft] = compare or AnswerDraft(found=True, answer="LoRA는 저랭크 행렬을 학습하고 [S1] QLoRA는 4비트 양자화를 더한다 [S2].", cited=["S1", "S2"])


LORA = row_draft(problem=("전체 미세조정의 비용", "S1"), method=("저랭크 행렬만 학습", "S2"), dataset=("GLUE", "S3"))
QLORA = row_draft(method=("4비트 양자화에 LoRA를 더함", "S1"), result=("65B를 48GB GPU 한 장에서 학습", "S2"))


def test_table_rows_cells_and_global_labels(fake_llm, lib):
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA})
    r = pipeline.run(req(), USER)
    assert r.handoff is False and len(r.table) == 2
    lora, qlora = r.table
    assert (lora["paper_id"], lora["title"]) == (41, TITLES[41])
    # 6칸이 모두 있고, 근거 없는 칸은 null
    for row in r.table:
        assert {"problem", "method", "dataset", "metric", "result", "limitation", "labels"} <= set(row)
    assert lora["metric"] is None and lora["limitation"] is None and "metric" not in lora["labels"]
    assert lora["labels"] == {"problem": "S1", "method": "S2", "dataset": "S3"}
    # 두 번째 논문의 라벨은 첫 논문 뒤에서 이어진다 (전역 라벨 공간)
    assert qlora["labels"] == {"method": "S4", "result": "S5"}
    # 표의 모든 라벨이 source_details에 있고, source_details에는 표에서 쓴 블록만 있다
    used = {lab for row in r.table for lab in row["labels"].values()}
    assert {d.label for d in r.source_details} == used == {"S1", "S2", "S3", "S4", "S5"}
    assert {d.paper_id for d in r.source_details} == {41, 42}


def test_comparison_answer_is_verified_and_counted(fake_llm, lib):
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA})
    usage = {}
    r = pipeline.run(req(), USER, usage)
    assert "[S1]" in r.answer and r.level == "L2" and r.view == "dev"
    assert r.sources and all(" p." in s for s in r.sources)
    # 추출 2회 + 비교 1회, 토큰은 합계
    assert len(fake_llm.structured_calls) == 3
    assert (usage["in_tok"], usage["out_tok"]) == (300, 60)
    # 표에 수치("65B", "48GB")가 있으므로 검토 대상
    assert r.needs_review is True


def test_value_without_valid_label_is_dropped(fake_llm, lib):
    bad = row_draft(problem=("근거 라벨이 없는 값", None), method=("없는 라벨을 인용", "S9"), dataset=("GLUE", "S1"))
    prepare(fake_llm, {"LoRA": bad, "QLoRA": QLORA})
    lora = pipeline.run(req(), USER).table[0]
    assert lora["problem"] is None and lora["method"] is None  # 근거 없는 값은 내보내지 않는다
    assert lora["dataset"] == "GLUE" and lora["labels"] == {"dataset": "S1"}


def test_cell_text_is_cleaned(fake_llm, lib, monkeypatch):
    monkeypatch.setattr(config_rag, "PRIOR_CELL_MAX_CHARS", 20)
    messy = row_draft(method=("저랭크   행렬 [S2]\n만 학습하고 나머지는 고정한다 [S1]", "S1"))
    prepare(fake_llm, {"LoRA": messy, "QLoRA": QLORA})
    method = pipeline.run(req(), USER).table[0]["method"]
    assert "[S" not in method and "  " not in method and len(method) <= 20


def test_one_failed_paper_is_skipped(fake_llm, lib):
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": ApiError(503, "UPSTREAM_TIMEOUT", "x")})
    r = pipeline.run(req(), USER)
    assert [row["paper_id"] for row in r.table] == [41]
    assert "1편은 정리하지 못했어요" in r.answer and r.needs_review is True


def test_all_papers_failed_raises_instead_of_handoff(fake_llm, lib):
    err = ApiError(503, "UPSTREAM_TIMEOUT", "x")
    prepare(fake_llm, {"LoRA": err, "QLoRA": err})
    with pytest.raises(ApiError) as e:
        pipeline.run(req(), USER)
    assert e.value.code == "UPSTREAM_TIMEOUT"


def test_unexpected_extract_error_only_skips_that_paper(fake_llm, lib):
    prepare(fake_llm, {"LoRA": RuntimeError("secret-internal"), "QLoRA": QLORA})
    r = pipeline.run(req(), USER)
    assert [row["paper_id"] for row in r.table] == [42]
    assert "secret-internal" not in r.answer


def test_comparison_failure_keeps_the_table(fake_llm, lib):
    def boom(system, user):
        raise ApiError(500, "INTERNAL_ERROR", "x")

    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA})
    fake_llm.state["structured"][AnswerDraft] = boom
    r = pipeline.run(req(), USER)
    assert len(r.table) == 2 and r.needs_review is True and "정리표로 비교했어요" in r.answer


def test_comparison_not_found_or_bad_citation(fake_llm, lib):
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA}, compare=AnswerDraft(found=False, answer="", cited=[]))
    r = pipeline.run(req(), USER)
    assert len(r.table) == 2 and "정리표로 비교했어요" in r.answer and r.needs_review is True
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA}, compare=AnswerDraft(found=True, answer="없는 근거 [S99]", cited=["S99"]))
    assert pipeline.run(req(), USER).needs_review is True


def test_no_numbers_and_valid_citations_need_no_review(fake_llm, lib):
    plain = row_draft(method=("저랭크 행렬만 학습", "S1"))
    prepare(fake_llm, {"LoRA": plain, "QLoRA": plain}, compare=AnswerDraft(found=True, answer="둘 다 어댑터를 쓴다 [S1] [S2].", cited=["S1", "S2"]))
    assert pipeline.run(req(), USER).needs_review is False


# ---- 근거 없음 / 대상 논문 / 팀 격리 ----

def test_no_evidence_is_handoff_without_llm(fake_llm, lib, monkeypatch):
    monkeypatch.setattr(prior.store, "chunks_of_paper", lambda *a, **k: [])
    r = pipeline.run(req(), USER)
    assert r.handoff is True and r.table is None and r.sources == [] and fake_llm.structured_calls == []


def test_papers_not_in_the_team_index_are_ignored(fake_llm, lib):
    prepare(fake_llm, {"LoRA": LORA})
    r = pipeline.run(req(scope={"type": "paper", "ids": [41, 999, 41]}), USER)  # 999: 이 팀 색인에 없음(다른 팀 논문 포함), 41은 한 번만
    assert [row["paper_id"] for row in r.table] == [41]
    r = pipeline.run(req(scope={"type": "paper", "ids": [999]}), USER)
    assert r.handoff is True and len(fake_llm.structured_calls) == 2  # 앞선 호출(추출 1 + 비교 1)뿐, 두 번째는 호출 없음


def test_only_the_users_team_index_is_asked(fake_llm, lib, monkeypatch):
    asked = []
    monkeypatch.setattr(prior.store, "paper_chunk_counts", lambda team_id: asked.append(team_id) or {41: 1})
    prepare(fake_llm, {"LoRA": LORA})
    pipeline.run(req(scope={"type": "paper", "ids": [41]}), CurrentUser(user_id=1, username="u", role="member", team_id=4, team_type="dev", view="dev"))
    assert asked == [4]


def test_paper_cap(fake_llm, lib, monkeypatch):
    monkeypatch.setattr(config_rag, "PRIOR_MAX_PAPERS", 2)
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA, "VeRA": LORA})
    r = pipeline.run(req(scope={"type": "paper", "ids": [43, 41, 42]}), USER)
    assert [row["paper_id"] for row in r.table] == [43, 41]  # 앞에서부터 상한까지, 입력 순서 유지


def test_scope_all_picks_papers_by_question(fake_llm, lib):
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA})
    r = pipeline.run(req(scope={"type": "all"}), USER)
    assert [row["paper_id"] for row in r.table] == [41, 42]  # 검색 결과의 논문을 중복 없이 순서대로


def test_scope_all_without_hits_is_handoff(fake_llm, lib, monkeypatch):
    monkeypatch.setattr(prior.store, "search", lambda *a, **k: [])
    r = pipeline.run(req(scope={"type": "all"}), USER)
    assert r.handoff is True and fake_llm.structured_calls == []


def test_web_source_has_no_pdf_evidence(fake_llm, lib):
    assert pipeline.run(req(source="web"), USER).handoff is True and fake_llm.structured_calls == []


def test_level_and_view_reach_the_comparison_prompt(fake_llm, lib):
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA})
    pipeline.run(req(level="L1", view="rnd"), USER)
    system = [s for s, _, schema in fake_llm.structured_calls if schema is AnswerDraft][0]
    from app.rag.prompts import LEVEL_RULES, VIEW_RULES
    assert LEVEL_RULES["L1"] in system and VIEW_RULES["rnd"] in system


def test_extraction_gets_each_papers_own_evidence_only(fake_llm, lib):
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA})
    pipeline.run(req(), USER)
    users = {u.split("[논문]\n")[1]: u for _, u, schema in fake_llm.structured_calls if schema is PriorRowDraft}
    assert "QLoRA: Efficient" not in users[TITLES[41]] and TITLES[41] not in users[TITLES[42]]
    assert "[S1]" in users[TITLES[41]]  # 근거 블록은 논문 안에서 S1부터


def test_extraction_runs_in_parallel_threads(fake_llm, lib, monkeypatch):
    monkeypatch.setattr(config_rag, "PRIOR_WORKERS", 2)
    both_started = threading.Barrier(2, timeout=5)  # 두 논문의 추출이 동시에 시작해야 통과한다

    def extract(system, user):
        both_started.wait()
        return LORA

    fake_llm.state["structured"][PriorRowDraft] = extract
    fake_llm.state["structured"][AnswerDraft] = AnswerDraft(found=True, answer="비교 [S1]", cited=["S1"])
    assert len(pipeline.run(req(), USER).table) == 2


# ---- 기존 경로 불변 / API ----

def test_tutor_mode_is_untouched(fake_llm, monkeypatch):
    monkeypatch.setattr(pipeline.store, "search", lambda *a, **k: [chunk(41, 1, "LoRA freezes the weights.")])
    r = pipeline.run(RagRequest(question="LoRA란?"), USER)
    assert r.table is None and len(fake_llm.calls) == 1 and fake_llm.structured_calls == []


def test_api_returns_table_and_records_tokens(client, auth, fake_llm, lib):
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA})
    body = {"question": "비교해줘", "mode": "prior", "scope": {"type": "paper", "ids": [41, 42]}}
    r = client.post("/rag-query", json=body, headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert {"answer", "sources", "source_details", "needs_review", "handoff", "level", "view", "latency_ms", "table"} == set(data)
    assert data["table"][0]["labels"]["method"] == "S2"
    # 튜터 요청에는 table 키가 없다
    tutor = client.post("/rag-query", json={"question": "LoRA란?"}, headers=auth).json()
    assert "table" not in tutor


# ---- 근거 모으기: 앞쪽(제목·초록·서론) + 문장형 질의 ----

def test_lead_chunks_come_first_and_count_against_the_budget(fake_llm, lib, monkeypatch):
    asked = {}

    def lead(team_id, pid, k=3):
        asked["k"] = k
        return [chunk(pid, 1, f"{TITLES[pid]} 초록"), chunk(pid, 1, f"{TITLES[pid]} 서론")][:k]

    queries = []

    def by_query(team_id, pid, query, k=4):
        queries.append((query, k))
        return [chunk(pid, 1, f"{TITLES[pid]} 초록"), chunk(pid, 5, f"{TITLES[pid]} 5쪽 {query[:4]}"), chunk(pid, 6, f"{TITLES[pid]} 6쪽 {query[:4]}")][:k]

    monkeypatch.setattr(prior.store, "lead_chunks", lead)
    monkeypatch.setattr(prior.store, "chunks_of_paper", by_query)
    monkeypatch.setattr(config_rag, "PRIOR_CHUNKS_PER_PAPER", 5)
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA})
    pipeline.run(req(scope={"type": "paper", "ids": [41]}), USER)
    _, user, _ = [c for c in fake_llm.structured_calls if c[2] is PriorRowDraft][0]
    assert asked["k"] == config_rag.PRIOR_LEAD_CHUNKS == 3 and "초록" in user and "서론" in user
    assert user.count("초록") == 1                                  # 질의 결과에 같은 청크가 또 나와도 한 번만
    assert [q for q, _ in queries] == list(PRIOR_EVIDENCE_QUERIES)  # 방법·결과·한계 질의가 각각 한 번씩
    assert all(k == 3 for _, k in queries)                           # 남은 자리(5 − 앞쪽 2)만큼만 질의에서 가져온다


def test_evidence_queries_are_sentences_not_keyword_lists():
    # 키워드를 나열한 질의는 임베딩에서 잘 맞지 않았다(실제 논문 3편으로 확인). 문장형으로 유지한다
    assert len(PRIOR_EVIDENCE_QUERIES) == 3
    assert all(len(q.split()) >= 6 for q in PRIOR_EVIDENCE_QUERIES)


def test_grouped_citations_are_split_in_the_comparison(fake_llm, lib):
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA}, compare=AnswerDraft(found=True, answer="두 방법은 닮았다 [S1, S2]. 차이도 있다 [S4,S5].", cited=["S1", "S2"]))
    r = pipeline.run(req(), USER)
    assert "[S1] [S2]" in r.answer and "[S4] [S5]" in r.answer and "[S1, S2]" not in r.answer


def test_extraction_is_deterministic_but_the_comparison_is_not(fake_llm, lib):
    prepare(fake_llm, {"LoRA": LORA, "QLoRA": QLORA})
    pipeline.run(req(), USER)
    by_schema = {s.__name__: t for (_, _, s), t in zip(fake_llm.structured_calls, fake_llm.structured_temps)}
    assert by_schema == {"PriorRowDraft": config_rag.EXTRACT_TEMPERATURE, "AnswerDraft": None}  # 정리표 추출은 고정, 비교 문단은 기본값
