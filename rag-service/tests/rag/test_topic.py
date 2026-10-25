"""주제 모드(POST /topic-suggest): 한계 추출 → 후보 제안 → 유사 연구. 실제 LLM·색인 없이 가짜로 확인한다."""
import json

import pytest

from app.rag import config_rag, topic
from app.rag.deps import CurrentUser
from app.rag.errors import ApiError
from app.rag.schemas import LimitationDraft, LimitationItem, TopicDraft, TopicDraftItem, TopicRequest
from app.rag.store_stub import Hit

USER = CurrentUser(user_id=12, username="tester", role="member", team_id=3, team_type="dev", view="dev")
TITLES = {41: "LoRA: Low-Rank Adaptation", 42: "QLoRA: Efficient Finetuning", 43: "VeRA: Vector-based Adaptation", 77: "DoRA: Weight-Decomposed"}


def req(**kw):
    return TopicRequest(**{"paper_ids": [41, 42], **kw})


def chunk(pid, page, text="본문", score=0.8):
    return Hit(text=text, score=score, metadata={"paper_id": pid, "source": TITLES[pid], "page": page, "type": "body"})


@pytest.fixture()
def lib(monkeypatch):
    """색인이 있는 논문 {41, 42, 43, 77}. 논문마다 쪽 1~3의 청크를 돌려주고, 검색은 유사한 논문 43·77을 돌려준다."""
    monkeypatch.setattr(topic.store, "paper_chunk_counts", lambda team_id: {41: 3, 42: 3, 43: 3, 77: 3})
    monkeypatch.setattr(topic.store, "chunks_of_paper",
                        lambda team_id, pid, query, k=4: [chunk(pid, p, f"{TITLES[pid]} {p}쪽") for p in (1, 2, 3)][:k])
    calls = []

    def search(team_id, sources, query, k=5, paper_ids=None, tags=None, min_score=None):
        calls.append({"team_id": team_id, "sources": sources, "query": query, "k": k, "min_score": min_score})
        return [chunk(41, 1, score=.95), chunk(43, 2, score=.72), chunk(43, 3, score=.81), chunk(77, 1, score=.66)]

    monkeypatch.setattr(topic.store, "search", search)
    return calls


def limits(*items):
    return LimitationDraft(items=[LimitationItem(summary=s, label=lab) for s, lab in items])


def item(perspective, based_on, title=None, **kw):
    return TopicDraftItem(perspective=perspective, title=title or f"{perspective} 주제", question=f"{perspective} 질문?", approach=f"{perspective} 접근",
                          datasets=kw.get("datasets", ["GLUE"]), baselines=kw.get("baselines", ["LoRA"]), metrics=kw.get("metrics", ["평균"]), based_on=based_on)


FOUR = [item("limitation_fix", ["S1"]), item("combine", ["S1", "S2"]), item("extend", ["S2"]), item("efficiency", ["S3"])]


def prepare(fake_llm, lim=None, topics=None):
    def extract(system, user):
        title = user.split("[논문]\n", 1)[1]
        out = (lim or {}).get(title.split(":")[0], limits((f"{title.split(':')[0]}의 한계", "S1"), (f"{title.split(':')[0]}의 두 번째 한계", "S2")))
        if isinstance(out, Exception):
            raise out
        return out

    fake_llm.state["structured"][LimitationDraft] = extract
    fake_llm.state["structured"][TopicDraft] = topics if topics is not None else TopicDraft(topics=FOUR)


def call(**kw):
    return topic.run(req(**kw), USER)


def test_normal_flow_matches_the_frontend_shape(fake_llm, lib):
    prepare(fake_llm)
    usage = {}
    r = topic.run(req(), USER, usage)
    assert r.handoff is False and r.needs_review is True and r.view == "dev"
    # 한계: 논문마다 2개, 전역 라벨 S1..S4, 쪽·논문 정보는 근거 블록의 것
    assert [(lim.label, lim.paper_id, lim.page) for lim in r.limitations] == [("S1", 41, 1), ("S2", 41, 2), ("S3", 42, 1), ("S4", 42, 2)]
    assert [d.label for d in r.source_details] == ["S1", "S2", "S3", "S4"] and len(r.sources) == 4
    # 후보: 서로 다른 관점, AI 제안, 존재하는 근거 라벨
    assert [t.perspective for t in r.topics] == ["limitation_fix", "combine", "extend", "efficiency"]
    assert all(t.ai_generated and t.based_on and set(t.based_on) <= {"S1", "S2", "S3", "S4"} for t in r.topics)
    assert r.topics[0].experiment.datasets == ["GLUE"]
    # 추출 2회 + 후보 1회, 토큰은 합계
    assert len(fake_llm.structured_calls) == 3 and (usage["in_tok"], usage["out_tok"]) == (300, 60)


def test_limitations_are_validated(fake_llm, lib):
    messy = limits(("라벨이 없는 한계", "S9"), ("[S2] 본문   한계  ", "S2"), ("같은 블록 두 번째", "S2"), ("세 번째", "S3"), ("네 번째", "S1"))
    prepare(fake_llm, lim={"LoRA": messy, "QLoRA": limits(("한계", "S1"))})
    r = call()
    lora = [lim for lim in r.limitations if lim.paper_id == 41]
    # S9(없는 라벨)와 같은 블록의 두 번째는 버리고, 논문당 상한(2)까지만, [S#] 표시는 지운다
    assert [(lim.page, lim.summary) for lim in lora] == [(2, "본문 한계"), (3, "세 번째")]


def test_candidates_are_validated(fake_llm, lib):
    topics = TopicDraft(topics=[
        item("limitation_fix", ["S1", "S99"], title="유효"),           # 없는 라벨은 빼고 유효한 것만 남긴다
        item("limitation_fix", ["S1"], title="같은 관점 중복"),         # 관점이 겹치면 버린다
        item("combine", ["S99"], title="근거 라벨 없음"),               # 유효한 근거가 하나도 없으면 버린다
        item("extend", [], title="근거 없음"),
        item("efficiency", ["S2"], title="  "),                        # 제목이 비면 버린다
        item("evaluation", ["S3"], title="평가"),
    ])
    prepare(fake_llm, topics=topics)
    r = call(n=3)
    assert [(t.title, t.based_on) for t in r.topics] == [("유효", ["S1"]), ("평가", ["S3"])]  # 후보가 n보다 적으면 그대로


def test_candidate_count_is_capped_at_n(fake_llm, lib):
    prepare(fake_llm)
    assert len(call(n=2).topics) == 2 and len(call(n=1).topics) == 1


def test_list_items_are_cleaned_and_capped(fake_llm, lib):
    many = item("limitation_fix", ["S1"], datasets=[f"D{i}" for i in range(9)] + ["D0", "  ", "[S1]"], baselines=[], metrics=["지표 [S2]"])
    prepare(fake_llm, topics=TopicDraft(topics=[many]))
    t = call().topics[0]
    assert t.experiment.datasets == [f"D{i}" for i in range(5)] and t.experiment.baselines == [] and t.experiment.metrics == ["지표"]


# ---- 근거 없음 ----

def test_no_limitations_is_handoff_without_the_suggest_call(fake_llm, lib):
    prepare(fake_llm, lim={"LoRA": limits(), "QLoRA": limits(("엉뚱한 라벨", "S9"))})
    r = call()
    assert r.handoff is True and r.topics == [] and r.limitations == [] and r.source_details == []
    assert len(fake_llm.structured_calls) == 2  # 추출 2회뿐, 후보 생성은 부르지 않는다


def test_no_evidence_is_handoff_without_llm(fake_llm, lib, monkeypatch):
    monkeypatch.setattr(topic.store, "chunks_of_paper", lambda *a, **k: [])
    r = call()
    assert r.handoff is True and fake_llm.structured_calls == []


def test_all_candidates_invalid_is_handoff(fake_llm, lib):
    prepare(fake_llm, topics=TopicDraft(topics=[item("combine", ["S99"])]))
    r = call()
    assert r.handoff is True and r.topics == [] and r.limitations == []


# ---- 대상 논문 / 팀 격리 ----

def test_papers_not_in_the_team_index_are_ignored(fake_llm, lib):
    prepare(fake_llm)
    r = call(paper_ids=[41, 999, 41])
    assert {lim.paper_id for lim in r.limitations} == {41}
    assert len(fake_llm.structured_calls) == 2  # 추출 1회(41) + 후보 1회
    assert call(paper_ids=[999, 998]).handoff is True and len(fake_llm.structured_calls) == 2  # 전부 없으면 호출 없이 handoff


def test_only_the_users_team_is_used(fake_llm, lib, monkeypatch):
    teams = []
    monkeypatch.setattr(topic.store, "paper_chunk_counts", lambda team_id: teams.append(("counts", team_id)) or {41: 3})
    monkeypatch.setattr(topic.store, "chunks_of_paper", lambda team_id, pid, q, k=4: teams.append(("chunks", team_id)) or [chunk(41, 1)])
    prepare(fake_llm)
    topic.run(req(paper_ids=[41]), CurrentUser(user_id=1, username="u", role="member", team_id=4, team_type="dev", view="dev"))
    assert {team for _, team in teams} == {4} and ("counts", 4) in teams


# ---- 실패 ----

def test_one_failed_paper_is_skipped(fake_llm, lib):
    prepare(fake_llm, lim={"QLoRA": ApiError(503, "UPSTREAM_TIMEOUT", "x")})
    r = call()
    assert {lim.paper_id for lim in r.limitations} == {41} and r.topics


def test_all_extractions_failed_raises(fake_llm, lib):
    err = ApiError(503, "UPSTREAM_TIMEOUT", "x")
    prepare(fake_llm, lim={"LoRA": err, "QLoRA": err})
    with pytest.raises(ApiError) as e:
        call()
    assert e.value.code == "UPSTREAM_TIMEOUT"


def test_unexpected_error_is_not_leaked(fake_llm, lib):
    prepare(fake_llm, lim={"LoRA": RuntimeError("secret-internal"), "QLoRA": limits(("한계", "S1"))})
    r = call()
    assert {lim.paper_id for lim in r.limitations} == {42} and "secret-internal" not in r.model_dump_json()


def test_suggest_failure_is_an_error_not_handoff(fake_llm, lib):
    def boom(system, user):
        raise ApiError(500, "INTERNAL_ERROR", "x")

    prepare(fake_llm)
    fake_llm.state["structured"][TopicDraft] = boom
    with pytest.raises(ApiError):
        call()


# ---- 프롬프트 ----

def test_hint_n_and_view_reach_the_suggest_prompt(fake_llm, lib):
    prepare(fake_llm)
    call(hint="메모리 효율", n=2, view="rnd")
    system, user, _ = [c for c in fake_llm.structured_calls if c[2] is TopicDraft][0]
    from app.rag.prompts import VIEW_RULES
    assert "최대 2개" in system and VIEW_RULES["rnd"] in system
    assert "메모리 효율" in user and "[S1]" in user and "《LoRA: Low-Rank Adaptation》 p.1" in user
    call()
    assert "[방향]\n없음" in [c for c in fake_llm.structured_calls if c[2] is TopicDraft][-1][1]


def test_suggest_prompt_only_has_found_limitations(fake_llm, lib):
    prepare(fake_llm)
    call()
    _, user, _ = [c for c in fake_llm.structured_calls if c[2] is TopicDraft][0]
    assert "LoRA의 한계" in user and "본문" not in user  # 원문 청크가 아니라 찾은 한계만 넘긴다


# ---- 유사 연구 ----

def test_similar_papers_exclude_selected_and_respect_threshold(fake_llm, lib):
    prepare(fake_llm)
    r = call()
    for t in r.topics:
        assert [(s.paper_id, s.score) for s in t.similar_papers] == [(43, 0.81), (77, 0.66)]  # 선택한 41은 빠지고 논문별 최고점, 점수 순
    assert lib[0]["min_score"] == config_rag.TOPIC_SIMILAR_MIN_SCORE and lib[0]["team_id"] == 3 and lib[0]["sources"] == ["pdf"]
    assert "limitation_fix 주제" in lib[0]["query"]  # 후보의 제목과 질문으로 찾는다


def test_similar_papers_are_capped(fake_llm, lib, monkeypatch):
    monkeypatch.setattr(config_rag, "TOPIC_SIMILAR_MAX", 1)
    prepare(fake_llm)
    assert [s.paper_id for s in call().topics[0].similar_papers] == [43]


def test_similar_search_failure_keeps_the_candidates(fake_llm, lib, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("index broken")

    monkeypatch.setattr(topic.store, "search", boom)
    prepare(fake_llm)
    r = call()
    assert len(r.topics) == 4 and all(t.similar_papers == [] for t in r.topics)


# ---- API ----

BODY = {"paper_ids": [41, 42], "hint": "비공개-방향-시험", "n": 4}


def test_api_response_keys_and_token_log(client, auth, fake_llm, lib, access_log):
    prepare(fake_llm)
    r = client.post("/topic-suggest", json=BODY, headers={**auth, "X-Request-Id": "req-topic-1"})
    assert r.status_code == 200
    assert set(r.json()) == {"limitations", "topics", "sources", "source_details", "needs_review", "handoff", "view", "latency_ms"}
    assert set(r.json()["topics"][0]) == {"perspective", "title", "question", "approach", "experiment", "based_on", "similar_papers", "ai_generated"}
    (rec,) = [x for x in access_log if x["request_id"] == "req-topic-1"]
    assert (rec["path"], rec["status"], rec["team_id"], rec["in_tok"], rec["out_tok"]) == ("/topic-suggest", 200, 3, 300, 60)
    assert "비공개" not in json.dumps(rec, ensure_ascii=False)


def test_api_other_team_ids_get_handoff(client, fake_llm, lib, monkeypatch):
    from conftest import make_token
    monkeypatch.setattr(topic.store, "paper_chunk_counts", lambda team_id: {41: 3} if team_id == 3 else {})
    other = {"Authorization": f"Bearer {make_token(team_id=4)}"}
    r = client.post("/topic-suggest", json={"paper_ids": [41]}, headers=other)
    assert r.status_code == 200 and r.json()["handoff"] is True and fake_llm.structured_calls == []


def test_api_requires_login_and_team(client, fake_llm, lib):
    from conftest import make_token
    r = client.post("/topic-suggest", json=BODY)
    assert (r.status_code, r.json()["code"]) == (401, "UNAUTHORIZED")
    r = client.post("/topic-suggest", json=BODY, headers={"Authorization": f"Bearer {make_token(team_id=None)}"})
    assert (r.status_code, r.json()["code"]) == (403, "NO_TEAM")
    assert fake_llm.structured_calls == []


@pytest.mark.parametrize("body", [
    {"paper_ids": []}, {"paper_ids": list(range(1, 12)), "hint": "비공개-방향-시험"}, {"paper_ids": [41], "n": 5},
    {"paper_ids": ["41"]}, {"paper_ids": [41], "hint": "비공개-방향-시험" * 200}, {},
])
def test_api_validation_errors_do_not_echo_input(client, auth, fake_llm, body):
    r = client.post("/topic-suggest", json=body, headers=auth)
    assert (r.status_code, r.json()["code"]) == (422, "VALIDATION_ERROR")
    assert "비공개" not in r.text and fake_llm.structured_calls == []


def test_api_not_ready_is_503(client, auth, fake_llm, monkeypatch):
    from app.rag import router_modes
    monkeypatch.setattr(router_modes.store, "readiness", lambda: {"embedder": False})
    r = client.post("/topic-suggest", json=BODY, headers=auth)
    assert (r.status_code, r.json()["code"]) == (503, "NOT_READY")
