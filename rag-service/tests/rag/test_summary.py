"""논문 요약(POST /summary): 섹션 6개, 근거 없는 섹션은 '논문에서 찾을 수 없음'. 가짜 LLM·색인으로 확인한다."""
import re

import pytest

from app.rag import config_rag, summary
from app.rag.deps import CurrentUser
from app.rag.errors import ApiError
from app.rag.prompts import ANSWER_STYLE, SUMMARY_EMPTY_TEXT
from app.rag.schemas import SummaryDraft, SummaryRequest, SummarySectionDraft
from app.rag.store_stub import Hit

USER = CurrentUser(user_id=12, username="tester", role="member", team_id=3)
TITLE = "LoRA: Low-Rank Adaptation of Large Language Models"
KEYS = ["problem", "idea", "method", "result", "limit", "check"]
# 질의 종류별로 다른 쪽을 돌려준다. 'What' 질의 둘(문제·핵심 아이디어)은 같은 쪽이라 중복이 제거된다
PAGES = {"What": [1, 2], "Our": [4, 5], "Experimental": [7, 8], "Limitations": [9], "Implementation": [6], "How": [6]}


def chunk(page):
    return Hit(text=f"본문 {page}쪽", score=0.8, metadata={"paper_id": 41, "source": TITLE, "page": page, "type": "body", "has_math": False})


@pytest.fixture()
def lib(monkeypatch):
    monkeypatch.setattr(summary.store, "paper_chunk_counts", lambda team_id: {41: 12} if team_id == 3 else {})
    queries = []

    def chunks_of_paper(team_id, pid, query, k=4):
        queries.append(query)
        first = query.split()[0]
        return [chunk(p) for p in PAGES[first]][:k]

    monkeypatch.setattr(summary.store, "chunks_of_paper", chunks_of_paper)
    monkeypatch.setattr(summary.store, "lead_chunks", lambda team_id, pid, k=3: [])  # 앞쪽 청크는 아래 별도 시험에서 켠다
    return queries


def sec(key, text, *labels):
    return SummarySectionDraft(key=key, text=text, labels=list(labels))


# 블록 라벨은 쪽 순서: p1=S1 p2=S2 p4=S3 p5=S4 p6=S5 p7=S6 p8=S7 p9=S8
FULL = SummaryDraft(sections=[
    sec("problem", "전체 미세조정은 비용이 크다 [S1].", "S1"),
    sec("idea", "저랭크 행렬만 학습한다.", "S2"),
    sec("method", "- 가중치 고정\n- 행렬 B, A만 학습", "S3", "S4"),
    sec("result", "GLUE에서 비슷한 성능을 낸다.", "S6"),
    sec("limit", "랭크를 정해야 한다.", "S8"),
    sec("check", "적용 위치를 정한다.", "S5"),
])


def prepare(fake_llm, draft=FULL):
    fake_llm.state["structured"][SummaryDraft] = draft


def call(**kw):
    return summary.run(SummaryRequest(paper_id=kw.pop("paper_id", 41), **kw), kw.pop("user", USER))


def test_six_sections_in_order_with_sources(fake_llm, lib):
    prepare(fake_llm)
    r = call()
    assert (r.paper_id, r.title) == (41, TITLE)
    assert [s.key for s in r.sections] == KEYS
    assert [s.title for s in r.sections] == ["문제", "핵심 아이디어", "방법", "결과", "한계", "구현·재현 체크포인트"]
    # sources는 프론트가 읽는 '제목 p.N' 문자열이고, 논문 쪽 순서를 따른다
    assert r.sections[2].sources == [f"{TITLE} p.4", f"{TITLE} p.5"]
    assert all(re.fullmatch(r"(.*)\s+p\.(\d+)", src) for s in r.sections for src in s.sources)
    # 본문에는 [S#] 표시가 남지 않고, 마크다운 줄바꿈은 유지된다
    assert r.sections[0].text == "전체 미세조정은 비용이 크다 ."  # [S1] 표시만 지워진다
    assert r.sections[2].text == "- 가중치 고정\n- 행렬 B, A만 학습"


def test_check_section_and_answer_style_are_single(fake_llm, lib):
    # 관점(dev/rnd)이 없어졌으므로 check 섹션과 답변 스타일은 하나다. 요청에 view가 있어도 무시한다.
    prepare(fake_llm)
    r = call(view="rnd")
    assert r.sections[-1].key == "check" and r.sections[-1].title == "구현·재현 체크포인트"
    system = fake_llm.structured_calls[-1][0]
    assert ANSWER_STYLE in system and "구현·재현 체크포인트" in system


def test_unsupported_sections_say_so(fake_llm, lib):
    draft = SummaryDraft(sections=[
        sec("problem", "근거 라벨이 없는 본문"),                    # 라벨 없음
        sec("idea", "없는 라벨을 인용", "S99"),                       # 이 논문 블록에 없는 라벨
        sec("method", None),                                         # 근거에 없다고 답함
        sec("result", "  ", "S6"),                                   # 본문이 비었다
        sec("limit", "한계 문장", "S99", "S8"),                      # 일부만 유효하면 유효한 근거만 남긴다
    ])                                                               # check는 아예 없다
    prepare(fake_llm, draft)
    r = call()
    assert [s.key for s in r.sections] == KEYS
    for s in (r.sections[0], r.sections[1], r.sections[2], r.sections[3], r.sections[5]):
        assert (s.text, s.sources) == (SUMMARY_EMPTY_TEXT, [])
    assert (r.sections[4].text, r.sections[4].sources) == ("한계 문장", [f"{TITLE} p.9"])


def test_duplicate_key_last_wins_and_unknown_labels_dedupe(fake_llm, lib):
    prepare(fake_llm, SummaryDraft(sections=[sec("problem", "첫 번째", "S1"), sec("problem", "두 번째", "S2", "S2")]))
    s = call().sections[0]
    assert (s.text, s.sources) == ("두 번째", [f"{TITLE} p.2"])


def test_body_is_cleaned_and_capped(fake_llm, lib, monkeypatch):
    monkeypatch.setattr(config_rag, "SUMMARY_TEXT_MAX_CHARS", 30)
    messy = "문장   하나 [S1]\n\n\n\n- 항목  [S2]\n" + "가" * 100
    prepare(fake_llm, SummaryDraft(sections=[sec("problem", messy, "S1")]))
    text = call().sections[0].text
    assert "[S" not in text and "  " not in text and "\n\n\n" not in text and len(text) <= 30


def test_needs_review_only_for_numbers_or_math(fake_llm, lib):
    prepare(fake_llm, SummaryDraft(sections=[sec("result", "GLUE 평균이 87.2다.", "S6")]))
    assert call().needs_review is True
    prepare(fake_llm, SummaryDraft(sections=[sec("idea", "저랭크 행렬만 학습한다.", "S2")]))
    assert call().needs_review is False
    prepare(fake_llm, SummaryDraft(sections=[sec("method", "식 $W = W_0 + BA$ 를 쓴다.", "S3")]))
    assert call().needs_review is True
    prepare(fake_llm, SummaryDraft(sections=[sec("idea", "수치 없음", "S2"), sec("result", "87.2는 근거 없는 섹션의 본문", )]))
    assert call().needs_review is False  # 근거가 없어 버려진 섹션의 숫자는 세지 않는다


# ---- 근거 모으기 ----

def test_evidence_uses_one_query_per_section_and_one_llm_call(fake_llm, lib):
    prepare(fake_llm)
    usage = {}
    summary.run(SummaryRequest(paper_id=41), USER, usage)
    assert len(lib) == 6 and len(fake_llm.structured_calls) == 1 and (usage["in_tok"], usage["out_tok"]) == (100, 20)
    _, user, _ = fake_llm.structured_calls[0]
    # 'What' 질의 둘이 같은 쪽을 돌려줘도 블록은 한 번씩만(쪽 1,2,4,5,6,7,8,9 → S1..S8)
    assert user.count("본문 1쪽") == 1 and "[S8]" in user and "[S9]" not in user and TITLE in user


def test_context_is_capped(fake_llm, lib, monkeypatch):
    monkeypatch.setattr(config_rag, "SUMMARY_CONTEXT_CHARS", 12)
    prepare(fake_llm)
    call()
    _, user, _ = fake_llm.structured_calls[0]
    assert "[S1]" in user and "[S8]" not in user  # 글자 수 상한을 넘는 뒤쪽 블록은 넣지 않는다


# ---- 없는 논문 / 팀 격리 ----

def test_missing_paper_is_404_without_llm(fake_llm, lib):
    for pid in (999, 42):
        with pytest.raises(ApiError) as e:
            call(paper_id=pid)
        assert (e.value.status, e.value.code) == (404, "NOT_FOUND")
    assert fake_llm.structured_calls == [] and lib == []


def test_other_teams_paper_looks_the_same_as_missing(fake_llm, lib):
    other = CurrentUser(user_id=1, username="u", role="member", team_id=4)
    with pytest.raises(ApiError) as e:
        summary.run(SummaryRequest(paper_id=41), other)  # 41은 팀 3의 논문
    assert (e.value.status, e.value.code, e.value.detail) == (404, "NOT_FOUND", "논문을 찾을 수 없습니다.")
    assert fake_llm.structured_calls == []


def test_indexed_but_unreadable_paper_is_404(fake_llm, lib, monkeypatch):
    monkeypatch.setattr(summary.store, "chunks_of_paper", lambda *a, **k: [])
    with pytest.raises(ApiError) as e:
        call()
    assert e.value.status == 404 and fake_llm.structured_calls == []


def test_llm_failure_is_an_error(fake_llm, lib):
    def boom(system, user):
        raise ApiError(503, "UPSTREAM_TIMEOUT", "x")

    fake_llm.state["structured"][SummaryDraft] = boom
    with pytest.raises(ApiError) as e:
        call()
    assert e.value.code == "UPSTREAM_TIMEOUT"


# ---- API ----

def test_api_response_shape_and_token_log(client, auth, fake_llm, lib, access_log):
    prepare(fake_llm)
    r = client.post("/summary", json={"paper_id": 41}, headers={**auth, "X-Request-Id": "req-sum-1"})
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"paper_id", "title", "sections", "needs_review", "latency_ms"}
    assert all(set(s) == {"key", "title", "text", "sources"} for s in data["sections"])
    (rec,) = [x for x in access_log if x["request_id"] == "req-sum-1"]
    assert (rec["path"], rec["status"], rec["team_id"], rec["in_tok"], rec["out_tok"]) == ("/summary", 200, 3, 100, 20)


def test_api_not_found_requires_login_and_validation(client, auth, fake_llm, lib):
    from conftest import make_token
    r = client.post("/summary", json={"paper_id": 999}, headers=auth)
    assert (r.status_code, r.json()["code"]) == (404, "NOT_FOUND")
    r = client.post("/summary", json={"paper_id": 41})
    assert (r.status_code, r.json()["code"]) == (401, "UNAUTHORIZED")
    r = client.post("/summary", json={"paper_id": 41}, headers={"Authorization": f"Bearer {make_token(team_id=None)}"})
    assert (r.status_code, r.json()["code"]) == (403, "NO_TEAM")
    for body in ({"paper_id": "41"}, {"paper_id": True}, {}):
        r = client.post("/summary", json=body, headers=auth)
        assert (r.status_code, r.json()["code"]) == (422, "VALIDATION_ERROR")
    assert fake_llm.structured_calls == []


def test_api_not_ready_is_503(client, auth, fake_llm, monkeypatch):
    from app.rag import router_modes
    monkeypatch.setattr(router_modes.store, "readiness", lambda: {"embedder": False})
    r = client.post("/summary", json={"paper_id": 41}, headers=auth)
    assert (r.status_code, r.json()["code"]) == (503, "NOT_READY")


def test_lead_chunks_are_included_and_deduplicated(fake_llm, lib, monkeypatch):
    asked = {}

    def lead(team_id, pid, k=3):
        asked["k"] = k
        return [chunk(1), chunk(3)]  # 1쪽은 질의 결과와 겹치고, 3쪽은 질의가 가져오지 않는 쪽

    monkeypatch.setattr(summary.store, "lead_chunks", lead)
    prepare(fake_llm)
    call()
    _, user, _ = fake_llm.structured_calls[0]
    assert asked["k"] == config_rag.SUMMARY_LEAD_CHUNKS == 3
    assert user.count("본문 1쪽") == 1 and "본문 3쪽" in user  # 앞쪽 청크가 들어가고 중복은 없다
    assert user.index("본문 1쪽") < user.index("본문 3쪽") < user.index("본문 4쪽")  # 쪽 순서


def test_section_queries_are_sentences():
    from app.rag.prompts import SUMMARY_CHECK, SUMMARY_SECTIONS
    queries = [q for *_, q in [*SUMMARY_SECTIONS, SUMMARY_CHECK]]
    assert all(len(q.split()) >= 6 for q in queries)  # 키워드 나열이 아니라 문장형 질의
