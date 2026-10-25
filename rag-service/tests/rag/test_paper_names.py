"""질문이 이름을 든 논문 감지와 논문별 검색 합치기 (app/rag/paper_names.py, pipeline._with_named_papers)."""
import pytest

from app.rag import config_rag, paper_names, pipeline
from app.rag.schemas import RagRequest, Scope
from app.rag.store_stub import Hit

TITLES = {
    1: "LoRA: Low-Rank Adaptation of Large Language Models",
    2: "QLoRA: Efficient Finetuning of Quantized LLMs",
    3: "The Power of Scale for Parameter-Efficient Prompt Tuning",
    4: "Prefix-Tuning: Optimizing Continuous Prompts for Generation",
    5: "Parameter-Efficient Transfer Learning for NLP",
    6: "RETA-LLM: A Retrieval-Augmented Large Language Model Toolkit",
}
ALIASES = paper_names.aliases_of(TITLES)


def names(question):
    return sorted(paper_names.detect(question, ALIASES))


@pytest.mark.parametrize("question,expected", [
    ("QLoRA와 Prefix-Tuning의 차이점은 무엇인가요?", [2, 4]),
    ("프롬프트 튜닝과 프리픽스 튜닝은 무엇이 다른가요?", [3, 4]),
    ("Q LoRA와 LoRA의 차이점은?", [1, 2]),           # 띄어쓰기 오타
    ("QLoRA, LoRA, 어댑터 세 방법을 비교해 주세요", [1, 2, 5]),
    ("LoRA와 어댑터 방식은 추론 지연이 어떻게 다른가요?", [1, 5]),
    ("How does QLoRA differ from prefix-tuning?", [2, 4]),
])
def test_detects_every_named_paper(question, expected):
    assert names(question) == expected


@pytest.mark.parametrize("question,expected", [
    ("QLoRA는 무엇을 양자화하나요?", [2]),            # QLoRA 안의 LoRA를 따로 세지 않는다
    ("LoRA는 어떤 파라미터를 학습하나요?", [1]),
    ("어댑터는 몇 개의 과제로 실험했나요?", [5]),
    ("트랜스포머의 어텐션은 어떻게 동작하나요?", []),
    ("colorado에서 열린 학회는?", []),                # 영단어의 일부(colorado 안의 lora)는 이름이 아니다
    ("", []),
])
def test_single_or_no_name_is_not_a_comparison(question, expected):
    assert names(question) == expected


def test_aliases_use_title_prefix_for_papers_not_in_the_table():
    out = paper_names.aliases_of({9: "NewMethod: A Brand New Idea"})
    assert out == {9: ["newmethod"]}
    assert paper_names.aliases_of({10: "A Title Without Colon"}) == {}


def h(text, score, paper):
    return Hit(text=text, score=score, metadata={"paper_id": paper, "source": TITLES[paper], "page": 1, "type": "body"})


def test_merge_takes_one_per_paper_in_turn_then_fills_from_base():
    base = [h("b1", 0.7, 1), h("b2", 0.69, 1), h("b3", 0.68, 1), h("b4", 0.67, 1), h("b5", 0.66, 1)]
    per_paper = [[h("l1", 0.62, 1), h("l2", 0.61, 1)], [h("a1", 0.52, 5), h("a2", 0.51, 5)]]
    out = paper_names.merge(base, per_paper, 5)
    assert len(out) == 5
    assert {x.metadata["paper_id"] for x in out} == {1, 5}            # 두 논문이 모두 들어온다
    assert [x.score for x in out] == sorted((x.score for x in out), reverse=True)


def test_merge_does_not_duplicate_chunks():
    same = h("same", 0.7, 1)
    out = paper_names.merge([same], [[same], [h("a1", 0.52, 5)]], 5)
    assert [x.text for x in out].count("same") <= 2 and len({id(x) for x in out}) == len(out)


# ---- 파이프라인 연결 ----
REQ = RagRequest(question="LoRA와 어댑터 방식은 추론 지연이 어떻게 다른가요?")


class User:
    team_id = 3


@pytest.fixture()
def fake_store(monkeypatch):
    calls = []

    def search(team_id, sources, query, k=5, paper_ids=None, tags=None, min_score=None):
        calls.append({"k": k, "paper_ids": paper_ids})
        if paper_ids == [5]:
            return [h("adapter text", 0.52, 5), h("adapter text 2", 0.46, 5)]   # 두 번째는 하한(0.50) 미만이라 빠진다
        if paper_ids == [1]:
            return [h("lora text", 0.61, 1)]
        return [h(f"lora {i}", 0.7 - i * 0.01, 1) for i in range(5)]             # 기본 검색은 LoRA 논문이 전부 차지한다

    monkeypatch.setattr(pipeline.store, "search", search)
    monkeypatch.setattr(pipeline.store, "paper_titles", lambda team: TITLES, raising=False)
    return calls


def test_pipeline_merges_named_papers_and_applies_the_named_floor(fake_store):
    hits = pipeline._with_named_papers(REQ, 3, [h(f"lora {i}", 0.7 - i * 0.01, 1) for i in range(5)])
    assert {x.metadata["paper_id"] for x in hits} == {1, 5} and len(hits) == 5
    assert all(x.score >= config_rag.NAMED_PAPER_MIN_SCORE for x in hits if x.metadata["paper_id"] == 5)
    assert "adapter text 2" not in [x.text for x in hits]
    assert sorted(c["paper_ids"][0] for c in fake_store if c["paper_ids"]) == [1, 5]


@pytest.mark.parametrize("update", [
    {"question": "LoRA는 어떤 파라미터를 학습하나요?"},                          # 이름 하나
    {"question": "트랜스포머는 어떻게 동작하나요?"},                              # 이름 없음
    {"scope": Scope(type="paper", ids=[1])},                                   # 왼쪽 목록에서 논문을 골랐다
])
def test_pipeline_leaves_other_questions_alone(fake_store, update):
    base = [h("only", 0.7, 1)]
    assert pipeline._with_named_papers(REQ.model_copy(update=update), 3, base) is base
    assert fake_store == []


def test_pipeline_without_title_support_is_unchanged(monkeypatch):
    monkeypatch.delattr(pipeline.store, "paper_titles", raising=False)
    base = [h("only", 0.7, 1)]
    assert pipeline._with_named_papers(REQ, 3, base) is base
