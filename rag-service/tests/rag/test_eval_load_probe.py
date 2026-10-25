"""eval/load_probe.py: 집계 함수, 동시 수 제한, LLM 경로 보호를 가짜 서버로 시험한다. 네트워크·LLM 없음."""
import asyncio
import sys
from pathlib import Path

import httpx
import pytest

EVAL = Path(__file__).resolve().parents[3] / "eval"
sys.path.insert(0, str(EVAL))

import load_probe  # noqa: E402


def test_aggregate_uses_ceil_n_times_095_for_p95():
    got = load_probe.aggregate([float(i) for i in range(1, 21)])  # 1..20
    assert got == {"n": 20, "mean": 10.5, "max": 20.0, "p95": 19.0}  # ceil(20 x 0.95) = 19번째
    assert load_probe.aggregate([5.0])["p95"] == 5.0
    assert load_probe.aggregate([3.0, 1.0, 2.0, 9.0])["p95"] == 9.0  # 정렬 후 ceil(3.8) = 4번째


def test_run_level_never_exceeds_the_concurrency_and_counts_statuses():
    active = peak = 0

    async def handler(request):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200 if request.url.path == "/health" else 500)

    async def go(path):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://t") as client:
            return await load_probe.run_level(client, ("GET", path, None), 4, 12, {})

    ok = asyncio.run(go("/health"))
    assert peak <= 4 and peak > 1 and ok["n"] == 12 and ok["statuses"] == {200: 12}
    assert asyncio.run(go("/x"))["statuses"] == {500: 12}


def test_connection_errors_are_counted_as_status_zero():
    def boom(request):
        raise httpx.ConnectError("x")

    async def go():
        async with httpx.AsyncClient(transport=httpx.MockTransport(boom), base_url="http://t") as client:
            return await load_probe.run_level(client, ("GET", "/health", None), 2, 3, {})

    assert asyncio.run(go())["statuses"] == {0: 3}


def test_llm_path_needs_both_flags(monkeypatch):
    monkeypatch.setattr(load_probe.asyncio, "run", lambda coro: coro.close() or pytest.fail("호출하면 안 된다"))
    assert load_probe.main(["--token", "t", "--timeout", "5", "--llm"]) == 2
    assert load_probe.main(["--token", "t", "--timeout", "5", "--requests", "0"]) == 2


def test_default_paths_do_not_include_the_llm_route():
    assert all(route != load_probe.LLM_PATH for route in load_probe.PATHS.values())
    assert load_probe.LLM_CONCURRENCY == 3
