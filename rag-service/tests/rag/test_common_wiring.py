"""common-py를 RAG 서비스에 붙인 결과 확인: 오류 형식, 요청 ID, 요청 로그(토큰 수), CORS, level claim 무시."""
import json

import pytest

from conftest import make_token

BODY = {"question": "LoRA는 어떤 파라미터를 학습하나요?"}


def test_auth_errors_use_common_format(client):
    r = client.post("/rag-query", json=BODY)
    assert (r.status_code, r.json()) == (401, {"detail": "로그인이 필요합니다.", "code": "UNAUTHORIZED"})
    assert r.headers["www-authenticate"] == "Bearer"
    bad = client.post("/rag-query", json=BODY, headers={"Authorization": "Bearer not-a-token"})
    assert (bad.status_code, bad.json()["code"]) == (401, "UNAUTHORIZED")


def test_request_id_is_returned_and_kept(client, auth):
    assert client.post("/rag-query", json=BODY, headers=auth).headers["x-request-id"]
    r = client.post("/rag-query", json=BODY, headers={**auth, "X-Request-Id": "req-abc-1"})
    assert r.headers["x-request-id"] == "req-abc-1"


def test_access_log_records_user_team_and_tokens(client, auth, access_log):
    client.post("/rag-query", json=BODY, headers={**auth, "X-Request-Id": "req-log-1"})
    (rec,) = [r for r in access_log if r["request_id"] == "req-log-1"]
    assert (rec["path"], rec["status"], rec["user_id"], rec["team_id"]) == ("/rag-query", 200, 12, 3)
    assert (rec["in_tok"], rec["out_tok"]) == (100, 20)  # 가짜 LLM이 돌려준 사용량
    assert "question" not in rec and "LoRA" not in json.dumps(rec, ensure_ascii=False)  # 질문 원문은 로그에 없다


def test_access_log_for_auth_failure_has_no_user(client, access_log):
    client.post("/rag-query", json=BODY, headers={"X-Request-Id": "req-log-2"})
    (rec,) = [r for r in access_log if r["request_id"] == "req-log-2"]
    assert (rec["status"], rec["user_id"], rec["team_id"]) == (401, None, None)


def test_cors_preflight_from_frontend(client):
    r = client.options(
        "/rag-query",
        headers={"Origin": "http://localhost:5174", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "authorization,content-type"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5174"
    other = client.options("/rag-query", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in other.headers


@pytest.mark.parametrize("legacy", ["L1", "L3", "L4"])
def test_legacy_level_claim_in_token_is_ignored(client, legacy):
    # v0.2: 예전 토큰에 level이 있어도 응답 깊이에 영향을 주지 않는다. 깊이는 요청 body의 level로만 정한다.
    r = client.post("/rag-query", json=BODY, headers={"Authorization": f"Bearer {make_token(level=legacy)}"})
    assert r.status_code == 200
    assert r.json()["level"] == "L2"
