import io
import json
import logging
import time
from unittest.mock import Mock

import pytest
from referoom_common import get_settings
from app import main
from app.services import stt_service, tts_service
from app.utils.audio_utils import AudioInputError


def request(client, route, headers=None):
    if route == "stt":
        return client.post('/stt', files={'audio': ('input.webm', b'fake-audio', 'audio/webm')}, headers=headers)
    if route == "tts":
        return client.post('/tts', json={'text':'LoRA 질문'}, headers=headers)
    return client.get('/audio/'+'0'*32, headers=headers)


@pytest.mark.parametrize('state,status', [('ready',200),('loading',503),('failed',503)])
def test_public_health(client, monkeypatch, state, status):
    monkeypatch.setattr(stt_service,'model_status',lambda:state)
    response=client.get('/health')
    assert response.status_code==status
    assert response.headers['x-request-id']
    if status==503: assert response.json()['code']=='NOT_READY'


@pytest.mark.parametrize('route',['stt','tts','audio'])
def test_missing_auth_does_not_infer(client,backend,route):
    response=request(client,route)
    assert response.status_code==401
    assert response.json()['code']=='UNAUTHORIZED'
    assert response.headers['www-authenticate']=='Bearer'
    backend[0].assert_not_called();backend[1].assert_not_called()


@pytest.mark.parametrize('route',['stt','tts','audio'])
def test_no_team_does_not_infer(client,backend,token,route):
    response=request(client,route,{'Authorization':'Bearer '+token(team_id=None)})
    assert response.status_code==403
    assert response.json()['code']=='NO_TEAM'
    backend[0].assert_not_called();backend[1].assert_not_called()


@pytest.mark.parametrize('changes,code',[({'exp':int(time.time())-1},'TOKEN_EXPIRED'),({'iss':'other'},'UNAUTHORIZED'),({'sub':'not-numeric'},'UNAUTHORIZED'),({'role':'unknown'},'UNAUTHORIZED')])
def test_invalid_claims(client,token,changes,code):
    response=request(client,'tts',{'Authorization':'Bearer '+token(**changes)})
    assert response.status_code==401
    assert response.json()['code']==code


def test_bad_header_cannot_use_valid_cookie(client,token):
    client.cookies.set('ACCESS_TOKEN',token())
    assert request(client,'tts',{'Authorization':'Bearer invalid'}).status_code==401


def test_duplicate_auth_headers_rejected(client,token):
    response=client.post('/tts',json={'text':'hello'},headers=[('Authorization','Bearer '+token()),('Authorization','Bearer '+token())])
    assert response.status_code==401


def test_stt_success_and_closes_upload(client,backend,auth):
    response=request(client,'stt',auth)
    assert response.status_code==200
    assert response.json()['text']=='LoRA 질문'
    assert response.json()['latency_ms']>=0
    assert backend[0].call_args.args[0].closed


@pytest.mark.parametrize('error,status,code',[(stt_service.EmptyTranscriptionError('empty'),422,'STT_EMPTY'),(stt_service.ModelNotReadyError('private'),503,'NOT_READY'),(AudioInputError('too large',413,'PAYLOAD_TOO_LARGE'),413,'PAYLOAD_TOO_LARGE')])
def test_stt_errors_close_upload(client,backend,auth,error,status,code):
    backend[0].side_effect=error
    response=request(client,'stt',auth)
    assert response.status_code==status
    assert response.json()['code']==code
    assert backend[0].call_args.args[0].closed
    assert 'private' not in response.text


@pytest.mark.parametrize('payload',[{}, {'text':''}, {'text':'   '}, {'text':{'private':'input'}}])
def test_tts_validation_is_common_and_private(client,auth,payload):
    response=client.post('/tts',json=payload,headers=auth)
    assert response.status_code==422
    assert set(response.json())=={'detail','code'}
    assert response.json()['code']=='VALIDATION_ERROR'
    assert 'private' not in response.text


def test_stt_missing_upload_validation(client,auth):
    response=client.post('/stt',headers=auth)
    assert response.status_code==422
    assert response.json()['code']=='VALIDATION_ERROR'


def test_tts_download_owner_expiry_and_cleanup(client,application,backend,auth,token,monkeypatch):
    response=request(client,'tts',auth)
    assert response.status_code==200
    body=response.json()
    audio_id=body['audio_id']
    storage=application.state.audio_storage
    assert (storage.directory/'12'/f'{audio_id}.mp3').is_file()
    audio=client.get(body['audio_url'],headers=auth)
    assert audio.status_code==200 and audio.content==b'fake-mp3'
    assert audio.headers['cache-control']=='no-store'
    other=client.get(body['audio_url'],headers={'Authorization':'Bearer '+token(sub='13')})
    missing=client.get('/audio/'+'0'*32,headers=auth)
    assert other.status_code==missing.status_code==404
    assert other.json()==missing.json()
    from app.routers import audio as module
    monkeypatch.setattr(module,'time',lambda:time.time()+601)
    expired=client.get(body['audio_url'],headers=auth)
    assert expired.status_code==404 and expired.json()==missing.json()
    storage.cleanup()
    assert not list(storage.directory.glob('*/*.mp3'))
    assert not list(storage.directory.glob('*/*.json'))


@pytest.mark.parametrize('error,code',[(tts_service.TtsNotReadyError('서비스 준비 중'),'NOT_READY'),(tts_service.TtsUpstreamError('음성 응답 대기 실패'),'UPSTREAM_TIMEOUT')])
def test_tts_expected_errors(client,backend,auth,error,code):
    backend[1].side_effect=error
    response=request(client,'tts',auth)
    assert response.status_code==503 and response.json()['code']==code


def test_unexpected_error_is_sanitized(client,backend,auth):
    backend[1].side_effect=RuntimeError('private-provider-detail')
    response=request(client,'tts',auth)
    assert response.status_code==500 and response.json()['code']=='INTERNAL_ERROR'
    assert 'private-provider-detail' not in response.text
    assert response.headers['x-request-id']


def test_cors_preflight(client):
    response=client.options('/tts',headers={'Origin':'http://localhost:5174','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Authorization,Content-Type,X-Request-Id','X-Request-Id':'voice-preflight'})
    assert response.status_code==200
    assert response.headers['access-control-allow-origin']=='http://localhost:5174'
    assert response.headers['x-request-id']=='voice-preflight'


@pytest.mark.parametrize('status,headers',[(401,{}),(200,{'auth':True})])
def test_cors_normal_and_auth_errors(client,auth,status,headers):
    response=request(client,'tts',{'Origin':'http://localhost:5174',**(auth if headers else {})})
    assert response.status_code==status
    assert response.headers['access-control-allow-origin']=='http://localhost:5174'
    assert 'x-request-id' in response.headers['access-control-expose-headers'].lower()


def test_disallowed_origin(client):
    response=client.options('/tts',headers={'Origin':'https://other.invalid','Access-Control-Request-Method':'POST'})
    assert response.status_code==400
    assert 'access-control-allow-origin' not in response.headers


def test_bad_request_id_replaced(client):
    response=client.get('/health',headers={'X-Request-Id':'bad id'})
    assert response.headers['x-request-id']!='bad id'


def test_access_log_has_ids_without_text_or_token(client,auth):
    records=[]
    class Capture(logging.Handler):
        def emit(self,record):records.append(record.getMessage())
    logger=logging.getLogger('referoom_common.access')
    handler=Capture();logger.addHandler(handler)
    try:
        response=client.post('/tts?private-query=never-log',json={'text':'private-question-never-log'},headers={**auth,'X-Request-Id':'voice-log-case'})
    finally:logger.removeHandler(handler)
    assert response.status_code==200
    record=json.loads(records[-1])
    assert record['user_id']==12 and record['team_id']==3
    assert record['path']=='/tts' and record['request_id']=='voice-log-case'
    assert record['in_tok'] is None
    assert 'private-question-never-log' not in records[-1]
    assert 'private-query' not in records[-1]
    assert auth['Authorization'] not in records[-1]


def test_lifespan_initializes_once_and_cleans_on_start(application,backend,monkeypatch):
    from fastapi.testclient import TestClient
    cleanup=Mock()
    monkeypatch.setattr(application.state.audio_storage,'cleanup',cleanup)
    with TestClient(application) as client:
        client.get('/health');client.get('/health')
    backend[2].assert_called_once()
    cleanup.assert_called_once()


def test_model_failure_keeps_health_available(application,backend,monkeypatch):
    from fastapi.testclient import TestClient
    backend[2].side_effect=RuntimeError('private-model-path')
    monkeypatch.setattr(stt_service,'model_status',lambda:'failed')
    with TestClient(application) as client:
        response=client.get('/health')
    assert response.status_code==503 and 'private-model-path' not in response.text


def test_missing_jwt_fails_fast(monkeypatch):
    monkeypatch.delenv('JWT_SECRET')
    get_settings.cache_clear()
    with pytest.raises(RuntimeError,match='JWT_SECRET'):main.create_app()


def test_wildcard_cors_fails_fast(monkeypatch):
    monkeypatch.setenv('CORS_ALLOWED_ORIGINS','*')
    get_settings.cache_clear()
    with pytest.raises(RuntimeError):main.create_app()


def test_openapi_registers_only_current_routes(client):
    schema=client.get('/openapi.json').json()
    assert set(schema['paths'])=={'/health','/stt','/tts','/audio/{audio_id}','/voice-qa'}
    for path,method in [('/stt','post'),('/tts','post'),('/audio/{audio_id}','get')]:
        assert {'bearerAuth':[]} in schema['paths'][path][method]['security']


@pytest.mark.parametrize('path',['/stt-tts/','/stt.html','/tts.html','/index.html','/static/stt.html','/uploads/test.mp3'])
def test_legacy_routes_not_served(client,path):
    assert client.get(path).status_code==404
