import httpx
import openai
import pytest

from app.rag import config_rag, llm, pipeline
from app.rag.context import build_blocks, render_context
from app.rag.deps import CurrentUser
from app.rag.errors import ApiError
from app.rag.schemas import AnswerDraft, RagRequest
from app.rag.store_stub import Hit

USER = CurrentUser(user_id=12, username="tester", role="member", team_id=3, team_type="dev", view="dev")
REQ = RagRequest(question="LoRA는 어떤 파라미터를 학습하나요?")
TITLE = "LoRA: Low-Rank Adaptation of Large Language Models"
REAL_GENERATE = llm.generate  # conftest의 autouse 가짜로 바뀌기 전의 원본 (수집 시점에 캡처)


def hit(score=0.82, page=1, type="body", has_math=False, text="LoRA freezes the weights.", paper_id=41):
    return Hit(text=text, score=score, metadata={
        "paper_id": paper_id, "source": TITLE, "page": page, "type": type, "has_math": has_math,
        "url": "https://arxiv.org/abs/2106.09685",
    })


@pytest.fixture()
def set_hits(monkeypatch):
    def _set(*hits):
        monkeypatch.setattr(pipeline.store, "search", lambda *a, **k: list(hits))
    return _set


def run(**kw):
    return pipeline.run(REQ.model_copy(update=kw), USER)


# ---- 근거 없음 ----
def test_no_hits_skips_llm(fake_llm, set_hits):
    set_hits()
    r = run()
    assert r.handoff is True and r.sources == [] and fake_llm.calls == []


def test_below_min_score_skips_llm(fake_llm, set_hits):
    set_hits(hit(score=config_rag.MIN_SCORE - 0.01))
    r = run()
    assert r.handoff is True and fake_llm.calls == []


def test_found_false_is_handoff(fake_llm, set_hits):
    set_hits(hit())
    fake_llm.state["draft"] = AnswerDraft(found=False, answer="모르겠습니다", cited=[])
    r = run()
    assert r.handoff is True and r.sources == [] and r.needs_review is False
    assert len(fake_llm.calls) == 1


# ---- 정상 / 출처 ----
def test_clean_answer_has_sources_and_no_review(set_hits):
    set_hits(hit())
    r = run()
    assert r.handoff is False and r.needs_review is False
    assert r.sources == [f"{TITLE} p.1"]
    assert r.source_details[0].label == "S1" and r.source_details[0].paper_id == 41


def test_sources_only_cited_blocks(fake_llm, set_hits):
    set_hits(hit(page=1), hit(page=3), hit(page=5))
    fake_llm.state["draft"] = AnswerDraft(found=True, answer="A [S1] B [S3]", cited=["S1", "S3"])
    r = run()
    assert r.sources == [f"{TITLE} p.1", f"{TITLE} p.5"]
    assert r.needs_review is False


# ---- 인용 검증 ----
def test_unknown_label_marks_review_and_falls_back_to_all(fake_llm, set_hits):
    set_hits(hit(page=1), hit(page=3))
    fake_llm.state["draft"] = AnswerDraft(found=True, answer="A [S9]", cited=["S9"])
    r = run()
    assert r.needs_review is True
    assert r.sources == [f"{TITLE} p.1", f"{TITLE} p.3"]  # 검증된 라벨 0개 → 전체 블록


def test_answer_without_label_marks_review(fake_llm, set_hits):
    set_hits(hit())
    fake_llm.state["draft"] = AnswerDraft(found=True, answer="라벨이 없는 답변", cited=["S1"])
    assert run().needs_review is True


# ---- needs_review 규칙 ----
@pytest.mark.parametrize("answer", ["비용은 $r$ 에 비례 [S1]", "정확도가 12.5 향상 [S1]", "약 30% 감소 [S1]"])
def test_math_or_number_in_answer(fake_llm, set_hits, answer):
    set_hits(hit())
    fake_llm.state["draft"] = AnswerDraft(found=True, answer=answer, cited=["S1"])
    assert run().needs_review is True


def test_has_math_chunk(set_hits):
    set_hits(hit(has_math=True))
    assert run().needs_review is True


def test_weak_score_between_min_and_review(set_hits):
    set_hits(hit(score=(config_rag.MIN_SCORE + config_rag.REVIEW_SCORE) / 2))
    r = run()
    assert r.handoff is False and r.needs_review is True


def test_annotation_only(set_hits):
    set_hits(hit(type="annotation"))
    assert run().needs_review is True


def test_annotation_plus_body_is_ok(fake_llm, set_hits):
    set_hits(hit(page=1), hit(page=2, type="annotation"))
    fake_llm.state["draft"] = AnswerDraft(found=True, answer="A [S1] B [S2]", cited=["S1", "S2"])
    assert run().needs_review is False


# ---- 수준 × 관점 ----
def test_level_view_change_prompt_not_sources(fake_llm, set_hits):
    set_hits(hit())
    base = run(level="L1", view="dev")
    other = run(level="L3", view="rnd")
    (sys_a, _, _), (sys_b, _, _) = fake_llm.calls
    assert sys_a != sys_b
    assert "입문" in sys_a and "구현 관점" in sys_a
    assert "심화" in sys_b and "연구 관점" in sys_b
    assert base.sources == other.sources


def test_question_and_context_in_user_message(fake_llm, set_hits):
    set_hits(hit())
    run()
    _, user, _ = fake_llm.calls[0]
    assert "[S1] 《" + TITLE + "》 p.1" in user and REQ.question in user


# ---- 토큰 기록 / 로그 ----
def test_usage_recorded_and_no_text_in_log(set_hits, caplog):
    set_hits(hit())
    usage = {}
    with caplog.at_level("INFO", logger="rag"):
        pipeline.run(REQ, USER, usage)
    assert usage == {"in_tok": 100, "out_tok": 20, "images": 0, "retry": "none"}
    assert REQ.question not in caplog.text and "저랭크" not in caplog.text


# ---- 컨텍스트 ----
def test_context_merges_same_page_and_marks_annotation():
    blocks = build_blocks([hit(text="a"), hit(text="b"), hit(page=2, type="annotation", text="memo")])
    assert [b.label for b in blocks] == ["S1", "S2"] and blocks[0].text == "a\nb"
    ctx = render_context(blocks)
    assert "[S2]" in ctx and "(팀원 주석)" in ctx


def test_context_respects_max_chars():
    blocks = build_blocks([hit(page=i, text="x" * 100) for i in range(1, 6)], max_chars=250)
    assert sum(len(b.text) for b in blocks) == 250


# ---- LLM 오류 매핑 ----
class _Chain:
    def __init__(self, exc=None, out=None):
        self.exc, self.out = exc, out

    def invoke(self, _):
        if self.exc:
            raise self.exc
        return self.out


class _FakeModel:
    def __init__(self, chain):
        self.chain = chain

    def with_structured_output(self, *_, **__):
        return self.chain


def test_timeout_maps_to_503(monkeypatch):
    exc = openai.APITimeoutError(request=httpx.Request("POST", "http://x"))
    monkeypatch.setattr(llm, "get_llm", lambda: _FakeModel(_Chain(exc=exc)))
    with pytest.raises(ApiError) as e:
        REAL_GENERATE("s", "u")
    assert (e.value.status, e.value.code) == (503, "UPSTREAM_TIMEOUT")
    assert "http://x" not in e.value.detail


def test_unexpected_error_hides_message(monkeypatch):
    monkeypatch.setattr(llm, "get_llm", lambda: _FakeModel(_Chain(exc=RuntimeError("secret-internal"))))
    with pytest.raises(ApiError) as e:
        REAL_GENERATE("s", "u")
    assert e.value.status == 500 and "secret-internal" not in e.value.detail


def test_page_images_attached_only_for_visual_blocks(monkeypatch):
    from app.rag import config_rag, page_images, pipeline
    from app.rag.context import Block

    monkeypatch.setattr(page_images, "render_page", lambda tid, pid, page: f"img{pid}-{page}")
    blocks = [Block("S1", 1, "A", 3, None, "body", ["t"], visual=False, score=0.9),
              Block("S2", 1, "A", 5, None, "body", ["t"], visual=True, score=0.6),
              Block("S3", 2, "B", 2, None, "body", ["t"], visual=True, score=0.8),
              Block("S4", 2, "B", 2, None, "annotation", ["t"], visual=True, score=0.7)]
    assert page_images.pick_pages(3, blocks, max_pages=2) == [("S3", "img2-2"), ("S2", "img1-5")]  # 점수순, 같은 페이지는 한 번
    assert page_images.pick_pages(3, blocks[:1], max_pages=2) == []


# ---- 텍스트 우선 + 이미지 재시도 ----
def table_hit(**kw):
    h = hit(text="Fine-Tune/LoRA 19.8 AdapterL 23.9 (+20.7%)", **kw)
    h.metadata["has_table"] = True
    return h


@pytest.fixture()
def images_on(monkeypatch):
    from app.rag import config_rag, page_images

    monkeypatch.setattr(config_rag, "PAGE_IMAGES", True)
    monkeypatch.setattr(page_images, "render_page", lambda tid, pid, page: "png")


def test_image_retry_when_cited_visual_block_and_value(set_hits, fake_llm, images_on):
    set_hits(table_hit())
    fake_llm.state["drafts"] = [AnswerDraft(found=True, answer="20.7% 늘어납니다 [S1]", cited=["S1"]),
                                AnswerDraft(found=True, answer="AdapterL은 20.7% 증가 [S1]", cited=["S1"])]
    usage = {}
    resp = pipeline.run(REQ, USER, usage)
    assert len(fake_llm.calls) == 2 and fake_llm.calls[0][2] is None and fake_llm.calls[1][2] == [("S1", "png")]
    assert resp.answer.startswith("AdapterL") and resp.needs_review and usage["images"] == 1
    assert usage["in_tok"] == 200  # 두 호출 합산


def test_no_retry_for_refusal_or_plain_text(set_hits, fake_llm, images_on):
    set_hits(table_hit())
    fake_llm.state["draft"] = AnswerDraft(found=False, answer="", cited=[])
    assert pipeline.run(REQ, USER).handoff and len(fake_llm.calls) == 1  # 거절은 재시도하지 않는다
    fake_llm.calls.clear()
    fake_llm.state["draft"] = AnswerDraft(found=True, answer="가중치를 고정합니다 [S1]", cited=["S1"])
    pipeline.run(REQ, USER)
    assert len(fake_llm.calls) == 1  # 수치·수식이 없으면 재시도하지 않는다


def test_retry_refusal_withholds_unverified_values(set_hits, fake_llm, images_on):
    set_hits(table_hit())
    fake_llm.state["drafts"] = [AnswerDraft(found=True, answer="19.8ms입니다 [S1]", cited=["S1"]),
                                AnswerDraft(found=False, answer="", cited=[])]
    usage = {}
    resp = pipeline.run(REQ, USER, usage)
    # 이미지에서 확인되지 않은 텍스트 수치는 내보내지 않고, 원본 페이지만 안내한다
    assert resp.answer == pipeline.WITHHELD_ANSWER and "19.8" not in resp.answer
    assert resp.needs_review and not resp.handoff and resp.sources and usage["retry"] == "withheld"


def test_refusal_retry_only_when_enabled(set_hits, fake_llm, images_on, monkeypatch):
    set_hits(table_hit())
    fake_llm.state["drafts"] = [AnswerDraft(found=False, answer="", cited=[]),
                                AnswerDraft(found=True, answer="AdapterL 23.9ms [S1]", cited=["S1"])]
    assert pipeline.run(REQ, USER).handoff and len(fake_llm.calls) == 1  # 기본: 거절은 재시도 안 함
    fake_llm.calls.clear()
    fake_llm.state["drafts"] = [AnswerDraft(found=False, answer="", cited=[]),
                                AnswerDraft(found=True, answer="AdapterL 23.9ms [S1]", cited=["S1"])]
    monkeypatch.setattr(config_rag, "PAGE_IMAGES_ON_REFUSAL", True)
    usage = {}
    resp = pipeline.run(REQ, USER, usage)
    assert not resp.handoff and resp.needs_review and usage["retry"] == "refusal_answered"


def test_limit_captions_keeps_body_chunks():
    cap = lambda s: Hit(text="Figure 1: x", score=s, metadata={"kind": "caption"})
    body = lambda s: Hit(text="t", score=s, metadata={"kind": "text"})
    hits = [cap(.9), cap(.8), body(.7), cap(.6), body(.5), body(.4), body(.3)]
    out = pipeline.limit_captions(hits, 4, 1)
    assert [h.score for h in out] == [.9, .7, .5, .4]
    assert pipeline.limit_captions(hits, 4, None) == hits[:4]


def test_image_call_uses_image_model(monkeypatch):
    calls = []

    def fake_get_llm(model=None, effort=None):
        calls.append((model, effort))
        return _FakeModel(_Chain(exc=RuntimeError("stop")))

    monkeypatch.setattr(llm, "generate", REAL_GENERATE)
    monkeypatch.setattr(llm, "get_llm", fake_get_llm)
    monkeypatch.setattr(config_rag, "LLM_IMAGE_MODEL", "gpt-6-luna")
    monkeypatch.setattr(config_rag, "LLM_IMAGE_REASONING_EFFORT", "none")
    for images in (None, [("S1", "png")]):
        with pytest.raises(ApiError):
            llm.generate("s", "u", images=images)
    assert calls == [(None, None), ("gpt-6-luna", "none")]  # 텍스트는 기본 모델, 이미지는 이미지 모델
    assert llm.is_reasoning_model("gpt-6-luna") and not llm.is_reasoning_model("gpt-4o")


def test_pdf_path_prefers_store_contract(monkeypatch):
    from app.rag import deps, page_images

    monkeypatch.setattr(deps.store, "pdf_path", lambda team_id, paper_id: f"/pdf/{team_id}/{paper_id}.pdf", raising=False)
    assert page_images._pdf_path(3, 7) == "/pdf/3/7.pdf"  # 저장소가 팀별 경로를 주면 로컬 시드를 보지 않는다
