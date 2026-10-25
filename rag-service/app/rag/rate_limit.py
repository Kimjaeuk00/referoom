"""팀당 호출 한도: 비용이 큰 경로(/verify, /topic-suggest, /summary, /rag-query mode=prior)에 거는 슬라이딩 윈도 카운터.

프로세스 메모리에만 기록한다. 워커가 여러 개면 워커마다 따로 세므로 실제 허용량은 한도 × 워커 수까지 늘 수 있는 근사치다.
"""
import threading
import time
from collections import deque
from collections.abc import Callable

from app.rag import config_rag
from app.rag.errors import ApiError


class SlidingWindowLimiter:
    """키(팀 번호)별로 최근 window_seconds 안의 호출 수가 limit 이하일 때만 통과시킨다. limit이 0 이하이면 꺼진다."""

    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._calls: dict[int, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: int) -> bool:
        if self.limit <= 0:
            return True
        now = self._clock()
        with self._lock:
            calls = self._calls.setdefault(key, deque())
            while calls and now - calls[0] >= self.window_seconds:
                calls.popleft()
            if len(calls) >= self.limit:
                return False
            calls.append(now)
            return True


limiter = SlidingWindowLimiter(config_rag.RATE_LIMIT_CALLS, config_rag.RATE_LIMIT_WINDOW_SECONDS)


def check_team(team_id: int) -> None:
    """한도를 넘었으면 LLM을 부르기 전에 429로 막는다."""
    if not limiter.allow(team_id):
        raise ApiError(429, "RATE_LIMITED", "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.")
