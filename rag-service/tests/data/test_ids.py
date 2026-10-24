import pytest

from app.data.ids import key_from_paper_id, paper_id_from_key


@pytest.mark.parametrize("key", ["263A8NW8", "V3HSB2SA", "4RDQ4ID6", "ZZZZZZZZ", "00000001"])
def test_roundtrip(key):
    assert key_from_paper_id(paper_id_from_key(key)) == key


def test_known_values_and_js_safe_range():
    assert paper_id_from_key("0000000A") == 10
    assert key_from_paper_id(10) == "0000000A"
    # JSON·JavaScript에서 정확히 표현되는 정수여야 한다
    assert paper_id_from_key("ZZZZZZZZ") < 2**53


@pytest.mark.parametrize("key", ["", "abc12345", "ABC1234", "ABC123456", "ABC-1234", "00000000", None, 12345678])
def test_invalid_key(key):
    with pytest.raises(ValueError):
        paper_id_from_key(key)


@pytest.mark.parametrize("paper_id", [0, -1, 36**8, True, "10", 1.5, None])
def test_invalid_paper_id(paper_id):
    with pytest.raises(ValueError):
        key_from_paper_id(paper_id)
