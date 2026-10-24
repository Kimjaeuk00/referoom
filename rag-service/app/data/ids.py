"""Zotero 항목 키 ↔ paper_id 변환.

Zotero 키(영문 대문자·숫자 8자리)를 36진 정수로 바꿔 paper_id로 쓴다. 매핑 파일 없이 항상 같은 값이 나오고,
최대값 36**8-1 ≈ 2.8e12 < 2**53 이라 JSON·JavaScript에서도 정확하다.
"""
import re

_KEY = re.compile(r"[A-Z0-9]{8}")
_BASE = 36
_MAX_ID = _BASE**8 - 1
_DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def paper_id_from_key(key: str) -> int:
    """Zotero 키 → paper_id. 형식이 다르거나 0이면 ValueError."""
    if not isinstance(key, str) or _KEY.fullmatch(key) is None:
        raise ValueError("Zotero 항목 키는 영문 대문자·숫자 8자리여야 합니다.")
    value = int(key, _BASE)
    if value == 0:
        raise ValueError("유효하지 않은 Zotero 항목 키입니다.")
    return value


def key_from_paper_id(paper_id: int) -> str:
    """paper_id → Zotero 키. 범위를 벗어나면 ValueError."""
    if type(paper_id) is not int or not 1 <= paper_id <= _MAX_ID:
        raise ValueError("유효한 paper_id가 아닙니다.")
    digits = []
    while paper_id:
        paper_id, rest = divmod(paper_id, _BASE)
        digits.append(_DIGITS[rest])
    return "".join(reversed(digits)).rjust(8, "0")
