"""All voice tests are offline and use isolated audio storage."""
import os
import sys
import time
from pathlib import Path
from unittest.mock import Mock

# Establish safe settings before application import and dotenv loading.
os.environ["JWT_SECRET"] = "voice-test-secret-0123456789-abcdefgh"
os.environ["OPENAI_API_KEY"] = "offline-voice-test-key"
os.environ["LLM_API_KEY"] = "offline-voice-test-key"
os.environ["CORS_ALLOWED_ORIGINS"] = "http://localhost:5174,http://localhost:8008"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import jwt
import pytest
from fastapi.testclient import TestClient
from referoom_common import get_settings
from app import main
from app.routers.audio import AudioStorage
from app.services import stt_service, tts_service


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import socket
    def blocked(*args, **kwargs):
        raise AssertionError("External network is forbidden in voice tests")
    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setenv("JWT_SECRET", "voice-test-secret-0123456789-abcdefgh")
    monkeypatch.setenv("OPENAI_API_KEY", "offline-voice-test-key")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5174,http://localhost:8008")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def backend(monkeypatch):
    stt = Mock(return_value={"text": "LoRA 질문", "language": "ko", "duration_s": 1.2})
    tts = Mock(return_value=b"fake-mp3")
    initialize = Mock()
    monkeypatch.setattr(stt_service, "transcribe_upload", stt)
    monkeypatch.setattr(stt_service, "initialize_model", initialize)
    monkeypatch.setattr(stt_service, "model_status", lambda: "ready")
    monkeypatch.setattr(tts_service, "synthesize_speech", tts)
    return stt, tts, initialize


@pytest.fixture
def application(tmp_path, backend):
    return main.create_app(AudioStorage(tmp_path / "audio"))


@pytest.fixture
def client(application):
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def token():
    def make(**changes):
        now = int(time.time())
        claims = dict(iss="simple-auth-server", sub="12", username="voice-tester",
                      role="member", team_id=3, iat=now, exp=now+3600)
        claims.update(changes)
        return jwt.encode(claims, "voice-test-secret-0123456789-abcdefgh", algorithm="HS256")
    return make


@pytest.fixture
def auth(token):
    return {"Authorization": "Bearer " + token()}
