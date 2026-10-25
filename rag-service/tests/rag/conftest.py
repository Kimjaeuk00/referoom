import os
import sys
import time
from pathlib import Path

# 앱 import 전에 설정해야 한다
os.environ["JWT_SECRET"] = "test-secret"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from fastapi.testclient import TestClient
from jose import jwt


def make_token(**overrides) -> str:
    claims = {
        "iss": "simple-auth-server",
        "sub": "12",
        "team_id": 3,
        "level": "L1",
        "view": "rnd",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    claims.update(overrides)
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, "test-secret", algorithm="HS256")


@pytest.fixture(autouse=True)
def fake_llm(monkeypatch):
    """실제 LLM을 호출하지 않는다. calls에 (system, user, images) 호출 기록을 남긴다.
    state["drafts"]에 목록을 넣으면 호출 순서대로 돌려준다 (이미지 재시도 시험용)."""
    from app.rag import llm
    from app.rag.schemas import AnswerDraft

    calls = []
    state = {"draft": AnswerDraft(found=True, answer="사전학습 가중치는 고정하고 저랭크 행렬만 학습합니다 [S1]", cited=["S1"])}

    def generate(system, user, images=None):
        calls.append((system, user, images))
        drafts = state.get("drafts")
        return (drafts.pop(0) if drafts else state["draft"]), 100, 20

    monkeypatch.setattr(llm, "generate", generate)
    generate.calls = calls
    generate.state = state
    return generate


@pytest.fixture()
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture()
def auth():
    return {"Authorization": f"Bearer {make_token()}"}
