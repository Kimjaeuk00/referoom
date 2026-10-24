"""공통 에러 포맷 {"detail": 메시지, "code": 코드} (DEV_01 3.3절)."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, detail: str):
        self.status = status
        self.code = code
        self.detail = detail


def _body(code: str, detail: str) -> dict:
    return {"detail": detail, "code": code}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(status_code=exc.status, content=_body(exc.code, exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, __: RequestValidationError):
        # 입력 원문(질문)이 응답·로그에 남지 않도록 상세 입력값은 반환하지 않는다
        return JSONResponse(status_code=422, content=_body("VALIDATION_ERROR", "요청 형식이 올바르지 않습니다."))
