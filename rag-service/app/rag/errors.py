"""공통 에러 포맷 {"detail": 메시지, "code": 코드} (DEV_01 3.3절).

오류 클래스와 처리기는 common-py(referoom_common)의 것을 그대로 쓴다. 인증이 던지는 ApiError와 이 서비스가 던지는 ApiError가
같은 클래스여야 하나의 처리기가 모두 받는다. 기존 `from app.rag.errors import ApiError` 경로는 그대로 쓸 수 있다.
"""
from referoom_common import ApiError, register_error_handlers

__all__ = ["ApiError", "register_error_handlers"]
