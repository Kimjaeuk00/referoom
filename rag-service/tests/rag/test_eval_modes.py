"""eval/의 모드별 평가(mode_checks.py, run_eval.py)를 네트워크·LLM 없이 시험한다. 가짜 HTTP 서버(httpx.MockTransport)를 쓴다."""
import json
import sys
from collections import Counter
from pathlib import Path

import httpx
import pytest

EVAL = Path(__file__).resolve().parents[3] / "eval"
sys.path.insert(0, str(EVAL))

import mode_checks  # noqa: E402
import run_eval  # noqa: E402

QUESTIONS = EVAL / "questions"
BASE = "http://rag.test"


def questions():
    return run_eval.load_questions(QUESTIONS)


def sample(mode, qid=None):
    return next(q for q in questions() if q["mode"] == mode and (qid is None or q["id"] == qid))


# ---------- 질문 파일 ----------

def test_question_files_cover_every_mode_and_pass_the_count_rules():
    qs = questions()
    assert run_eval.dataset_gaps(qs) == []
    modes = Counter(q["mode"] for q in qs)
    assert modes["tutor"] == 49 and all(modes[m] >= 3 for m in ("prior", "topic", "verify"))
    assert all(q["type"] == q["mode"] for q in qs if q["mode"] != "tutor")
    assert len({q["id"] for q in qs}) == len(qs)


def write(tmp_path, *items):
    (tmp_path / "q.jsonl").write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n", encoding="utf-8")
    return tmp_path


TUTOR = {"id": "X1", "type": "general", "question": "질문입니다", "level": "L2", "expected_answer": "답",
         "key_points": ["a"], "evidence": {"paper": "P", "pages": [1]}, "should_refuse": False}


def test_a_question_without_mode_is_tutor(tmp_path):
    assert run_eval.load_questions(write(tmp_path, TUTOR))[0]["mode"] == "tutor"


@pytest.mark.parametrize("change", [
    {"type": "level"},              # 예전 '수준' 유형은 없어졌다(요청 깊이 질문은 depth)
    {"mode": "chat"},
    {"level": None},                # tutor는 요청 깊이가 필수
    {"level": "L4"},
    {"type": "exception"},          # 거절 유형과 should_refuse가 어긋남
])
def test_invalid_tutor_questions_are_rejected(tmp_path, change):
    with pytest.raises(ValueError):
        run_eval.load_questions(write(tmp_path, {**TUTOR, **change}))


def test_depth_type_is_a_valid_tutor_type(tmp_path):
    assert run_eval.load_questions(write(tmp_path, {**TUTOR, "type": "depth"}))[0]["type"] == "depth"


def test_level_is_optional_for_other_modes(tmp_path):
    item = {**sample("verify"), "id": "Z9"}
    item.pop("level", None)
    assert run_eval.load_questions(write(tmp_path, item))[0]["id"] == "Z9"
    with pytest.raises(ValueError):
        run_eval.load_questions(write(tmp_path, {**item, "level": "L9"}))


def bad(mode, **change):
    item = {**sample(mode), **change}
    return item


@pytest.mark.parametrize("item", [
    bad("prior", expected_papers=[]),
    bad("prior", expected_papers=["A"], expected_cells=[{"paper": "A", "column": "nope", "pattern": "x"}]),
    bad("prior", expected_papers=["A"], expected_cells=[{"paper": "A", "column": "method", "pattern": "("}]),
    bad("prior", expected_papers=["A"], expected_cells=[{"paper": "A", "column": "method"}]),
    bad("topic", papers=[]),
    bad("topic", papers=[f"p{i}" for i in range(11)]),
    bad("topic", n=9),
    bad("topic", min_topics=0),
    bad("topic", should_refuse=True),
    bad("verify", expected_claims=[]),
    bad("verify", expected_claims=[{"contains": "x", "verdicts": ["maybe"]}]),
    bad("verify", expected_claims=[{"contains": "x", "verdicts": ["match"], "extra": 1}]),
    bad("verify", question="짧은 원고"),   # 서버 하한 10자 미만
    bad("verify", should_refuse=True),
])
def test_invalid_mode_questions_are_rejected(item):
    with pytest.raises(ValueError):
        mode_checks.validate_item(item)


# ---------- 요청 만들기 ----------

def test_requests_follow_each_modes_api():
    path, body = mode_checks.build_request(sample("prior", "PR01"), 5)
    assert path == "/rag-query" and body["mode"] == "prior" and body["question"] and "level" not in body and body["top_k"] == 5
    path, body = mode_checks.build_request(sample("topic", "TP03"), 5, [7])
    assert path == "/topic-suggest" and body == {"paper_ids": [7], "hint": "어댑터와 LoRA를 비교하는 방향", "n": 2}
    path, body = mode_checks.build_request(sample("verify", "VF01"), 5)
    assert path == "/verify" and set(body) == {"text"} and body["text"].startswith("LoRA")
    tutor = sample("tutor")
    path, body = mode_checks.build_request(tutor, 3)
    assert path == "/rag-query" and "mode" not in body and body["level"] == tutor["level"]  # 요청 깊이는 그대로 보낸다


LIBRARY = [{"id": 11, "title": "LoRA: Low-Rank Adaptation of Large Language Models"},
           {"id": 12, "title": "QLoRA: Efficient Finetuning of Quantized LLMs"},
           {"id": 13, "title": "Prefix-Tuning: Optimizing Continuous Prompts"}]


def test_titles_resolve_to_ids_only_when_unique():
    assert mode_checks.resolve_papers(["lora: low-rank", "QLoRA"], LIBRARY) == [11, 12]
    assert mode_checks.resolve_papers(["LoRA"], LIBRARY) is None          # LoRA·QLoRA 둘 다 해당
    assert mode_checks.resolve_papers(["Missing"], LIBRARY) is None
    assert mode_checks.resolve_papers(["Prefix-Tuning"], []) is None


# ---------- 응답 검사 ----------

def prior_body(**change):
    body = {"handoff": False, "sources": ["a"], "source_details": [{"label": "S1", "page": 1}, {"label": "S2", "page": 2}],
            "table": [
                {"paper_id": 1, "title": "LoRA: Low-Rank Adaptation of Large Language Models", "method": "저랭크 행렬 학습", "labels": {"method": "S1"},
                 "problem": None, "dataset": None, "metric": None, "result": None, "limitation": None},
                {"paper_id": 2, "title": "QLoRA: Efficient Finetuning of Quantized LLMs", "method": "4-bit NormalFloat 양자화", "labels": {"method": "S2"},
                 "problem": None, "dataset": None, "metric": None, "result": None, "limitation": None},
            ]}
    return {**body, **change}


def test_prior_check():
    item = sample("prior", "PR01")
    assert mode_checks.check(item, prior_body()) == (True, "papers=2/2;cells=1/1;labels=ok")
    only_one = prior_body(table=prior_body()["table"][:1])
    assert mode_checks.check(item, only_one)[0] is False                                   # 기대한 논문이 표에 없다
    wrong = prior_body()
    wrong["table"][1]["method"] = "어댑터를 끼운다"
    assert mode_checks.check(item, wrong) == (False, "papers=2/2;cells=0/1;labels=ok")      # 칸 내용이 틀리다
    ungrounded = prior_body()
    ungrounded["table"][1]["labels"] = {"method": "S9"}
    assert mode_checks.check(item, ungrounded) == (False, "papers=2/2;cells=1/1;labels=bad")  # 없는 출처 라벨
    assert mode_checks.check(item, prior_body(handoff=True))[1] == "handoff"


def test_prior_refusal_requires_handoff_without_table_or_sources():
    item = sample("prior", "PR03")
    assert mode_checks.check(item, {"handoff": True, "table": None, "sources": [], "source_details": []})[0] is True
    assert mode_checks.check(item, prior_body())[0] is False
    assert mode_checks.check(item, {"handoff": True, "table": None, "sources": ["x"], "source_details": []})[0] is False


def topic_body(**change):
    body = {"handoff": False, "needs_review": True, "source_details": [{"label": "S1"}, {"label": "S2"}],
            "limitations": [{"label": "S1"}, {"label": "S2"}],
            "topics": [{"perspective": "한계 직접 해결", "based_on": ["S1"]}, {"perspective": "방법 결합", "based_on": ["S1", "S2"]}]}
    return {**body, **change}


def test_topic_check():
    item = sample("topic", "TP01")
    assert mode_checks.check(item, topic_body()) == (True, "topics=2/2;labels=ok;perspectives=distinct")
    assert mode_checks.check(item, topic_body(topics=topic_body()["topics"][:1]))[0] is False        # 후보 수 부족
    dup = [{"perspective": "방법 결합", "based_on": ["S1"]}, {"perspective": "방법 결합", "based_on": ["S2"]}]
    assert mode_checks.check(item, topic_body(topics=dup)) == (False, "topics=2/2;labels=ok;perspectives=dup")
    unknown = [{"perspective": "a", "based_on": ["S1"]}, {"perspective": "b", "based_on": ["S7"]}]
    assert mode_checks.check(item, topic_body(topics=unknown)) == (False, "topics=2/2;labels=bad;perspectives=distinct")  # 없는 근거 라벨
    assert mode_checks.check(item, topic_body(topics=[{"perspective": "a", "based_on": []}] * 2))[0] is False  # 근거 없는 후보
    assert mode_checks.check(item, topic_body(handoff=True))[1] == "handoff"


def verify_body(verdict="match", labels=("S1",), **change):
    body = {"handoff": False, "draft": "d", "warnings": [], "source_details": [{"label": "S1"}],
            "claims": [{"sentence": "LoRA는 10,000배 줄인다", "subject": "LoRA", "verdict": verdict, "labels": list(labels)}]}
    return {**body, **change}


def test_verify_check():
    item = sample("verify", "VF01")
    assert mode_checks.check(item, verify_body()) == (True, "claims=1/1;labels=ok")
    assert mode_checks.check(item, verify_body("mismatch"))[0] is False                    # 기대한 판정이 아니다
    assert mode_checks.check(item, verify_body(labels=()))[0] is False                     # 근거가 있다는 판정인데 라벨이 없다
    assert mode_checks.check(item, verify_body(labels=("S9",)))[0] is False                # 없는 출처 라벨
    assert mode_checks.check(item, verify_body(claims=[]))[0] is False                     # 기대한 주장이 추출되지 않았다
    # 근거 없음 판정은 라벨이 없어도 된다
    dora = sample("verify", "VF03")
    body = verify_body("not_found", labels=(), claims=[{"sentence": "DoRA는 71.2다", "subject": "DoRA", "verdict": "not_found", "labels": []}])
    assert mode_checks.check(dora, body) == (True, "claims=1/1;labels=ok")
    # 근거를 하나도 못 찾으면 서버가 handoff와 not_found 주장을 함께 돌려준다: not_found를 기대한 질문만 통과
    assert mode_checks.check(dora, {**body, "handoff": True}) == (True, "claims=1/1;labels=ok")
    assert mode_checks.check(dora, {**body, "handoff": True, "claims": []})[0] is False        # 주장이 없으면 실패
    assert mode_checks.check(sample("verify", "VF01"), verify_body("not_found", labels=(), handoff=True)) == (False, "handoff")
    # 조건 다름도 불일치도 모두 허용하는 질문(VF02)
    qlora = sample("verify", "VF02")
    for verdict in ("mismatch", "condition_differs"):
        claim = {"sentence": "QLoRA 24GB", "subject": "QLoRA", "verdict": verdict, "labels": ["S1"]}
        assert mode_checks.check(qlora, verify_body(claims=[claim]))[0] is True
    assert mode_checks.check(qlora, verify_body(claims=[{"sentence": "QLoRA 24GB", "subject": "QLoRA", "verdict": "match", "labels": ["S1"]}]))[0] is False


# ---------- 가짜 서버로 전체 흐름 ----------

def fake_server(seen):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, body))
        assert request.headers["authorization"] == "Bearer t"
        if request.url.path == "/papers":
            return httpx.Response(200, json={"total": 3, "items": LIBRARY})
        if request.url.path == "/topic-suggest":
            return httpx.Response(200, json={**topic_body(), "latency_ms": 5})
        if request.url.path == "/verify":
            return httpx.Response(200, json={**verify_body(), "latency_ms": 5})
        assert request.url.path == "/rag-query"
        if body.get("mode") == "prior":
            return httpx.Response(200, json={**prior_body(), "answer": "표", "level": "L2", "needs_review": False, "latency_ms": 5})
        return httpx.Response(200, json={"answer": "답", "sources": ["s"], "source_details": [{"title": "T", "page": 1}], "handoff": False,
                                         "needs_review": False, "level": body["level"], "latency_ms": 5})
    return handler


def run(items, seen):
    rubric = run_eval.load_rubric()
    with httpx.Client(transport=httpx.MockTransport(fake_server(seen))) as client:
        return run_eval.evaluate_questions(items, client, BASE, "t", rubric=rubric)


def test_evaluate_runs_every_mode_against_its_endpoint():
    tutor = {**sample("tutor"), "evidence": {"paper": "T", "pages": [1]}, "should_refuse": False, "type": "general"}
    items = [tutor, sample("prior", "PR01"), sample("topic", "TP01"), sample("verify", "VF01")]
    seen = []
    rows = run(items, seen)
    assert [r["status"] for r in rows] == ["ok"] * 4
    assert [r["mode"] for r in rows] == ["tutor", "prior", "topic", "verify"]
    assert rows[0]["grounded"] is True and rows[0]["mode_pass"] is None and rows[0]["judge_status"] == "not_configured"
    assert [r["mode_pass"] for r in rows[1:]] == [True, True, True]
    assert rows[2]["mode_detail"].startswith("topics=2/2") and all(r["judge_status"] == "not_applicable" for r in rows[1:])
    assert [(m, p) for m, p, _ in seen] == [("POST", "/rag-query"), ("POST", "/rag-query"), ("GET", "/papers"), ("POST", "/topic-suggest"), ("POST", "/verify")]
    assert seen[3][2]["paper_ids"] == [11, 12]    # 제목이 라이브러리 id로 바뀌어 간다


def test_topic_question_with_unknown_papers_is_not_sent():
    seen = []
    row = run([{**sample("topic", "TP01"), "papers": ["Not in the library"]}], seen)[0]
    assert row["status"] == "request_error" and row["mode_pass"] is None and row["accuracy"] is False
    assert [p for _, p, _ in seen] == ["/papers"]   # /topic-suggest는 부르지 않는다


def test_a_malformed_mode_response_is_not_counted_as_a_pass():
    def handler(request):
        return httpx.Response(200, json={"claims": "x", "handoff": False, "source_details": [], "latency_ms": 1})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        row = run_eval.evaluate_questions([sample("verify", "VF01")], client, BASE, "t", rubric=run_eval.load_rubric())[0]
    assert row["status"] == "invalid_response" and row["mode_pass"] is False


# ---------- 집계·보고서·재집계 ----------

def test_summary_report_and_rescoring_keep_modes_apart(tmp_path):
    tutor = {**sample("tutor"), "evidence": {"paper": "T", "pages": [1]}, "should_refuse": False, "type": "general"}
    items = [tutor, sample("prior", "PR01"), sample("topic", "TP01"), sample("verify", "VF01")]
    rows = run(items, [])
    rows[3]["mode_pass"], rows[3]["mode_detail"] = False, "claims=0/1;labels=ok"
    summary = run_eval.summarize(rows)
    assert summary["tutor_total"] == 1 and summary["grounded_pass"] == 1 and summary["grounded_total"] == 1
    assert summary["modes"] == {"prior": {"total": 1, "ok": 1, "pass": 1}, "topic": {"total": 1, "ok": 1, "pass": 1},
                                "verify": {"total": 1, "ok": 1, "pass": 0}}
    assert summary["accuracy_known"] == 0   # 정확성·환각 판정은 tutor 답변만 센다

    csv_path, md_path = run_eval.write_reports(rows, items, tmp_path, "t1", rubric=run_eval.load_rubric())
    report = md_path.read_text(encoding="utf-8")
    assert "prior 1/1" in report and "verify 0/1" in report and "요청 깊이 적합성" in report and "수준 적합성(수동):" not in report
    header = csv_path.read_text(encoding="utf-8-sig").splitlines()[0].split(",")
    assert {"mode", "mode_pass", "mode_detail", "level_score"} <= set(header)
    assert all(i["question"] not in report for i in items) and "claims=0/1" not in report   # 질문 원문 없이 개수만 (detail은 CSV에만)

    again = run_eval.read_collection(csv_path, items)
    assert [r["mode"] for r in again] == ["tutor", "prior", "topic", "verify"] and [r["mode_pass"] for r in again] == [None, True, True, False]
    template = run_eval.review_template(again, items, run_eval.load_rubric())
    assert [r["id"] for r in template["records"]] == [tutor["id"]]   # 사람·자동 판정 양식은 tutor만
    staged = run_eval.apply_reviews(again, items, template, run_eval.load_rubric())
    assert [r["judge_status"] for r in staged] == ["not_configured", "not_applicable", "not_applicable", "not_applicable"]


def test_the_judge_is_only_called_for_tutor_answers():
    tutor = {**sample("tutor"), "evidence": {"paper": "T", "pages": [1]}, "should_refuse": False, "type": "general"}
    calls = []

    def judge(question, response, rubric):
        calls.append(question["id"])
        return {"id": question["id"], "response_sha256": run_eval.fingerprint(response),
                "key_points": ["unjudgeable"] * len(question["key_points"]), "contradiction": None, "refusal_appropriate": None,
                "fabricated_answer": None, "context_complete": False, "context_sha256": None, "claims": [],
                "human_reviewed": False, "level_score": None, "math_correct": None}

    seen = []
    with httpx.Client(transport=httpx.MockTransport(fake_server(seen))) as client:
        rows = run_eval.evaluate_questions([tutor, sample("prior", "PR01")], client, BASE, "t", rubric=run_eval.load_rubric(),
                                           judge=judge, judge_model="fixed-judge")
    assert calls == [tutor["id"]]                                  # prior 응답은 판정기에 보내지 않는다
    assert rows[0]["judge_model"] == "fixed-judge" and rows[1]["judge_model"] is None
