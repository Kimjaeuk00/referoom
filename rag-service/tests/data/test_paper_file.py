"""GET /papers/{id}/file: 팀이 보관한 원문 PDF를 내려준다. 팀 격리와 응답 헤더를 시험한다 (실제 Zotero·모델·네트워크 없음)."""
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app.rag import config_rag

PAPER = 434253507605
TEAM, OTHER_TEAM = 3, 4
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def headers(**overrides) -> dict:
    now = int(time.time())
    claims = {"iss": "simple-auth-server", "sub": "12", "username": "tester", "role": "member", "team_id": TEAM,
              "team_type": "dev", "view": "rnd", "iat": now, "exp": now + 3600, **overrides}
    if claims["team_id"] is None and "team_type" not in overrides:
        claims["team_type"] = None
    claims = {k: v for k, v in claims.items() if v is not None or k in ("team_id", "team_type")}
    return {"Authorization": "Bearer " + jwt.encode(claims, "test-secret-0123456789-abcdefghijklmnop", algorithm="HS256")}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app.main import app

    monkeypatch.setattr(config_rag, "STORE_BACKEND", "local")
    monkeypatch.setattr(config_rag, "PDF_DIR", tmp_path / "pdfs")
    (tmp_path / "pdfs" / str(TEAM)).mkdir(parents=True)
    (tmp_path / "pdfs" / str(TEAM) / f"{PAPER}.pdf").write_bytes(PDF)
    return TestClient(app)


def test_same_team_gets_the_pdf_with_safe_headers(client):
    r = client.get(f"/papers/{PAPER}/file", headers=headers())
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content == PDF and r.content.startswith(b"%PDF")
    assert r.headers["content-disposition"] == 'inline; filename="paper.pdf"'  # 제목·경로 없음
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "private, max-age=300"
    assert str(PAPER) not in r.headers["content-disposition"]


def test_other_team_cannot_see_it_and_cannot_tell_it_exists(client):
    other = client.get(f"/papers/{PAPER}/file", headers=headers(team_id=OTHER_TEAM))
    missing = client.get("/papers/999/file", headers=headers(team_id=OTHER_TEAM))
    assert other.status_code == 404 and other.json()["code"] == "NOT_FOUND"
    assert other.json() == missing.json()  # 없는 논문과 똑같이 응답한다


def test_missing_file_is_404(client):
    r = client.get("/papers/12345/file", headers=headers())
    assert r.status_code == 404 and r.json() == {"detail": "논문을 찾을 수 없습니다.", "code": "NOT_FOUND"}


@pytest.mark.parametrize("paper_id", [0, -1, -434253507605])
def test_non_positive_ids_are_404(client, paper_id):
    assert client.get(f"/papers/{paper_id}/file", headers=headers()).status_code == 404


def test_requires_login_and_team(client):
    assert client.get(f"/papers/{PAPER}/file").status_code == 401
    r = client.get(f"/papers/{PAPER}/file", headers=headers(team_id=None))
    assert r.status_code == 403 and r.json()["code"] == "NO_TEAM"


def test_non_numeric_id_is_a_validation_error_without_echoing_input(client):
    r = client.get("/papers/..%2F..%2Fetc%2Fpasswd/file", headers=headers())
    assert r.status_code in (404, 422)
    assert "passwd" not in r.text
