import asyncio
import json
import re
from datetime import datetime
from types import SimpleNamespace

import pytest

from referoom_common import RequestLoggingMiddleware


def test_authenticated_usage_and_request_id(client, app_bundle, make_token, secret):
    token = make_token()
    response = client.get('/tokens?PRIVATE_QUERY=hidden', headers={
        'Authorization': f'Bearer {token}', 'X-Request-Id': 'trace-123',
    })
    assert response.status_code == 200
    assert response.headers['X-Request-Id'] == 'trace-123'
    _, records = app_bundle
    assert len(records) == 1
    record = records[0]
    assert set(record) == {'ts', 'request_id', 'path', 'status', 'latency_ms',
                           'user_id', 'team_id', 'in_tok', 'out_tok'}
    assert record['path'] == '/tokens'
    assert record['user_id'] == 101 and record['team_id'] == 7
    assert record['in_tok'] == 13 and record['out_tok'] == 0
    assert record['status'] == 200 and record['latency_ms'] >= 0
    assert datetime.fromisoformat(record['ts']).utcoffset().total_seconds() == 0
    output = json.dumps(record)
    for sensitive in (token, secret, 'PRIVATE_QUERY', 'test-member'):
        assert sensitive not in output


@pytest.mark.parametrize('value', [None, '', 'bad id', 'a' * 65, 'bad\nvalue'])
def test_request_id_generated_for_missing_or_invalid(client, app_bundle, value):
    headers = {} if value is None else {'X-Request-Id': value}
    response = client.get('/audio/file', headers=headers)
    request_id = response.headers['X-Request-Id']
    assert re.fullmatch('[0-9a-f]{32}', request_id)
    assert app_bundle[1][0]['request_id'] == request_id


@pytest.mark.parametrize('value', ['a', 'a' * 64, 'trace_id.1:2-3'])
def test_valid_request_id_preserved(client, value):
    assert client.get('/audio/file', headers={'X-Request-Id': value}).headers['X-Request-Id'] == value


def test_duplicate_request_ids_replaced(client):
    response = client.get('/audio/file', headers=[('X-Request-Id', 'one'),
                                                ('X-Request-Id', 'two')])
    assert re.fullmatch('[0-9a-f]{32}', response.headers['X-Request-Id'])


def test_path_template_and_unknown_usage(client, app_bundle):
    response = client.get('/audio/PRIVATE_FILENAME?PRIVATE_QUERY=hidden')
    assert response.status_code == 200
    record = app_bundle[1][0]
    assert record['path'] == '/audio/{audio_id}'
    assert all(record[name] is None for name in ('user_id', 'team_id', 'in_tok', 'out_tok'))
    assert 'PRIVATE_' not in json.dumps(record)


def test_unknown_route_does_not_log_raw_path(client, app_bundle):
    assert client.get('/PRIVATE_FILENAME').status_code == 404
    assert app_bundle[1][0]['path'] == '<unmatched>'


def test_invalid_metadata_logged_as_null(client, app_bundle):
    assert client.get('/metadata').status_code == 200
    record = app_bundle[1][0]
    assert all(record[name] is None for name in ('user_id', 'team_id', 'in_tok', 'out_tok'))


def test_unauthorized_request_logged_once(client, app_bundle):
    assert client.get('/team').status_code == 401
    records = app_bundle[1]
    assert len(records) == 1 and records[0]['status'] == 401
    assert records[0]['user_id'] is None and records[0]['team_id'] is None


def test_request_body_not_in_access_log(client, app_bundle):
    assert client.post('/validate', json={'question': 'PRIVATE_QUESTION_BODY'}).status_code == 200
    assert 'PRIVATE_QUESTION_BODY' not in json.dumps(app_bundle[1])


def test_forbidden_request_keeps_authenticated_ids(client, app_bundle, make_token):
    response = client.get('/admin', headers={'Authorization': f'Bearer {make_token()}'})
    assert response.status_code == 403
    record = app_bundle[1][0]
    assert record['user_id'] == 101 and record['team_id'] == 7


def test_streamed_response_unchanged(client, app_bundle):
    response = client.get('/stream')
    assert response.content == b'firstsecond'
    assert len(app_bundle[1]) == 1 and app_bundle[1][0]['status'] == 200


def test_body_not_read_and_asgi_chunks_preserved():
    records, sent = [], []
    class Capture:
        def info(self, value):
            records.append(json.loads(value))
    async def receive():
        raise AssertionError('미들웨어가 본문을 읽으면 안 됨')
    async def send(message):
        sent.append(message)
    async def app(scope, receive, send):
        scope['route'] = SimpleNamespace(path='/stream')
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'a', 'more_body': True})
        await send({'type': 'http.response.body', 'body': b'b', 'more_body': False})
    scope = {'type': 'http', 'headers': []}
    asyncio.run(RequestLoggingMiddleware(app, logger=Capture())(scope, receive, send))
    assert sent[1:] == [
        {'type': 'http.response.body', 'body': b'a', 'more_body': True},
        {'type': 'http.response.body', 'body': b'b', 'more_body': False},
    ]
    assert len(records) == 1


@pytest.mark.parametrize('kind', ['lifespan', 'websocket'])
def test_non_http_bypassed(kind):
    calls = []
    class NoLog:
        def info(self, value):
            raise AssertionError('HTTP 외 요청을 기록하면 안 됨')
    async def app(scope, receive, send):
        calls.append(scope['type'])
    asyncio.run(RequestLoggingMiddleware(app, logger=NoLog())({'type': kind}, None, None))
    assert calls == [kind]


def test_concurrent_requests_keep_separate_state():
    records = []
    class Capture:
        def info(self, value):
            records.append(json.loads(value))
    async def app(scope, receive, send):
        user_id = scope['test_user']
        scope['state'].update(user_id=user_id, team_id=user_id + 10,
                              in_tok=user_id, out_tok=0)
        scope['route'] = SimpleNamespace(path='/parallel')
        await asyncio.sleep(0)
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b''})
    async def send(message):
        pass
    async def run():
        middleware = RequestLoggingMiddleware(app, logger=Capture())
        await asyncio.gather(*[
            middleware({'type': 'http', 'headers': [], 'test_user': i}, None, send)
            for i in range(1, 6)
        ])
    asyncio.run(run())
    assert len(records) == 5
    assert len({record['request_id'] for record in records}) == 5
    for record in records:
        assert record['team_id'] == record['user_id'] + 10
        assert record['in_tok'] == record['user_id']
