"""데이터 API 공통 의존성: 인증(app.rag.deps) 위에 '라이브러리 사용 가능'과 '팀 관리자' 확인을 얹는다."""
from fastapi import Depends

from app.rag import config_rag
from app.rag.deps import CurrentUser, require_team
from app.rag.errors import ApiError


def require_library(user: CurrentUser = Depends(require_team)) -> CurrentUser:
    """로그인·팀 확인 뒤, 로컬 색인을 쓰는 설정(RAG_STORE=local)인지 확인한다. 인증 오류가 항상 먼저 나온다."""
    if config_rag.STORE_BACKEND != "local":
        raise ApiError(503, "NOT_READY", "논문 라이브러리를 사용할 수 없는 설정입니다. 서버를 RAG_STORE=local로 실행하세요.")
    return user


def require_admin(user: CurrentUser = Depends(require_library)) -> CurrentUser:
    if user.role != "team_admin":
        raise ApiError(403, "FORBIDDEN", "팀 관리자만 할 수 있습니다.")
    return user
