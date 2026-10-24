import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


logger = logging.getLogger("referoom_common.errors")


HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    503: "NOT_READY",
    504: "UPSTREAM_TIMEOUT",
}


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        detail: str,
    ):
        super().__init__(detail)

        self.status = status
        self.code = code
        self.detail = detail


def _error_response(
    request: Request,
    status: int,
    code: str,
    detail: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    response_headers = dict(headers or {})

    if status == 401:
        response_headers.setdefault(
            "WWW-Authenticate",
            "Bearer",
        )

    request_id = getattr(
        request.state,
        "request_id",
        None,
    )

    if request_id:
        response_headers["X-Request-Id"] = request_id

    return JSONResponse(
        status_code=status,
        content={
            "detail": detail,
            "code": code,
        },
        headers=response_headers,
    )


def register_error_handlers(app: FastAPI) -> None:

    @app.exception_handler(ApiError)
    async def handle_api_error(
        request: Request,
        exception: ApiError,
    ) -> JSONResponse:
        return _error_response(
            request=request,
            status=exception.status,
            code=exception.code,
            detail=exception.detail,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exception: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            request=request,
            status=422,
            code="VALIDATION_ERROR",
            detail="요청 형식이 올바르지 않습니다.",
        )

    @app.exception_handler(HTTPException)
    async def handle_http_error(
        request: Request,
        exception: HTTPException,
    ) -> JSONResponse:
        status = exception.status_code

        code = HTTP_ERROR_CODES.get(
            status,
            f"HTTP_{status}",
        )

        try:
            detail = HTTPStatus(status).phrase
        except ValueError:
            detail = "요청을 처리할 수 없습니다."

        return _error_response(
            request=request,
            status=status,
            code=code,
            detail=detail,
            headers=exception.headers,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exception: Exception,
    ) -> JSONResponse:
        logger.error(
            "예상하지 못한 서버 오류: type=%s",
            type(exception).__name__,
        )

        return _error_response(
            request=request,
            status=500,
            code="INTERNAL_ERROR",
            detail="서버 내부 오류가 발생했습니다.",
        )
