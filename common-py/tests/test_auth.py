import secrets
from time import time

import pytest

from referoom_common import Settings, get_settings


def bearer(token):
    return {'Authorization': f'Bearer {token}'}


def assert_error(response, status, code):
    assert response.status_code == status
    assert set(response.json()) == {'detail', 'code'}
    assert response.json()['code'] == code
    assert response.headers['X-Request-Id']
    if status == 401:
        assert response.headers['WWW-Authenticate'] == 'Bearer'


def test_bearer_user_and_voice_id_alias(client, make_token):
    response = client.get('/me', headers=bearer(make_token()))
    assert response.status_code == 200
    assert response.json() == {
        'user_id': 101, 'id': '101', 'username': 'test-member',
        'role': 'member', 'team_id': 7,
    }


@pytest.mark.parametrize('legacy', ['L1', 'L2', 'L4', None, 7])
def test_legacy_level_claim_is_ignored(client, make_token, legacy):
    # v0.2: level은 더 이상 필수도 검증 대상도 아니다. 예전 토큰에 어떤 값이 있어도 통과하고 사용자에게 노출되지 않는다.
    response = client.get('/me', headers=bearer(make_token({'level': legacy})))
    assert response.status_code == 200
    assert 'level' not in response.json()


@pytest.mark.parametrize('legacy', [
    {'view': 'dev'}, {'view': 'all'}, {'view': None},
    {'team_type': 'rnd'}, {'team_type': 'other'}, {'team_type': None},
])
def test_legacy_view_and_team_type_claims_are_ignored(client, make_token, legacy):
    # 관점·팀 유형은 없어졌다. 예전 토큰에 어떤 값이 있어도 통과하고 사용자에게 노출되지 않는다.
    response = client.get('/me', headers=bearer(make_token(legacy)))
    assert response.status_code == 200
    assert not {'view', 'team_type'} & set(response.json())


@pytest.mark.parametrize('name', ['view', 'team_type'])
def test_token_without_view_and_team_type_is_accepted(client, make_token, name):
    assert client.get('/me', headers=bearer(make_token(omit=[name]))).status_code == 200


def test_current_user_has_no_level_view_or_team_type():
    from dataclasses import fields

    from referoom_common import CurrentUser

    assert not {'level', 'view', 'team_type'} & {f.name for f in fields(CurrentUser)}


def test_cookie_fallback(client, make_token):
    client.cookies.set('ACCESS_TOKEN', make_token())
    assert client.get('/team').json() == {'team_id': 7}


@pytest.mark.parametrize('authorization', [
    'Bearer invalid', 'Basic invalid', 'Bearer', '',
])
def test_bad_header_cannot_fall_back_to_good_cookie(client, make_token, authorization):
    client.cookies.set('ACCESS_TOKEN', make_token())
    assert_error(client.get('/team', headers={'Authorization': authorization}),
                 401, 'UNAUTHORIZED')


def test_bearer_takes_precedence_over_cookie(client, make_token):
    client.cookies.set('ACCESS_TOKEN', make_token({'team_id': 8}))
    response = client.get('/team', headers=bearer(make_token({'team_id': 9})))
    assert response.json() == {'team_id': 9}


def test_duplicate_authorization_rejected(client, make_token):
    value = f'Bearer {make_token()}'
    response = client.get('/me', headers=[('Authorization', value),
                                         ('Authorization', value)])
    assert_error(response, 401, 'UNAUTHORIZED')


def test_missing_token(client):
    assert_error(client.get('/me'), 401, 'UNAUTHORIZED')


@pytest.mark.parametrize('kind', [
    'expired', 'bad-signature', 'wrong-issuer', 'hs384', 'unsigned',
    'future-iat', 'future-nbf', 'tampered',
])
def test_invalid_jwt(client, make_token, kind):
    now = int(time())
    if kind == 'expired':
        token = make_token({'iat': now - 120, 'exp': now - 60})
    elif kind == 'bad-signature':
        token = make_token(key=secrets.token_hex(32))
    elif kind == 'wrong-issuer':
        token = make_token({'iss': 'untrusted'})
    elif kind == 'hs384':
        token = make_token(algorithm='HS384', key=secrets.token_hex(48))
    elif kind == 'unsigned':
        token = make_token(algorithm='none')
    elif kind == 'future-iat':
        token = make_token({'iat': now + 120})
    elif kind == 'future-nbf':
        token = make_token({'nbf': now + 120})
    else:
        header, payload, signature = make_token().split('.')
        payload = ('e' if payload[0] != 'e' else 'f') + payload[1:]
        token = '.'.join((header, payload, signature))
    expected = 'TOKEN_EXPIRED' if kind == 'expired' else 'UNAUTHORIZED'
    assert_error(client.get('/me', headers=bearer(token)), 401, expected)


@pytest.mark.parametrize('name', [
    'iss', 'sub', 'username', 'role', 'team_id', 'iat', 'exp',
])
def test_missing_claim(client, make_token, name):
    assert_error(client.get('/me', headers=bearer(make_token(omit=[name]))),
                 401, 'UNAUTHORIZED')


@pytest.mark.parametrize('changes', [
    {'sub': '0'}, {'sub': '-1'}, {'sub': 'abc'}, {'sub': 101},
    {'sub': str(1 << 63)}, {'username': ' '}, {'username': None},
    {'role': 'admin'},
    {'team_id': True}, {'team_id': 0}, {'team_id': -1},
    {'team_id': '7'}, {'team_id': 1 << 63},
    {'iat': True}, {'iat': '123'}, {'exp': '9999999999'},
    {'iat': None}, {'exp': None}, {'iat': 100.5}, {'exp': 9999999999.5},
])
def test_invalid_claim_types_and_values(client, make_token, changes):
    assert_error(client.get('/me', headers=bearer(make_token(changes))),
                 401, 'UNAUTHORIZED')


def test_expiration_checked_before_claim_lifetime_validation(client, make_token):
    # 이미 만료된 토큰은 만료 오류가 우선하며 어느 경우에도 인증되지 않는다.
    token = make_token({'iat': 100, 'exp': 100})
    assert_error(client.get('/me', headers=bearer(token)), 401, 'TOKEN_EXPIRED')


@pytest.mark.parametrize('expired', [False, True])
def test_invalid_cookie_token(client, make_token, expired):
    token = make_token({'iat': 100, 'exp': 200}) if expired else 'invalid'
    client.cookies.set('ACCESS_TOKEN', token)
    code = 'TOKEN_EXPIRED' if expired else 'UNAUTHORIZED'
    assert_error(client.get('/me'), 401, code)


@pytest.mark.parametrize('route,role,team_id,expected,code', [
    ('/me', 'member', None, 200, None),
    ('/team', 'member', None, 403, 'NO_TEAM'),
    ('/admin', 'team_admin', None, 403, 'NO_TEAM'),
    ('/team', 'member', 7, 200, None),
    ('/team', 'team_admin', 7, 200, None),
    ('/admin', 'member', 7, 403, 'FORBIDDEN'),
    ('/admin', 'team_admin', 7, 200, None),
])
def test_team_and_admin_permissions(client, make_token, route, role, team_id, expected, code):
    token = make_token({'role': role, 'team_id': team_id})
    response = client.get(route, headers=bearer(token))
    if code:
        assert_error(response, expected, code)
    else:
        assert response.status_code == expected


@pytest.mark.parametrize('route', ['/team', '/admin'])
def test_permissions_require_authentication(client, route):
    assert_error(client.get(route), 401, 'UNAUTHORIZED')


def test_query_parameters_cannot_override_team(client, make_token):
    response = client.get('/team?team_id=999&role=team_admin',
                          headers=bearer(make_token()))
    assert response.json() == {'team_id': 7}


def test_settings_cache_and_secret_repr(secret):
    first = get_settings()
    assert get_settings() is first
    assert first.jwt_algorithm == 'HS256'
    assert first.jwt_issuer == 'simple-auth-server'
    assert secret not in repr(first)


@pytest.mark.parametrize('value', [None, '', '   '])
def test_settings_missing_secret(secret, monkeypatch, value):
    if value is None:
        monkeypatch.delenv('JWT_SECRET')
    else:
        monkeypatch.setenv('JWT_SECRET', value)
    with pytest.raises(RuntimeError):
        Settings.from_env()


@pytest.mark.parametrize('value', ['', ' , ', '*', 'http://localhost:5174,*'])
def test_settings_reject_invalid_cors(secret, monkeypatch, value):
    monkeypatch.setenv('CORS_ALLOWED_ORIGINS', value)
    with pytest.raises(RuntimeError):
        Settings.from_env()


def test_settings_parse_cors_and_preserve_secret(secret, monkeypatch):
    monkeypatch.setenv('JWT_SECRET', f' {secret} ')
    monkeypatch.setenv('CORS_ALLOWED_ORIGINS', ' http://localhost:5174, http://localhost:8008 ')
    settings = Settings.from_env()
    assert settings.jwt_secret == f' {secret} '
    assert settings.cors_allowed_origins == ('http://localhost:5174', 'http://localhost:8008')
