from app.rag import config_rag, pipeline
from app.rag.store_stub import Hit

from conftest import make_token

BODY = {"question": "LoRA는 어떤 파라미터를 학습하나요?"}
RESPONSE_KEYS = {
    "answer", "sources", "source_details", "needs_review", "handoff", "level", "view", "latency_ms",
}


def test_no_token_is_401(client):
    r = client.post("/rag-query", json=BODY)
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHORIZED"


def test_expired_token_is_401(client):
    r = client.post("/rag-query", json=BODY, headers={"Authorization": f"Bearer {make_token(exp=1)}"})
    assert r.status_code == 401
    assert r.json()["code"] == "TOKEN_EXPIRED"


def test_token_without_team_is_403(client):
    r = client.post("/rag-query", json=BODY, headers={"Authorization": f"Bearer {make_token(team_id=None)}"})
    assert r.status_code == 403
    assert r.json()["code"] == "NO_TEAM"


def test_ok_matches_schema(client, auth):
    r = client.post("/rag-query", json=BODY, headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert set(data) == RESPONSE_KEYS
    assert data["sources"] == ["LoRA: Low-Rank Adaptation of Large Language Models p.1"]
    assert data["source_details"][0]["label"] == "S1"
    assert data["handoff"] is False


def test_level_default_is_standard_depth_and_view_from_jwt(client, auth):
    # v0.2: JWT에는 level이 없다. 요청이 level을 보내지 않으면 기본 깊이(L2)이고 view는 JWT 값을 따른다.
    d = client.post("/rag-query", json=BODY, headers=auth).json()
    assert (d["level"], d["view"]) == ("L2", "rnd")
    d = client.post("/rag-query", json={**BODY, "level": "L3", "view": "dev"}, headers=auth).json()
    assert (d["level"], d["view"]) == ("L3", "dev")


def test_body_team_id_is_ignored(client, auth, monkeypatch):
    seen = {}

    def fake_search(team_id, *a, **k):
        seen["team_id"] = team_id
        return []

    monkeypatch.setattr(pipeline.store, "search", fake_search)
    client.post("/rag-query", json={**BODY, "team_id": 999}, headers=auth)
    assert seen["team_id"] == 3


def test_below_min_score_is_handoff(client, auth, monkeypatch):
    low = Hit(text="x", score=config_rag.MIN_SCORE - 0.01, metadata={"title": "t", "page": 1})
    monkeypatch.setattr(pipeline.store, "search", lambda *a, **k: [low])
    d = client.post("/rag-query", json=BODY, headers=auth).json()
    assert d["handoff"] is True and d["sources"] == []


def test_validation_error_does_not_echo_question(client, auth):
    r = client.post("/rag-query", json={"question": "a"}, headers=auth)
    assert r.status_code == 422
    assert set(r.json()) == {"detail", "code"}  # 입력 원문을 반환하지 않는다
    assert r.json()["code"] == "VALIDATION_ERROR"
    assert client.post("/rag-query", json={**BODY, "top_k": 11}, headers=auth).status_code == 422


def test_health_needs_no_auth(client):
    assert client.get("/health").status_code == 200
