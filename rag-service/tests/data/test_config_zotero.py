import pytest

from app.rag import config_rag


@pytest.mark.parametrize("raw, expected", [("6731353", 6731353), ("  42 ", 42), ("", None), ("abc", None), ("-5", None), ("0", None), (None, None)])
def test_optional_int(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("ZOTERO_TEST_VALUE", raising=False)
    else:
        monkeypatch.setenv("ZOTERO_TEST_VALUE", raw)
    assert config_rag._optional_int("ZOTERO_TEST_VALUE") == expected


def test_zotero_defaults_are_typed():
    assert config_rag.ZOTERO_GROUP_ID is None or isinstance(config_rag.ZOTERO_GROUP_ID, int)
    assert config_rag.ZOTERO_API_KEY is None or isinstance(config_rag.ZOTERO_API_KEY, str)
    assert isinstance(config_rag.ZOTERO_TEAM_ID, int) and config_rag.ZOTERO_TEAM_ID > 0
