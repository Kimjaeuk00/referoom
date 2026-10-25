import os
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    jwt_secret: str = field(repr=False)

    jwt_issuer: str = field(
        default="simple-auth-server",
        init=False,
    )

    jwt_algorithm: str = field(
        default="HS256",
        init=False,
    )

    cors_allowed_origins: tuple[str, ...] = (
        "http://localhost:5174",
        "http://localhost:8008",
    )

    @classmethod
    def from_env(cls) -> "Settings":
        secret = os.getenv("JWT_SECRET")

        if secret is None or not secret.strip():
            raise RuntimeError(
                "JWT_SECRET 환경변수가 설정되지 않았습니다."
            )

        origins_value = os.getenv(
            "CORS_ALLOWED_ORIGINS",
            "http://localhost:5174,http://localhost:8008",
        )

        origins = tuple(
            origin.strip()
            for origin in origins_value.split(",")
            if origin.strip()
        )

        if not origins or "*" in origins:
            raise RuntimeError(
                "CORS_ALLOWED_ORIGINS에는 "
                "명시적인 허용 주소를 설정해야 합니다."
            )

        return cls(
            jwt_secret=secret,
            cors_allowed_origins=origins,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
