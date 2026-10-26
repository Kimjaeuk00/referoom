import json
import logging
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient
from app import main
from app.routers.audio import AudioStorage
from app.services import stt_service, tts_service
from app.services.rag_client import RagClient
from app.services.speech_text import HANDOFF, LIMIT, NOTICE, make_speech_text


@pytest.fixture
def rag_body():
    return dict(answer='**LoRA**는 저랭크 행렬을 학습합니다 [S1].',sources=['LoRA p.1'],
                source_details=[dict(label='S1',paper_id=41,title='LoRA',page=1,snippet='low rank')],
                needs_review=False,handoff=False,level='L2',latency_ms=20,mode='tutor')


@pytest.fixture
def qa(tmp_path,backend,rag_body):
    calls=[]
    state={'status':200,'body':rag_body,'error':None,'headers':{}}
    def handler(request):
        calls.append(request)
        if state['error']:raise state['error']
        return httpx.Response(state['status'],json=state['body'],headers=state['headers'])
    rag=RagClient('http://rag.test:8001',transport=httpx.MockTransport(handler))
    app=main.create_app(AudioStorage(tmp_path/'qa-audio'),rag_client=rag)
    with TestClient(app,raise_server_exceptions=False) as client:
        yield client,calls,state,app


def ask(client,auth=None,**data):
    return client.post('/voice-qa',headers=auth,files={'audio':('question.webm',b'fake','audio/webm')},data=data)


def test_complete_flow_forwarding_owner_audio_and_latency(qa,backend,auth):
    client,calls,state,app=qa
    response=ask(client,{**auth,'X-Request-Id':'voice-qa-test'},scope=json.dumps({'type':'paper','ids':[41],'team_id':999}),view='dev',source='pdf',language='en',level='L1')
    assert response.status_code==200
    body=response.json()
    assert body['answer']==state['body']['answer'] and body['sources']==state['body']['sources']
    assert body['source_details'][0]['paper_id']==41
    assert body['level']=='L2' and body['mode']=='tutor'
    assert set(body['latency_ms'])=={'stt','rag','tts','total'}
    assert all(type(v) is int and v>=0 for v in body['latency_ms'].values())
    assert len(calls)==1
    request=calls[0]
    assert request.headers['Authorization']==auth['Authorization']
    assert request.headers['X-Request-Id']=='voice-qa-test'
    sent=json.loads(request.content)
    assert sent['question']=='LoRA 질문' and 'view' not in sent and 'source' not in sent  # 예전 클라이언트가 보낸 view·source는 전달하지 않는다
    assert sent['scope']=={'type':'paper','ids':[41]} and sent['level']=='L1'
    assert 'team_id' not in sent and 'mode' not in sent
    assert request.extensions['timeout']['connect']==5 and request.extensions['timeout']['read']==30
    backend[1].assert_called_once()
    assert backend[0].call_args.args[2]=='en' and backend[0].call_args.args[0].closed
    assert client.get(body['audio_url'],headers=auth).content==b'fake-mp3'
    assert list((app.state.audio_storage.directory/'12').glob('*.mp3'))


def test_speak_false_has_no_tts_or_audio(qa,backend,auth):
    client,calls,state,app=qa
    response=ask(client,auth,speak='false')
    assert response.status_code==200
    body=response.json()
    assert body['audio_id'] is None and body['audio_url'] is None and body['latency_ms']['tts']==0
    assert body['speech_text'].endswith(NOTICE)
    backend[1].assert_not_called()
    assert not list(app.state.audio_storage.directory.glob('**/*.mp3'))


@pytest.mark.parametrize('error',[tts_service.TtsUpstreamError('private-provider-error'),tts_service.TtsNotReadyError('private-key-error'),RuntimeError('private-storage-error')])
def test_tts_failure_preserves_answer_without_automatic_retry(qa,backend,auth,error,caplog):
    client,calls,state,app=qa
    backend[1].side_effect=error
    response=ask(client,auth)
    assert response.status_code==200
    body=response.json()
    assert body['answer']==state['body']['answer'] and body['sources']==state['body']['sources']
    assert body['audio_id'] is None and body['audio_url'] is None and not body['handoff']
    assert len(calls)==1
    backend[0].assert_called_once();backend[1].assert_called_once()
    assert 'private-' not in response.text and 'private-' not in caplog.text


def test_storage_failure_also_preserves_answer(qa,backend,auth,monkeypatch):
    client,calls,state,app=qa
    monkeypatch.setattr(app.state.audio_storage,'save',Mock(side_effect=OSError('private-disk-path')))
    response=ask(client,auth)
    assert response.status_code==200 and response.json()['audio_url'] is None
    assert response.json()['sources']==state['body']['sources']
    backend[1].assert_called_once()


def test_handoff_uses_fixed_narration(qa,backend,auth):
    client,calls,state,app=qa
    state['body'].update(handoff=True,sources=[],source_details=[],answer='찾을 수 없음')
    response=ask(client,auth)
    assert response.status_code==200 and response.json()['speech_text']==HANDOFF
    assert backend[1].call_args.args[0]==HANDOFF


@pytest.mark.parametrize('status,code',[(401,'TOKEN_EXPIRED'),(403,'NO_TEAM'),(422,'VALIDATION_ERROR'),(429,'TOO_MANY_REQUESTS'),(503,'NOT_READY'),(504,'UPSTREAM_TIMEOUT'),(500,'INTERNAL_ERROR')])
def test_rag_status_and_code_preserved_without_private_details(qa,backend,auth,status,code):
    client,calls,state,app=qa
    state.update(status=status,body={'detail':'private-question-and-provider-error','code':code})
    response=ask(client,auth)
    assert response.status_code==status and response.json()['code']==code
    assert 'private-' not in response.text and len(calls)==1
    backend[1].assert_not_called()
    assert backend[0].call_args.args[0].closed


@pytest.mark.parametrize('error,code',[(httpx.ReadTimeout('private'), 'UPSTREAM_TIMEOUT'),(httpx.ConnectTimeout('private'),'UPSTREAM_TIMEOUT'),(httpx.ConnectError('private'),'NOT_READY')])
def test_rag_transport_failure_no_retry(qa,backend,auth,error,code):
    client,calls,state,app=qa
    state['error']=error
    response=ask(client,auth)
    assert response.status_code==503 and response.json()['code']==code
    assert len(calls)==1 and 'private' not in response.text
    backend[1].assert_not_called()


@pytest.mark.parametrize('body',[{},[],{'answer':'private-incomplete'},None])
def test_malformed_success_is_not_forwarded(qa,backend,auth,body):
    client,calls,state,app=qa;state['body']=body
    response=ask(client,auth)
    assert response.status_code==502 and response.json()['code']=='UPSTREAM_ERROR'
    assert 'private' not in response.text
    backend[1].assert_not_called()


def test_redirect_not_followed_with_bearer(qa,backend,auth):
    client,calls,state,app=qa
    state.update(status=307,body={},headers={'Location':'https://other.invalid/rag-query'})
    response=ask(client,auth)
    assert response.status_code==502 and len(calls)==1


@pytest.mark.parametrize('data',[{'scope':'bad json'},{'scope':'[]'},{'scope':'null'},{'scope':'{"type":"batch"}'},{'speak':'yes'},{'language':'other'},{'level':'other'}])
def test_invalid_form_never_infers(qa,backend,auth,data):
    client,calls,state,app=qa
    response=ask(client,auth,**data)
    assert response.status_code==422 and response.json()['code']=='VALIDATION_ERROR'
    backend[0].assert_not_called();backend[1].assert_not_called()
    assert not calls


@pytest.mark.parametrize('text',['','   ','x','x'*1001])
def test_empty_or_out_of_range_transcript_never_queries(qa,backend,auth,text):
    client,calls,state,app=qa
    backend[0].return_value={'text':text,'language':'ko','duration_s':1}
    response=ask(client,auth)
    assert response.status_code==422
    assert response.json()['code']==('STT_EMPTY' if not text.strip() else 'VALIDATION_ERROR')
    assert not calls
    backend[1].assert_not_called()
    assert backend[0].call_args.args[0].closed


@pytest.mark.parametrize('kind',['missing','no-team','cookie-only'])
def test_auth_before_inference(qa,backend,token,kind):
    client,calls,state,app=qa
    auth=None
    if kind=='no-team':auth={'Authorization':'Bearer '+token(team_id=None)}
    if kind=='cookie-only':client.cookies.set('ACCESS_TOKEN',token())
    response=ask(client,auth)
    assert response.status_code==(403 if kind=='no-team' else 401)
    assert not calls
    backend[0].assert_not_called()


def test_manual_tts_retry_does_not_reinvoke_stt_or_rag(qa,backend,auth):
    client,calls,state,app=qa
    backend[1].side_effect=tts_service.TtsUpstreamError('unavailable')
    body=ask(client,auth).json()
    backend[1].side_effect=None
    retry=client.post('/tts',json={'text':body['speech_text']},headers=auth)
    assert retry.status_code==200
    assert len(calls)==1 and backend[0].call_count==1 and backend[1].call_count==2
    # The one-manual-retry UI limit remains A's responsibility; /tts is a general endpoint.


@pytest.mark.parametrize('url',['ftp://rag.test','http://user:pass@rag.test','http://rag.test?token=secret','http://rag.test#fragment',''])
def test_bad_rag_url_rejected(url):
    with pytest.raises(ValueError):RagClient(url)


@pytest.mark.parametrize('text',[
    '## **LoRA**는 $W=BA$를 사용합니다 [S1]. https://example.com',
    '[설명](https://example.com)과 `코드`입니다.',
    '수식 $$a+b$$ 및 \\(c+d\\)를 확인합니다.',
    '<b>설명</b>입니다. [S2]',
    '완료된 문장입니다. '*100,
    '아주긴문장'*200,
])
def test_speech_cleaning_is_bounded_and_deterministic(text):
    speech=make_speech_text(text)
    assert speech==make_speech_text(text) and len(speech)<=LIMIT
    assert speech.endswith(NOTICE)
    for marker in ['https://','[S1]','[S2]','**','`','$','<b>']:
        assert marker not in speech


def test_handoff_exact_and_math_replacement():
    assert make_speech_text('anything',True)==HANDOFF
    assert '(수식은 화면을 참고하세요)' in make_speech_text('식 $a+b$ 입니다.')
