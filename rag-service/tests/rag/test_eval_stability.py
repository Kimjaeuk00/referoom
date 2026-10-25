"""eval/stability.py: 판정 분포·일치율 집계와 호출 상한을 가짜 서버(httpx.MockTransport)로 시험한다. 네트워크·LLM 없음."""
import json
import sys
from pathlib import Path

import httpx
import pytest

EVAL = Path(__file__).resolve().parents[3] / "eval"
sys.path.insert(0, str(EVAL))

import stability  # noqa: E402

ITEM = {"id": "VF01", "mode": "verify", "type": "verify", "question": "LoRA는 175B에서 매개변수를 10,000배 줄인다고 보고되었다.", "view": "dev",
        "expected_claims": [{"contains": "LoRA", "verdicts": ["match"]}], "should_refuse": False}


def test_distribution_mode_and_agreement():
    got = stability.stability({"a#1": ["match", "match", "mismatch", "match"], "b#1": ["not_found"] * 3})
    assert got["a#1"] == {"n": 4, "distribution": {"match": 3, "mismatch": 1}, "mode": "match", "agreement": 0.75}
    assert got["b#1"]["agreement"] == 1.0 and got["b#1"]["mode"] == "not_found"


def test_tie_picks_the_alphabetically_first_value():
    got = stability.stability({"a#1": ["mismatch", "match", "mismatch", "match"]})["a#1"]
    assert (got["mode"], got["agreement"]) == ("match", 0.5)


def test_summarize_keys_claims_by_position_and_counts_errors():
    out = stability.summarize({"VF01": [["match"], ["match", "not_found"], None, ["mismatch"]]})
    assert out["claims"]["VF01#1"]["distribution"] == {"match": 2, "mismatch": 1}
    assert out["claims"]["VF01#2"]["n"] == 1
    assert out["claim_counts"] == {"VF01": {1: 2, 2: 1}} and out["errors"] == {"VF01": 1}


def fake_server(verdicts, statuses=None):
    seq, st = list(verdicts), list(statuses or [])

    def handler(request):
        if st and (code := st.pop(0)) != 200:
            return httpx.Response(code, json={"detail": "x", "code": "RATE_LIMITED"})
        claims = [{"verdict": v} for v in seq.pop(0)]
        return httpx.Response(200, json={"claims": claims})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_collect_over_a_mixed_fake_server():
    client = fake_server([["match"], ["match"], ["mismatch"], ["bogus"]], [200, 200, 429, 200, 200])
    got = stability.summarize(stability.collect([ITEM], 5, client, "http://rag.test", "t"))
    # 429는 실패, 알 수 없는 판정 값은 error로 센다
    assert got["errors"] == {"VF01": 1}
    assert got["claims"]["VF01#1"]["distribution"] == {"error": 1, "match": 2, "mismatch": 1}


def run_cli(tmp_path, *extra):
    q = tmp_path / "q.jsonl"
    q.write_text(json.dumps(ITEM, ensure_ascii=False) + "\n", encoding="utf-8")
    base = ["--questions", str(q), "--token", "t", "--timeout", "5", "--output-dir", str(tmp_path / "out")]
    return stability.main([*base, *extra])


def test_refuses_without_yes_and_above_max_calls(tmp_path, monkeypatch):
    monkeypatch.setattr(stability.httpx, "Client", lambda **kw: pytest.fail("호출하면 안 된다"))
    assert run_cli(tmp_path, "--repeat", "5", "--max-calls", "10") == 2  # --yes 없음
    assert run_cli(tmp_path, "--repeat", "5", "--max-calls", "4", "--yes") == 2  # 상한 초과


def test_result_file_has_no_manuscript_text(tmp_path, monkeypatch, capsys):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"claims": [{"sentence": ITEM["question"], "verdict": "match"}]}))
    real = httpx.Client
    monkeypatch.setattr(stability.httpx, "Client", lambda **kw: real(transport=transport, **kw))
    assert run_cli(tmp_path, "--repeat", "3", "--max-calls", "3", "--yes") == 0
    text = (tmp_path / "out" / "stability.json").read_text(encoding="utf-8")
    assert "LoRA" not in text and json.loads(text)["claims"]["VF01#1"]["agreement"] == 1.0
    assert "LoRA" not in capsys.readouterr().out
