import json
import logging
import os
import sys
import time
from pathlib import Path

# 앱 import 전에 설정해야 한다
os.environ["JWT_SECRET"] = "test-secret-0123456789-abcdefghijklmnop"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient
import jwt  # PyJWT (common-py와 같은 라이브러리)


def make_token(**overrides) -> str:
    """인증서버가 발급하는 claim 집합(v0.2: level 없음). 값이 None인 claim은 빼되, 팀 미가입은 team_id·team_type이 둘 다 null로 들어간다."""
    claims = {
        "iss": "simple-auth-server",
        "sub": "12",
        "username": "tester",
        "role": "member",
        "team_id": 3,
        "team_type": "dev",
        "view": "rnd",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    claims.update(overrides)
    if claims["team_id"] is None and "team_type" not in overrides:
        claims["team_type"] = None
    return jwt.encode({k: v for k, v in claims.items() if v is not None or k in ("team_id", "team_type")}, "test-secret-0123456789-abcdefghijklmnop", algorithm="HS256")


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    """실제 LLM을 호출하지 않는다. calls에 (system, user, images) 호출 기록을 남긴다.
    state["drafts"]에 목록을 넣으면 호출 순서대로 돌려준다 (이미지 재시도 시험용).

    모드별 구조화 호출(llm.generate_structured)도 가짜로 바꾼다. 응답은 스키마 클래스별로 state["structured"]에 준비한다:
      state["structured"][스키마] = 응답 인스턴스        # 호출마다 같은 응답
                                  = [응답, ...]          # 호출 순서대로 꺼낸다 (다 쓰면 AssertionError)
                                  = 함수(system, user)   # 호출 내용에 따라 응답하거나 ApiError 같은 예외를 던진다
    준비하지 않은 스키마로 부르면 AssertionError로 알린다(예상하지 못한 LLM 호출을 잡는다). 호출 기록은 structured_calls."""
    from app.rag import llm
    from app.rag.schemas import AnswerDraft

    calls = []
    state = {"draft": AnswerDraft(found=True, answer="사전학습 가중치는 고정하고 저랭크 행렬만 학습합니다 [S1]", cited=["S1"])}

    def generate(system, user, images=None):
        calls.append((system, user, images))
        drafts = state.get("drafts")
        return (drafts.pop(0) if drafts else state["draft"]), 100, 20

    structured_calls = []
    state["structured"] = {}
    state["structured_tokens"] = (100, 20)

    structured_temps = []

    def generate_structured(system, user, schema, temperature=None):
        structured_calls.append((system, user, schema))
        structured_temps.append(temperature)  # 추출·판독 호출은 낮은 온도를 쓴다(structured_temps로 확인)
        prepared = state["structured"].get(schema)
        if prepared is None:
            raise AssertionError(f"준비하지 않은 구조화 LLM 호출: {schema.__name__}")
        if callable(prepared):
            out = prepared(system, user)
        elif isinstance(prepared, list):
            if not prepared:
                raise AssertionError(f"{schema.__name__} 응답을 모두 사용했다")
            out = prepared.pop(0)
        else:
            out = prepared
        return out, *state["structured_tokens"]

    monkeypatch.setattr(llm, "generate", generate)
    monkeypatch.setattr(llm, "generate_structured", generate_structured)
    generate.calls = calls
    generate.state = state
    generate.structured_calls = structured_calls
    generate.structured_temps = structured_temps
    return generate


@pytest.fixture()
def access_log():
    """공통 요청 로그(JSON 한 줄)를 모은다. 이 로거는 전파되지 않아 caplog로는 못 받는다."""
    records: list[dict] = []

    class Collect(logging.Handler):
        def emit(self, record):
            records.append(json.loads(record.getMessage()))

    logger = logging.getLogger("referoom_common.access")
    handler = Collect()
    logger.addHandler(handler)
    yield records
    logger.removeHandler(handler)


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def auth():
    return {"Authorization": f"Bearer {make_token()}"}
