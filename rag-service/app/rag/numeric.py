"""원고 검증의 숫자 비교 (순수 함수, LLM·색인과 무관).

판정은 LLM이 아니라 이 모듈이 한다. 표기가 달라도 같은 값이면 같다고 보고(87.2 = 87.20 = 87.2%, 0.872 ↔ 87.2%, 0.3M = 300K,
1GB = 1024MB), 단위 종류가 다르거나 어느 쪽인지 알 수 없으면 같다고도 다르다고도 하지 않고 "unsure"로 돌려준다.
호출하는 쪽은 unsure를 '조건 다름'으로 다룬다(애매할 때는 일치로 내보내지 않는다).
"""
import re
from dataclasses import dataclass

_NUMBER_RE = re.compile(r"([+-]?\d[\d,]*(?:\.\d+)?)\s*(%p|pp|%|p|kb|mb|gb|tb|times|fold|k|m|b|x|×|배)?(?![a-z])", re.IGNORECASE)

_SCALES = {"k": 1e3, "m": 1e6, "b": 1e9}
_MEMORY = {"kb": 1024.0, "mb": 1024.0 ** 2, "gb": 1024.0 ** 3, "tb": 1024.0 ** 4}
_EPS = 1e-9


@dataclass(frozen=True)
class Quantity:
    value: float      # 단위를 풀어 쓴 값 (0.3M → 300000, 2GB → 2147483648, 87.2% → 87.2)
    kind: str         # plain | percent | count | memory | times
    decimals: int     # 쓴 소수 자릿수 (정밀도)
    scale: float      # 접미사 배율 (정밀도를 값의 크기로 바꿀 때 쓴다)


def parse_quantity(text: str | None) -> Quantity | None:
    """문자열에서 첫 숫자를 읽는다. 숫자가 없으면 None. 알 수 없는 영문 단어(BLEU 등)는 값에 영향이 없다."""
    if not text:
        return None
    m = _NUMBER_RE.search(text)
    if not m:
        return None
    literal = m.group(1).replace(",", "")
    unit = (m.group(2) or "").lower()
    decimals = len(literal.split(".")[1]) if "." in literal else 0
    value = float(literal)
    if unit in ("%", "%p", "pp", "p"):
        return Quantity(value, "percent", decimals, 1.0)
    if unit in _SCALES:
        return Quantity(value * _SCALES[unit], "count", decimals, _SCALES[unit])
    if unit in _MEMORY:
        return Quantity(value * _MEMORY[unit], "memory", decimals, _MEMORY[unit])
    if unit in ("x", "×", "배", "times", "fold"):
        return Quantity(value, "times", decimals, 1.0)
    return Quantity(value, "plain", decimals, 1.0)


def _tolerance(q: Quantity, decimals: int | None = None) -> float:
    """쓴 정밀도의 반올림 폭의 절반 (87.2 → 0.05)."""
    d = q.decimals if decimals is None else decimals
    return 0.5 * 10 ** (-d) * q.scale


def _aligned(a: Quantity, b: Quantity) -> tuple[float, float, float] | None:
    """두 값을 같은 척도로 맞춘다. 반환: (a, b, 허용 오차). 비교할 수 없으면 None.

    - 종류가 같으면 그대로
    - 퍼센트와 일반 숫자: 일반 숫자가 1보다 크면 같은 척도(87.2 ↔ 87.2%), 0~1이고 퍼센트 값이 1보다 크면 비율(0.872 ↔ 87.2%),
      둘 다 1 이하라 척도를 알 수 없으면 None
    - 일반 숫자와 개수(M·K·B): 일반 숫자가 1,000 이상이면 풀어 쓴 개수로 보고 비교(300,000 ↔ 0.3M). 그보다 작으면 접미사를 빼고 쓴 것인지
      알 수 없으므로 None
    - 그 밖의 종류 차이(메모리와 개수 등)는 None
    """
    if a.kind == b.kind:
        return a.value, b.value, max(_tolerance(a), _tolerance(b))
    kinds = {a.kind, b.kind}
    if kinds == {"plain", "count"}:
        plain = a if a.kind == "plain" else b
        if plain.value < 1000:
            return None  # 접미사를 빼고 쓴 값인지(0.3 ↔ 0.3M) 알 수 없다
        return a.value, b.value, max(_tolerance(a), _tolerance(b))
    if kinds != {"percent", "plain"}:
        return None
    plain, pct = (a, b) if a.kind == "plain" else (b, a)
    if plain.value > 1:
        x, y, tol = plain.value, pct.value, max(_tolerance(plain), _tolerance(pct))
    elif 0 <= plain.value <= 1 and pct.value > 1:
        x, y = plain.value * 100, pct.value
        tol = max(_tolerance(plain, max(plain.decimals - 2, 0)), _tolerance(pct))
    else:
        return None
    return (x, y, tol) if a is plain else (y, x, tol)


def compare_values(claimed: str | None, found: str | None) -> str:
    """두 값을 비교한다. 반환: 'equal' | 'different' | 'unsure'.

    같다고 보는 기준은 둘 중 거친 쪽 정밀도로 반올림했을 때 같은 값이다 (87.2와 87.24는 같고, 87.2와 87.3은 다르다).
    숫자를 읽을 수 없거나 단위 종류가 달라 같은 척도로 맞출 수 없으면 'unsure'.
    """
    qa, qb = parse_quantity(claimed), parse_quantity(found)
    if qa is None or qb is None:
        return "unsure"
    aligned = _aligned(qa, qb)
    if aligned is None:
        return "unsure"
    x, y, tol = aligned
    diff = abs(x - y)
    return "equal" if diff < _EPS or diff < tol - _EPS else "different"


def difference(claimed: str | None, found: str | None) -> float | None:
    """claimed - found (같은 척도로 맞춘 값, 소수 둘째 자리까지). 맞출 수 없으면 None. 본인 결과와 선행 값의 차이에 쓴다."""
    qa, qb = parse_quantity(claimed), parse_quantity(found)
    if qa is None or qb is None:
        return None
    aligned = _aligned(qa, qb)
    if aligned is None:
        return None
    x, y, _ = aligned
    # 개수·메모리처럼 접미사로 척도가 큰 값은 접미사 단위로 되돌려 사람이 읽는 크기로 둔다
    unit = qa.scale if qa.kind in ("count", "memory") else 1.0
    return round((x - y) / unit, 2)
