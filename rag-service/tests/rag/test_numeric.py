"""원고 검증의 숫자 비교(순수 함수). 애매하면 같다고도 다르다고도 하지 않는다."""
import pytest

from app.rag.numeric import compare_values, difference, parse_quantity


@pytest.mark.parametrize("a,b", [
    ("87.2", "87.20"), ("87.2", "87.2%"), ("87.2%", "87.2"), ("0.872", "87.2%"), ("87.2%", "0.872"),
    ("87.2", "87.24"), ("87.24", "87.2"),            # 거친 쪽 정밀도로 반올림하면 같다
    ("0.3M", "300K"), ("300,000", "0.3M"), ("1.5B", "1500M"),
    ("1GB", "1024MB"), ("48GB", "48 GB"), ("10배", "10x"), ("10,000배 줄임", "10,000 times"), ("3×", "3 fold"), ("3배", "3x"),
    ("28.4 BLEU", "28.4"), ("+1.4p", "1.4%"), ("1,234", "1234"), ("0.5", "0.50"),
])
def test_equal_notations(a, b):
    assert compare_values(a, b) == "equal"


@pytest.mark.parametrize("a,b", [
    ("87.2", "87.3"), ("87.2", "88.1"), ("24GB", "48GB"), ("0.3M", "0.4M"), ("0.3M", "350K"), ("300,000", "0.4M"),
    ("87.25", "87.2"),                              # 87.25는 87.3으로 반올림되므로 87.2와 다르다
    ("0.872", "88%"), ("10x", "11배"),
])
def test_different_values(a, b):
    assert compare_values(a, b) == "different"


@pytest.mark.parametrize("a,b", [
    (None, "87.2"), ("87.2", None), ("", "87.2"), ("약 절반", "50%"), ("높다", "낮다"),   # 숫자가 없으면 판단하지 않는다
    ("24GB", "24M"), ("24GB", "24"), ("10배", "10%"), ("0.3", "0.3M"), ("300", "0.3M"),                                     # 단위 종류가 달라 같은 척도로 맞출 수 없다
    ("0.5", "0.5%"), ("0.8", "0.9%"),                                                     # 둘 다 1 이하라 비율인지 퍼센트인지 알 수 없다
])
def test_unsure_is_never_equal_or_different(a, b):
    assert compare_values(a, b) == "unsure"


def test_parse_quantity_reads_units_and_precision():
    q = parse_quantity("약 0.3M개")
    assert (q.value, q.kind, q.decimals) == (300_000.0, "count", 1)
    assert parse_quantity("87.20%").decimals == 2 and parse_quantity("87.20%").kind == "percent"
    assert parse_quantity("2 GB").value == 2 * 1024 ** 3
    assert parse_quantity("BLEU 점수") is None and parse_quantity("") is None and parse_quantity(None) is None
    assert parse_quantity("-3.5").value == -3.5


def test_difference_aligns_notations():
    assert difference("88.1", "87.2") == 0.9
    assert difference("88.1", "87.2%") == 0.9
    assert difference("0.881", "87.2%") == 0.9
    assert difference("86.5", "87.2") == -0.7
    assert difference("0.4M", "300K") == 0.1  # 접미사 단위(M)로 읽는다
    assert difference("24GB", "48GB") == -24.0
    assert difference("88.1", "높음") is None and difference("24GB", "24") is None and difference(None, "1") is None
