"""A0 기반: llm.generate_structured의 오류 규칙, 가짜 LLM(fake_llm) 확장, 모드별 요청·응답 스키마."""
import logging
from types import SimpleNamespace

import httpx
import openai
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.rag import config_rag, context, llm, pipeline
from app.rag.errors import ApiError, register_error_handlers
from app.rag.schemas import (
    Claim, RagRequest, RagResponse, SummaryRequest, SummaryResponse, TopicRequest, TopicResponse, VerifyRequest, VerifyResponse,
)

REAL_STRUCTURED = llm.generate_structured  # conftest의 autouse 가짜로 바뀌기 전의 원본 (수집 시점에 캡처)


class _Out(BaseModel):
    x: int


class _Chain:
    def __init__(self, out=None, exc=None):
        self.out, self.exc, self.messages = out, exc, None

    def invoke(self, messages):
        self.messages = messages
        if self.exc:
            raise self.exc
        return self.out


class _Model:
    def __init__(self, chain):
        self.chain, self.asked = chain, None

    def with_structured_output(self, schema, **kwargs):
        self.asked = (schema, kwargs)
        return self.chain


def _use(monkeypatch, chain):
    model = _Model(chain)
    monkeypatch.setattr(llm, "get_llm", lambda: model)
    return model


# ---- generate_structured (진짜 함수, 모델만 가짜) ----

def test_structured_returns_parsed_and_tokens(monkeypatch):
    raw = SimpleNamespace(usage_metadata={"input_tokens": 11, "output_tokens": 5})
    chain = _Chain(out={"parsed": _Out(x=1), "raw": raw})
    model = _use(monkeypatch, chain)
    assert REAL_STRUCTURED("sys", "user", _Out) == (_Out(x=1), 11, 5)
    assert model.asked == (_Out, {"include_raw": True})
    assert chain.messages == [("system", "sys"), ("human", "user")]


def test_structured_without_usage_counts_zero(monkeypatch):
    _use(monkeypatch, _Chain(out={"parsed": _Out(x=2), "raw": None}))
    assert REAL_STRUCTURED("s", "u", _Out) == (_Out(x=2), 0, 0)


def test_structured_timeout_is_503(monkeypatch):
    exc = openai.APITimeoutError(request=httpx.Request("POST", "http://internal.example"))
    _use(monkeypatch, _Chain(exc=exc))
    with pytest.raises(ApiError) as e:
        REAL_STRUCTURED("s", "u", _Out)
    assert (e.value.status, e.value.code) == (503, "UPSTREAM_TIMEOUT")
    assert "internal.example" not in e.value.detail


def test_structured_other_error_is_500_and_hides_details(monkeypatch, caplog):
    _use(monkeypatch, _Chain(exc=RuntimeError("secret-internal")))
    with caplog.at_level(logging.INFO, logger="rag"), pytest.raises(ApiError) as e:
        REAL_STRUCTURED("s", "원고-본문-시험", _Out)
    assert (e.value.status, e.value.code) == (500, "INTERNAL_ERROR")
    assert "secret-internal" not in e.value.detail
    # 로그에는 예외 종류와 스키마 이름만 남고, 내부 메시지·요청 내용은 없다
    assert "RuntimeError (_Out)" in caplog.text
    assert "secret-internal" not in caplog.text and "원고-본문-시험" not in caplog.text


def test_structured_parse_failure_is_500(monkeypatch):
    _use(monkeypatch, _Chain(out={"parsed": None, "raw": None}))
    with pytest.raises(ApiError) as e:
        REAL_STRUCTURED("s", "u", _Out)
    assert (e.value.status, e.value.code) == (500, "INTERNAL_ERROR")


# ---- fake_llm 확장 ----

def test_fake_returns_prepared_instance_and_records_call(fake_llm):
    fake_llm.state["structured"][_Out] = _Out(x=7)
    assert llm.generate_structured("sys", "user", _Out) == (_Out(x=7), 100, 20)
    assert llm.generate_structured("sys", "user2", _Out)[0] == _Out(x=7)  # 같은 응답을 반복
    assert [(s, u) for s, u, _ in fake_llm.structured_calls] == [("sys", "user"), ("sys", "user2")]
    assert fake_llm.calls == []  # 답변 초안 호출 기록과 섞이지 않는다


def test_fake_list_pops_in_order_then_fails(fake_llm):
    fake_llm.state["structured"][_Out] = [_Out(x=1), _Out(x=2)]
    assert [llm.generate_structured("s", "u", _Out)[0].x for _ in range(2)] == [1, 2]
    with pytest.raises(AssertionError):
        llm.generate_structured("s", "u", _Out)


def test_fake_function_sees_the_request_and_can_raise(fake_llm):
    def respond(system, user):
        if "실패" in user:
            raise ApiError(500, "INTERNAL_ERROR", "x")
        return _Out(x=len(user))

    fake_llm.state["structured"][_Out] = respond
    assert llm.generate_structured("s", "abc", _Out)[0].x == 3
    with pytest.raises(ApiError):
        llm.generate_structured("s", "실패", _Out)


def test_fake_unprepared_schema_is_an_error(fake_llm):
    with pytest.raises(AssertionError, match="_Out"):
        llm.generate_structured("s", "u", _Out)


def test_fake_tokens_can_be_changed(fake_llm):
    fake_llm.state["structured"][_Out] = _Out(x=1)
    fake_llm.state["structured_tokens"] = (7, 3)
    assert llm.generate_structured("s", "u", _Out)[1:] == (7, 3)


# ---- 공용 함수 이름 ----

def test_shared_helpers_live_in_context_and_old_names_remain():
    assert pipeline._details is context.details_of
    assert pipeline._source_strings is context.source_strings
    assert pipeline.verify_citations is context.verify_citations
    block = context.Block(label="S1", paper_id=1, title="T", page=2, url=None, type="body", texts=["본문"])
    assert context.source_strings([block, block]) == ["T p.2"]
    assert context.details_of([block])[0].snippet == "본문"


# ---- 요청 스키마 ----

def test_rag_request_mode_default_and_values():
    assert RagRequest(question="LoRA란?").mode == "tutor"
    assert RagRequest(question="LoRA란?", mode="prior").mode == "prior"
    with pytest.raises(ValidationError):
        RagRequest(question="LoRA란?", mode="topic")  # 주제·검증은 전용 경로를 쓴다


def test_topic_request_rules():
    assert TopicRequest(paper_ids=[41]).model_dump() == {"paper_ids": [41], "hint": "", "n": 4}
    assert len(TopicRequest(paper_ids=list(range(1, 11))).paper_ids) == 10
    for bad in ({"paper_ids": []}, {"paper_ids": list(range(1, 12))}, {"paper_ids": ["41"]}, {"paper_ids": [True]},
                {"paper_ids": [1.5]}, {"paper_ids": [1], "n": 5}, {"paper_ids": [1], "n": 0},
                {"paper_ids": [1], "hint": "가" * 1001}):
        with pytest.raises(ValidationError):
            TopicRequest(**bad)


def test_verify_request_rules():
    assert VerifyRequest(text="  " + "가" * 10 + "  ").text == "가" * 10  # 앞뒤 공백은 세지 않는다
    assert VerifyRequest(text="가" * 3000).paper_ids is None
    for bad in ({"text": "가" * 9}, {"text": " " * 20}, {"text": "가" * 3001}, {"text": "가" * 10, "paper_ids": [1.5]},
                {"text": "가" * 10, "paper_ids": list(range(51))}):
        with pytest.raises(ValidationError):
            VerifyRequest(**bad)


def test_summary_request_rules():
    assert SummaryRequest(paper_id=41, view="rnd").model_dump() == {"paper_id": 41}  # 예전 클라이언트가 보낸 view는 무시한다
    for bad in ({"paper_id": "41"}, {"paper_id": True}, {}):
        with pytest.raises(ValidationError):
            SummaryRequest(**bad)


def test_validation_error_never_echoes_the_manuscript():
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/v")
    def v(req: VerifyRequest):
        return {"ok": True}

    client = TestClient(app)
    secret = "비공개-원고-문장-" * 400  # 3,000자 초과
    for body in ({"text": secret}, {"text": "짧음-비공개"}):
        r = client.post("/v", json=body)
        assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"
        assert "비공개" not in r.text


# ---- 응답 스키마 ----

def test_rag_response_omits_table_unless_set():
    app = FastAPI()

    @app.get("/plain", response_model=RagResponse)
    def plain():
        return RagResponse(answer="a", level="L2", latency_ms=1)

    @app.get("/prior", response_model=RagResponse)
    def prior():
        return RagResponse(answer="a", level="L2", latency_ms=1, table=[{"paper_id": 1, "title": "T"}])

    c = TestClient(app)
    assert set(c.get("/plain").json()) == {"answer", "sources", "source_details", "needs_review", "handoff", "level", "latency_ms"}
    assert c.get("/prior").json()["table"] == [{"paper_id": 1, "title": "T"}]


def test_response_models_match_the_frontend_shapes():
    topic = TopicResponse(
        limitations=[{"label": "S1", "paper_id": 41, "title": "LoRA", "page": 9, "summary": "랭크를 정해야 한다"}],
        topics=[{"perspective": "limitation_fix", "title": "T", "question": "Q", "approach": "A",
                 "experiment": {"datasets": ["GLUE"], "baselines": ["LoRA"], "metrics": ["평균"]},
                 "based_on": ["S1"], "similar_papers": [{"paper_id": 42, "title": "QLoRA", "score": 0.71}]}],
        latency_ms=5)
    assert topic.topics[0].ai_generated is True and topic.needs_review is True and topic.handoff is False
    verify = VerifyResponse(claims=[{"sentence": "s"}, {"sentence": "t", "verdict": "own_result", "delta": {"vs": "LoRA", "value": 0.9}}],
                            latency_ms=5)
    assert verify.claims[0].verdict == "not_found" and verify.claims[1].delta.value == 0.9 and verify.needs_review is True
    assert SummaryResponse(paper_id=41, title="T", sections=[{"key": "problem", "title": "문제", "text": "..."}],
                           latency_ms=3).sections[0].sources == []
    with pytest.raises(ValidationError):
        Claim(sentence="s", verdict="maybe")


def test_temperature_is_passed_only_when_given(monkeypatch):
    asked = []
    chain = _Chain(out={"parsed": _Out(x=1), "raw": None})
    monkeypatch.setattr(llm, "get_llm", lambda **kw: asked.append(kw) or _Model(chain))
    REAL_STRUCTURED("s", "u", _Out)                        # 정하지 않으면 get_llm()을 인자 없이 부른다(설정값 사용)
    REAL_STRUCTURED("s", "u", _Out, temperature=0.0)
    assert asked == [{}, {"temperature": 0.0}]


def test_get_llm_applies_temperature_but_not_to_reasoning_models(monkeypatch):
    made = []

    class Spy:
        def __init__(self, **kw):
            made.append(kw)

    monkeypatch.setattr(llm, "ChatOpenAI", Spy)
    llm.get_llm.cache_clear()
    llm.get_llm("gpt-4o", None, 0.0)
    llm.get_llm("gpt-4o")
    llm.get_llm("gpt-6-luna", None, 0.0)  # 추론 모델은 온도를 받지 않는다
    llm.get_llm.cache_clear()
    assert [m["temperature"] for m in made] == [0.0, config_rag.LLM_TEMPERATURE, None]
