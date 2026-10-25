import json
import logging
import secrets
import sys
from pathlib import Path
from time import time

import jwt
import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field


# 설치 여부와 무관하게 현재 작업 폴더의 실제 모듈을 검사한다.
PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from referoom_common import (
    ApiError,
    RequestLoggingMiddleware,
    get_settings,
    register_error_handlers,
    require_admin,
    require_team,
    verify_token,
)


class LogCapture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(json.loads(record.getMessage()))


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


@pytest.fixture
def secret(monkeypatch):
    value = secrets.token_hex(32)
    monkeypatch.setenv('JWT_SECRET', value)
    monkeypatch.delenv('CORS_ALLOWED_ORIGINS', raising=False)
    get_settings.cache_clear()
    yield value
    get_settings.cache_clear()


@pytest.fixture
def make_token(secret):
    def make(changes=None, *, omit=(), algorithm='HS256', key=None):
        now = int(time())
        claims = {
            'iss': 'simple-auth-server', 'sub': '101',
            'username': 'test-member', 'role': 'member',
            'team_id': 7, 'team_type': 'dev',
            'view': 'dev',
            'iat': now - 10, 'exp': now + 3600,
        }
        claims.update(changes or {})
        for name in omit:
            claims.pop(name, None)
        signing_key = secret if key is None else key
        if algorithm == 'none':
            signing_key = ''
        return jwt.encode(claims, signing_key, algorithm=algorithm)
    return make


@pytest.fixture
def app_bundle(secret):
    app = FastAPI()
    capture = LogCapture()
    logger = logging.Logger('referoom-common-test', level=logging.INFO)
    logger.addHandler(capture)
    app.add_middleware(RequestLoggingMiddleware, logger=logger)
    register_error_handlers(app)

    @app.get('/me')
    def me(user=Depends(verify_token)):
        return vars(user) | {'id': user.id}

    @app.get('/team')
    def team(user=Depends(require_team)):
        return {'team_id': user.team_id}

    @app.get('/admin')
    def admin(user=Depends(require_admin)):
        return {'team_id': user.team_id, 'role': user.role}

    @app.get('/tokens')
    def tokens(request: Request, user=Depends(require_team)):
        request.state.in_tok = 13
        request.state.out_tok = 0
        return {'ok': True}

    @app.get('/api-error/{status}')
    def api_error(status: int):
        raise ApiError(status, 'TEST_SERVICE_ERROR', '서비스에서 정한 안내')

    @app.get('/http-error/{status}')
    def http_error(status: int):
        raise HTTPException(status, detail='PRIVATE_EXCEPTION_TEXT',
                            headers={'Retry-After': '3'})

    @app.post('/validate')
    def validate(payload: Question):
        return {'ok': True}

    @app.get('/explode')
    def explode():
        raise RuntimeError('PRIVATE_EXCEPTION_TEXT')

    @app.get('/audio/{audio_id}')
    def audio(audio_id: str):
        return {'ok': True}

    @app.get('/stream')
    async def stream():
        async def chunks():
            yield b'first'
            yield b'second'
        return StreamingResponse(chunks())

    @app.get('/metadata')
    def metadata(request: Request):
        request.state.user_id = True
        request.state.team_id = -1
        request.state.in_tok = '15'
        request.state.out_tok = -1
        return {'ok': True}

    return app, capture.records


@pytest.fixture
def client(app_bundle):
    app, _ = app_bundle
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
