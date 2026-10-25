import json

from app.rag import dev_eval
from app.rag.store_stub import Hit


def h(source, page, score=0.5):
    return Hit(text="t", score=score, metadata={"source": source, "page": page})


EV = [{"paper": "A", "pages": [4]}]


def test_first_hit_rank_uses_paper_and_page_tolerance():
    hits = [h("B", 4), h("A", 9), h("A", 5), h("A", 4)]
    assert dev_eval.first_hit_rank(hits, EV) == 3  # p5는 ±1 이내
    assert dev_eval.first_hit_rank(hits, EV, page_tol=0) == 4
    assert dev_eval.first_hit_rank([h("B", 4)], EV) is None


def test_first_hit_rank_accepts_extra_evidence():
    assert dev_eval.first_hit_rank([h("C", 2)], EV + [{"paper": "C", "pages": [2]}]) == 1


def test_best_threshold_separates_when_possible():
    t, n = dev_eval.best_threshold([0.6, 0.5, 0.45], [0.3, 0.2])
    assert n == 5 and 0.3 < t <= 0.45


def test_best_threshold_reports_overlap():
    _, n = dev_eval.best_threshold([0.6, 0.3], [0.4])
    assert n == 2  # 3문항 중 1문항은 점수만으로 못 가른다


def test_questions_file_is_valid():
    path = dev_eval.QUESTIONS
    qs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(qs) == 30 and sum(q["should_refuse"] for q in qs) == 6
    assert len({q["id"] for q in qs}) == 30  # id 중복 없음
    required = {"id", "type", "question", "level", "view", "expected_answer", "key_points", "evidence", "should_refuse"}
    assert all(required <= set(q) for q in qs)
    assert all(q["evidence"] and q["evidence"]["pages"] for q in qs if not q["should_refuse"])


def test_evaluate_computes_metrics():
    qs = [
        {"id": "N1", "type": "general", "question": "질문", "should_refuse": False, "evidence": EV[0]},
        {"id": "X1", "type": "exception", "question": "예외", "should_refuse": True, "evidence": None},
    ]
    data = {"질문": [h("A", 4, 0.7)], "예외": [h("A", 1, 0.3)]}
    res = dev_eval.evaluate(qs, lambda q, k: data[q], k=5)
    assert res["hit@1"] == 1 and res["mrr"] == 1 and res["separated"] == "2/2"


def test_answer_rank_requires_all_key_points_in_right_paper():
    q = {"evidence": {"paper": "A", "pages": [1]}, "key_points": ["alpha", "beta|베타"]}
    hit = lambda src, text: Hit(text=text, score=0.5, metadata={"source": src, "page": 1})
    hits = [hit("B", "alpha beta"), hit("A", "alpha only"), hit("A", "Alpha and 베타")]
    assert dev_eval.answer_rank(hits, q) == 3
    assert dev_eval.answer_rank(hits, {**q, "key_points": []}) is None


def test_extra_questions_file_is_valid():
    path = dev_eval.QUESTIONS.with_name("rag_extra.jsonl")
    qs = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    base = [json.loads(l) for l in dev_eval.QUESTIONS.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(qs) == 23 and sum(q["should_refuse"] for q in qs) == 3
    assert not {q["id"] for q in qs} & {q["id"] for q in base}  # id가 기존 질문과 겹치지 않음
