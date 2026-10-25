"""v0.2 모드(선행연구·주제·검증·요약)가 함께 쓰는 보조 함수."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Callable, TypeVar

from app.rag.context import LABEL_RE, Block
from app.rag.errors import ApiError

logger = logging.getLogger("rag")
T = TypeVar("T")
R = TypeVar("R")


def map_safe(fn: Callable[[T], R], items: list[T], workers: int) -> list[tuple[R | None, ApiError | None]]:
    """items를 스레드 풀로 병렬 처리한다. 반환: 입력 순서대로 (결과, 오류) — 한 항목이 실패해도 나머지는 계속한다.

    ApiError는 그대로 돌려주고, 예상하지 못한 예외는 내용을 남기지 않고 종류만 기록한 뒤 500 INTERNAL_ERROR로 바꾼다.
    """
    def call(item: T):
        try:
            return fn(item), None
        except ApiError as e:
            return None, e
        except Exception as e:
            logger.error("mode worker failed: %s", type(e).__name__)
            return None, ApiError(500, "INTERNAL_ERROR", "답변을 생성하지 못했어요. 잠시 후 다시 시도해 주세요.")

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        return list(pool.map(call, items))


def adopt_block(used: list[Block], block: Block) -> str:
    """블록에 응답 전체에서 쓰는 전역 라벨(S1..)을 새로 붙여 used에 더하고 그 라벨을 돌려준다."""
    label = f"S{len(used) + 1}"
    used.append(replace(block, label=label))
    return label


_SPACE_RE = re.compile(r"\s+")


def clean_text(value: str | None, max_chars: int) -> str | None:
    """LLM이 쓴 문자열 정리: 값 안의 [S#] 표시 제거(근거는 라벨 필드로만 잇는다), 공백 정리, 길이 상한. 비면 None."""
    if not value:
        return None
    text = _SPACE_RE.sub(" ", LABEL_RE.sub("", value)).strip()
    return text[:max_chars] if text else None
