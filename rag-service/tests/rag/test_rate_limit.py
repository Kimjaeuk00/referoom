"""팀당 호출 한도: 슬라이딩 윈도 카운터(가짜 시계)와 비용이 큰 경로 연결. 한도를 넘으면 LLM을 부르기 전에 429 RATE_LIMITED."""
import pytest

from app.rag import rate_limit
from app.rag.rate_limit import SlidingWindowLimiter
from app.rag.schemas import ClaimExtraction
from tests.rag.conftest import make_token


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_passes_up_to_the_limit_then_blocks():
    lim = SlidingWindowLimiter(3, 60, Clock())
    assert [lim.allow(1) for _ in range(4)] == [True, True, True, False]


def test_passes_again_once_the_window_has_passed():
    clock = Clock()
    lim = SlidingWindowLimiter(2, 60, clock)
    assert lim.allow(1) and lim.allow(1) and not lim.allow(1)
    clock.now += 59.9
    assert not lim.allow(1)  # 첫 호출이 아직 창 안에 있다
    clock.now += 0.1
    assert lim.allow(1) and lim.allow(1)  # 정확히 창 길이가 지나면 두 호출 모두 빠진다
    assert not lim.allow(1)


def test_blocked_calls_do_not_extend_the_block():
    clock = Clock()
    lim = SlidingWindowLimiter(1, 60, clock)
    assert lim.allow(1)
    clock.now += 30
    assert not lim.allow(1)  # 막힌 호출은 기록하지 않는다
    clock.now += 30
    assert lim.allow(1)


def test_teams_are_counted_separately():
    lim = SlidingWindowLimiter(1, 60, Clock())
    assert lim.allow(3) and not lim.allow(3)
    assert lim.allow(4)


@pytest.mark.parametrize("limit", [0, -1])
def test_zero_or_negative_limit_is_off(limit):
    lim = SlidingWindowLimiter(limit, 60, Clock())
    assert all(lim.allow(1) for _ in range(100))


def test_check_team_raises_429_rate_limited(monkeypatch):
    monkeypatch.setattr(rate_limit, "limiter", SlidingWindowLimiter(1, 60, Clock()))
    rate_limit.check_team(3)
    with pytest.raises(rate_limit.ApiError) as e:
        rate_limit.check_team(3)
    assert (e.value.status, e.value.code) == (429, "RATE_LIMITED")
    rate_limit.check_team(4)


# ---- 경로 연결 ----

@pytest.fixture()
def one_call(monkeypatch):
    monkeypatch.setattr(rate_limit, "limiter", SlidingWindowLimiter(1, 60, Clock()))


def bodies():
    return {
        "/summary": {"paper_id": 999},
        "/topic-suggest": {"paper_ids": [999]},
        "/verify": {"text": "우리 방법은 GLUE에서 평균 88.5점을 얻었다."},
        "/rag-query (prior)": {"question": "LoRA와 비슷한 선행연구를 비교해 줘", "mode": "prior"},
    }


@pytest.mark.parametrize("name", list(bodies()))
def test_costly_paths_are_blocked_before_the_llm(name, client, auth, fake_llm, one_call):
    path = name.split(" ")[0]
    body = bodies()[name]
    fake_llm.state["structured"][ClaimExtraction] = ClaimExtraction(claims=[])  # /verify의 첫 호출만 쓴다
    first = client.post(path, json=body, headers=auth)
    assert first.status_code != 429
    llm_calls = (len(fake_llm.calls), len(fake_llm.structured_calls))
    second = client.post(path, json=body, headers=auth)
    assert second.status_code == 429 and second.json() == {"detail": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.", "code": "RATE_LIMITED"}
    assert (len(fake_llm.calls), len(fake_llm.structured_calls)) == llm_calls


def test_paths_share_one_budget_per_team(client, auth, fake_llm, one_call):
    assert client.post("/summary", json={"paper_id": 999}, headers=auth).status_code != 429
    assert client.post("/verify", json=bodies()["/verify"], headers=auth).status_code == 429


def test_other_team_is_not_affected(client, auth, fake_llm, one_call):
    assert client.post("/summary", json={"paper_id": 999}, headers=auth).status_code != 429
    assert client.post("/summary", json={"paper_id": 999}, headers=auth).status_code == 429
    other = {"Authorization": f"Bearer {make_token(team_id=4)}"}
    assert client.post("/summary", json={"paper_id": 999}, headers=other).status_code != 429


def test_tutor_questions_are_never_limited(client, auth, fake_llm, one_call):
    body = {"question": "LoRA는 무엇을 학습하나요?"}
    assert [client.post("/rag-query", json=body, headers=auth).status_code for _ in range(4)] == [200] * 4
    # 튜터 호출이 선행연구 한도를 쓰지도 않는다
    assert client.post("/rag-query", json={**body, "mode": "prior"}, headers=auth).status_code != 429


def test_default_is_off(client, auth, fake_llm):
    from app.rag import config_rag

    assert config_rag.RATE_LIMIT_CALLS == 0
    assert all(client.post("/summary", json={"paper_id": 999}, headers=auth).status_code == 404 for _ in range(5))
