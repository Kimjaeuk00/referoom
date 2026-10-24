"""인증 스텁. TODO(common-py): 백엔드의 common-py `require_team`이 완성되면 deps.py의 import만 교체한다.

시그니처와 에러 코드는 DEV_01 3.3절 계약과 동일하게 맞춘다.
"""
from dataclasses import dataclass

from fastapi import Cookie, Depends, Header
from jose import ExpiredSignatureError, JWTError, jwt

from app.rag import config_rag
from app.rag.errors import ApiError


@dataclass
class CurrentUser:
    user_id: int
    team_id: int | None
    role: str | None
    level: str | None
    view: str | None


def verify_token(
    authorization: str | None = Header(None),
    access_token: str | None = Cookie(None, alias="ACCESS_TOKEN"),
) -> CurrentUser:
    # Bearer 우선, 쿠키 폴백
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    elif access_token:
        token = access_token
    if not token:
        raise ApiError(401, "UNAUTHORIZED", "로그인이 필요합니다.")
    try:
        claims = jwt.decode(
            token, config_rag.JWT_SECRET, algorithms=["HS256"], issuer=config_rag.JWT_ISSUER
        )
        return CurrentUser(
            user_id=int(claims["sub"]),
            team_id=claims.get("team_id"),
            role=claims.get("role"),
            level=claims.get("level"),
            view=claims.get("view"),
        )
    except ExpiredSignatureError:
        raise ApiError(401, "TOKEN_EXPIRED", "로그인이 만료되었습니다.")
    except (JWTError, KeyError, ValueError):
        raise ApiError(401, "UNAUTHORIZED", "로그인이 필요합니다.")


def require_team(user: CurrentUser = Depends(verify_token)) -> CurrentUser:
    if user.team_id is None:
        raise ApiError(403, "NO_TEAM", "팀에 가입한 뒤 이용할 수 있습니다.")
    return user
