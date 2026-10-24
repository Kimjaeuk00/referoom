import json

import pytest


@pytest.mark.parametrize('status', [400, 401, 403, 404, 409, 422, 503])
def test_service_exception_preserves_contract(client, status):
    response = client.get(f'/api-error/{status}')
    assert response.status_code == status
    assert response.json() == {
        'detail': '서비스에서 정한 안내', 'code': 'TEST_SERVICE_ERROR',
    }
    assert response.headers['X-Request-Id']
    if status == 401:
        assert response.headers['WWW-Authenticate'] == 'Bearer'


@pytest.mark.parametrize('status,code', [
    (400, 'BAD_REQUEST'), (401, 'UNAUTHORIZED'), (403, 'FORBIDDEN'),
    (404, 'NOT_FOUND'), (405, 'METHOD_NOT_ALLOWED'), (409, 'CONFLICT'),
    (413, 'PAYLOAD_TOO_LARGE'), (415, 'UNSUPPORTED_MEDIA_TYPE'),
    (422, 'VALIDATION_ERROR'), (429, 'TOO_MANY_REQUESTS'),
    (503, 'NOT_READY'), (504, 'UPSTREAM_TIMEOUT'), (418, 'HTTP_418'),
    (499, 'HTTP_499'),
])
def test_http_exception_mapping_and_headers(client, status, code):
    response = client.get(f'/http-error/{status}')
    assert response.status_code == status
    assert response.json()['code'] == code
    assert set(response.json()) == {'detail', 'code'}
    assert 'PRIVATE_EXCEPTION_TEXT' not in response.text
    assert response.headers['Retry-After'] == '3'


@pytest.mark.parametrize('payload', [{}, {'question': 'x'}, {'question': {'PRIVATE_INPUT': 1}}])
def test_validation_error_does_not_echo_input(client, payload):
    response = client.post('/validate', json=payload)
    assert response.status_code == 422
    assert response.json() == {'detail': '요청 형식이 올바르지 않습니다.',
                               'code': 'VALIDATION_ERROR'}
    assert 'PRIVATE_INPUT' not in response.text


def test_malformed_json(client):
    response = client.post('/validate', content='{"PRIVATE_INPUT":',
                           headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert response.json()['code'] == 'VALIDATION_ERROR'
    assert 'PRIVATE_INPUT' not in response.text


def test_unexpected_error_is_safe_and_correlated(client, app_bundle, caplog):
    response = client.get('/explode', headers={'X-Request-Id': 'failure-123'})
    assert response.status_code == 500
    assert response.json() == {'detail': '서버 내부 오류가 발생했습니다.',
                               'code': 'INTERNAL_ERROR'}
    assert response.headers['X-Request-Id'] == 'failure-123'
    assert 'PRIVATE_EXCEPTION_TEXT' not in caplog.text + response.text
    assert 'RuntimeError' in caplog.text
    _, records = app_bundle
    assert len(records) == 1
    assert records[0]['status'] == 500
    assert records[0]['request_id'] == 'failure-123'


@pytest.mark.parametrize('method,path,status,code', [
    ('get', '/does-not-exist', 404, 'NOT_FOUND'),
    ('post', '/me', 405, 'METHOD_NOT_ALLOWED'),
])
def test_framework_errors(client, method, path, status, code):
    response = getattr(client, method)(path)
    assert response.status_code == status
    assert response.json()['code'] == code


def test_error_body_omits_stack_trace(client):
    response = client.get('/explode')
    assert set(json.loads(response.content)) == {'detail', 'code'}
    assert 'Traceback' not in response.text


def test_http_401_preserves_challenge(client):
    response = client.get('/http-error/401')
    assert response.headers['WWW-Authenticate'] == 'Bearer'
