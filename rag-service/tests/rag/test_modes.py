"""v0.2 모드 공용 함수: 근거 모으기(gather_evidence), 병렬 실행(map_safe), 텍스트 정리, 묶음 인용 정리."""
import pytest

from app.rag import modes
from app.rag.context import split_label_groups
from app.rag.errors import ApiError
from app.rag.store_stub import Hit


def hit(page, text):
    return Hit(text=text, score=0.5, metadata={"paper_id": 1, "page": page})


@pytest.fixture()
def fake_store(monkeypatch):
    calls = {"lead": [], "queries": []}
    data = {"lead": [], "by_query": {}}
    monkeypatch.setattr(modes.store, "lead_chunks", lambda team_id, pid, k=3: calls["lead"].append(k) or data["lead"][:k])
    monkeypatch.setattr(modes.store, "chunks_of_paper",
                        lambda team_id, pid, q, k=4: calls["queries"].append((q, k)) or data["by_query"].get(q, [])[:k])
    return calls, data


def test_lead_then_queries_interleaved_deduplicated_and_sorted_by_page(fake_store):
    calls, data = fake_store
    data["lead"] = [hit(1, "초록"), hit(1, "서론")]
    data["by_query"] = {"a": [hit(5, "A1"), hit(1, "초록"), hit(9, "A3")], "b": [hit(2, "B1"), hit(7, "B2")]}
    got = modes.gather_evidence(3, 1, ["a", "b"], total=5, lead=2)
    # 앞쪽 2개 + 남은 3자리를 질의 a·b의 1순위부터 번갈아(A1, B1) 채우고, 중복('초록')은 건너뛰어 다음 순위(B2)로
    assert [h.text for h in got] == ["초록", "서론", "B1", "A1", "B2"]  # 쪽 순서(1,1,2,5,7)
    assert calls["lead"] == [2] and calls["queries"] == [("a", 3), ("b", 3)]


def test_total_is_a_hard_cap(fake_store):
    _, data = fake_store
    data["lead"] = [hit(1, "L")]
    data["by_query"] = {"a": [hit(i, f"A{i}") for i in range(2, 9)], "b": [hit(i, f"B{i}") for i in range(2, 9)]}
    assert len(modes.gather_evidence(3, 1, ["a", "b"], total=4, lead=1)) == 4


def test_without_lead_the_store_is_not_asked_for_lead_chunks(fake_store):
    calls, data = fake_store
    data["by_query"] = {"a": [hit(3, "A")]}
    assert [h.text for h in modes.gather_evidence(3, 1, ["a"], total=2)] == ["A"]
    assert calls["lead"] == []


def test_no_budget_left_means_no_queries(fake_store):
    calls, data = fake_store
    data["lead"] = [hit(1, "L1"), hit(2, "L2")]
    assert len(modes.gather_evidence(3, 1, ["a"], total=2, lead=2)) == 2
    assert calls["queries"] == []


def test_per_query_overrides_the_default_count(fake_store):
    calls, data = fake_store
    data["by_query"] = {"a": [hit(1, "A1"), hit(2, "A2"), hit(3, "A3")], "b": [hit(4, "B1"), hit(5, "B2")]}
    got = modes.gather_evidence(3, 1, ["a", "b"], total=10, per_query=2)
    assert calls["queries"] == [("a", 2), ("b", 2)] and [h.text for h in got] == ["A1", "A2", "B1", "B2"]


# ---- map_safe / clean_text / adopt_block ----

def test_map_safe_keeps_order_and_isolates_failures(caplog):
    def fn(x):
        if x == 2:
            raise ApiError(503, "UPSTREAM_TIMEOUT", "x")
        if x == 3:
            raise RuntimeError("비공개-내부-메시지")
        return x * 10

    out = modes.map_safe(fn, [1, 2, 3, 4], workers=3)
    assert [r for r, _ in out] == [10, None, None, 40]
    assert out[1][1].code == "UPSTREAM_TIMEOUT" and out[2][1].status == 500 and out[0][1] is None
    assert "비공개" not in caplog.text and "RuntimeError" in caplog.text and "비공개" not in out[2][1].detail


def test_clean_text_strips_labels_spaces_and_caps():
    assert modes.clean_text("저랭크   행렬 [S2]\n만 학습 [S10]", 100) == "저랭크 행렬 만 학습"
    assert modes.clean_text("가나다라마바사", 3) == "가나다"
    assert modes.clean_text("  [S1]  ", 10) is None and modes.clean_text(None, 10) is None and modes.clean_text("", 10) is None


# ---- 묶음 인용 ----

@pytest.mark.parametrize("raw,fixed", [
    ("값이 같다 [S1, S2].", "값이 같다 [S1] [S2]."),
    ("[S1,S2,S3]", "[S1] [S2] [S3]"),
    ("[S1 , S2]", "[S1] [S2]"),
    ("[S1，S2]", "[S1] [S2]"),            # 전각 쉼표
    ("이미 풀어 쓴 [S1] [S2]와 단일 [S3]", "이미 풀어 쓴 [S1] [S2]와 단일 [S3]"),
    ("라벨이 아닌 [참고, 2020]과 [1, 2]", "라벨이 아닌 [참고, 2020]과 [1, 2]"),
    ("", ""),
])
def test_split_label_groups(raw, fixed):
    assert split_label_groups(raw) == fixed
