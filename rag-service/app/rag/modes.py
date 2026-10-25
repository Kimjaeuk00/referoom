"""v0.2 모드(선행연구·주제·검증·요약)가 함께 쓰는 보조 함수."""
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Callable, TypeVar

from app.rag.context import LABEL_RE, Block
from app.rag.deps import store
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


def gather_evidence(team_id: int, paper_id: int, queries, total: int, lead: int = 0, per_query: int | None = None) -> list:
    """한 논문의 근거 청크. 앞쪽 lead개(위치, 제목·초록·서론)에 질의별 상위 청크를 번갈아 더하고 중복은 뺀다. 쪽 순서로 돌려준다.

    total은 청크 합계 상한이고, per_query는 질의마다 가져올 상위 개수(기본: 남은 자리 수)다.
    """
    chosen = list(store.lead_chunks(team_id, paper_id, k=lead)) if lead > 0 else []
    seen = {(h.metadata.get("page"), h.text[:80]) for h in chosen}
    budget = total - len(chosen)
    k = per_query if per_query is not None else budget
    if budget > 0 and k > 0:
        per = [store.chunks_of_paper(team_id, paper_id, q, k=k) for q in queries]
        for rank in range(k):
            for hits in per:
                if rank < len(hits) and len(chosen) < total:
                    h = hits[rank]
                    key = (h.metadata.get("page"), h.text[:80])
                    if key not in seen:
                        seen.add(key)
                        chosen.append(h)
    return sorted(chosen, key=lambda h: h.metadata.get("page") or 0)
