import re
from dataclasses import dataclass
from typing import Annotated, Any

import jwt
from fastapi import Depends, Request
from fastapi.security import (
    HTTPAuthorizationCredentials,
    HTTPBearer,
)

from .errors import ApiError
from .settings import Settings, get_settings


MAX_LONG = (1 << 63) - 1

_bearer = HTTPBearer(
    auto_error=False,
    scheme_name="bearerAuth",
    bearerFormat="JWT",
)


@dataclass(frozen=True)
class CurrentUser:
    user_id: int
    username: str
    role: str
    team_id: int | None
    team_type: str | None
    view: str

    @property
    def id(self) -> str:
        return str(self.user_id)


def _required_string(
    claims: dict[str, Any],
    name: str,
) -> str:
    value = claims.get(name)

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Invalid string claim: {name}")

    return value


def _positive_integer(value: Any) -> int:
    # bool은 Python에서 int의 하위 타입이므로 별도로 제외한다.
    if type(value) is not int:
        raise ValueError("Invalid integer claim")

    if not 0 < value <= MAX_LONG:
        raise ValueError("Invalid positive integer claim")

    return value


def _to_current_user(
    claims: dict[str, Any],
) -> CurrentUser:
    # v0.2: 사용자 수준(level)은 더 이상 쓰지 않는다. 예전 토큰에 level claim이 있어도 읽지 않고 무시한다.
    subject = _required_string(claims, "sub")

    if re.fullmatch(r"[0-9]{1,19}", subject) is None:
        raise ValueError("Invalid subject")

    user_id = _positive_integer(int(subject))
    username = _required_string(claims, "username")
    role = _required_string(claims, "role")
    view = _required_string(claims, "view")

    if role not in {"member", "team_admin"}:
        raise ValueError("Invalid role")

    if view not in {"dev", "rnd"}:
        raise ValueError("Invalid view")

    issued_at = _positive_integer(claims.get("iat"))
    expires_at = _positive_integer(claims.get("exp"))

    if expires_at <= issued_at:
        raise ValueError("Invalid token lifetime")

    # 팀 미가입을 나타내는 null과 claim 누락은 구분한다.
    if "team_id" not in claims or "team_type" not in claims:
        raise ValueError("Missing team claims")

    team_id = claims["team_id"]
    team_type = claims["team_type"]

    if (team_id is None) != (team_type is None):
        raise ValueError("Inconsistent team claims")

    if team_id is not None:
        team_id = _positive_integer(team_id)
        team_type = _required_string(claims, "team_type")

        if team_type not in {"dev", "rnd"}:
            raise ValueError("Invalid team type")

    return CurrentUser(
        user_id=user_id,
        username=username,
        role=role,
        team_id=team_id,
        team_type=team_type,
        view=view,
    )


def verify_token(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(_bearer),
    ],
    settings: Annotated[
        Settings,
        Depends(get_settings),
    ],
) -> CurrentUser:
    authorization_headers = request.headers.getlist(
        "authorization"
    )

    if len(authorization_headers) > 1:
        raise ApiError(
            401,
            "UNAUTHORIZED",
            "인증 정보가 올바르지 않습니다.",
        )

    if authorization_headers:
        # 헤더가 존재하면 해당 Bearer 인증만 사용한다.
        # 잘못된 헤더를 쿠키 인증으로 우회하지 않는다.
        if credentials is None:
            raise ApiError(
                401,
                "UNAUTHORIZED",
                "Bearer 인증 정보가 필요합니다.",
            )

        token = credentials.credentials.strip()
    else:
        token = request.cookies.get("ACCESS_TOKEN")

    if not token or not token.strip():
        raise ApiError(
            401,
            "UNAUTHORIZED",
            "로그인이 필요합니다.",
        )

    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={
                "require": [
                    "iss",
                    "sub",
                    "username",
                    "role",
                    "view",
                    "iat",
                    "exp",
                ],
            },
        )

        if claims.get("iss") != settings.jwt_issuer:
            raise ValueError("Invalid issuer")

        user = _to_current_user(claims)

    except jwt.ExpiredSignatureError:
        raise ApiError(
            401,
            "TOKEN_EXPIRED",
            "로그인이 만료되었습니다. 다시 로그인해 주세요.",
        ) from None

    except (
        jwt.InvalidTokenError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
    ):
        raise ApiError(
            401,
            "UNAUTHORIZED",
            "인증 정보가 올바르지 않습니다.",
        ) from None

    # 이후 공통 로그 미들웨어에서 사용할 정보
    request.state.user_id = user.user_id
    request.state.team_id = user.team_id

    return user


def require_team(
    user: Annotated[
        CurrentUser,
        Depends(verify_token),
    ],
) -> CurrentUser:
    if user.team_id is None:
        raise ApiError(
            403,
            "NO_TEAM",
            "팀에 가입한 뒤 이용할 수 있습니다.",
        )

    return user


def require_admin(
    user: Annotated[
        CurrentUser,
        Depends(require_team),
    ],
) -> CurrentUser:
    if user.role != "team_admin":
        raise ApiError(
            403,
            "FORBIDDEN",
            "관리자 권한이 필요합니다.",
        )

    return user
