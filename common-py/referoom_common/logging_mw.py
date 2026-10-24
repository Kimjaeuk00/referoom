import json
import logging
import re
from datetime import datetime, timezone
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


_REQUEST_ID_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}"
)


def _get_access_logger() -> logging.Logger:
    logger = logging.getLogger("referoom_common.access")

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False

    return logger


def _request_id(scope: Scope) -> str:
    values = Headers(scope=scope).getlist("x-request-id")

    if len(values) == 1:
        value = values[0]

        if _REQUEST_ID_PATTERN.fullmatch(value):
            return value

    return uuid4().hex


def _positive_id(value: object) -> int | None:
    if type(value) is int and value > 0:
        return value

    return None


def _token_count(value: object) -> int | None:
    if type(value) is int and value >= 0:
        return value

    return None


class RequestLoggingMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        logger: logging.Logger | None = None,
    ):
        self.app = app
        self.logger = (
            logger if logger is not None else _get_access_logger()
        )

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat(
            timespec="milliseconds"
        )

        request_id = _request_id(scope)

        state = scope.setdefault("state", {})
        state["request_id"] = request_id

        status = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status

            if message["type"] == "http.response.start":
                status = message["status"]

                headers = MutableHeaders(scope=message)
                headers["X-Request-Id"] = request_id

            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            route = scope.get("route")
            path = getattr(route, "path", "<unmatched>")

            record = {
                "ts": timestamp,
                "request_id": request_id,
                "path": path,
                "status": status,
                "latency_ms": round(
                    (perf_counter() - started) * 1000,
                    2,
                ),
                "user_id": _positive_id(state.get("user_id")),
                "team_id": _positive_id(state.get("team_id")),
                "in_tok": _token_count(state.get("in_tok")),
                "out_tok": _token_count(state.get("out_tok")),
            }

            self.logger.info(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    allow_nan=False,
                )
            )
