from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmts.services.auth import (
    IAM_BASE_URL,
    AuthService,
    AuthenticationError,
    IAMHTTPClient,
    IAMSession,
    IAMTokenStore,
    UserIdentity,
    is_origin,
)


def _identity() -> UserIdentity:
    return UserIdentity('0', 'origin', 1337, True)


def _session() -> IAMSession:
    return IAMSession('opaque-token', '2026-10-22T18:00:00Z', _identity())


def _success_payload(*, token: bool = True) -> dict[str, object]:
    payload: dict[str, object] = {
        'ok': True,
        'contract': 'iam.light',
        'version': '1.0',
        'auth_level': 'light',
        'user': {
            'id': '0',
            'username': 'origin',
            'status': 'active',
            'verified': True,
        },
        'claims': {'tier': 1337},
    }
    if token:
        payload['token'] = 'opaque-token'
        payload['expires_at'] = '2026-10-22T18:00:00Z'
    return payload


def test_iam_base_url_is_fixed() -> None:
    assert IAMHTTPClient().base_url == IAM_BASE_URL
    with pytest.raises(ValueError, match='fixed'):
        IAMHTTPClient('https://example.invalid/iam')


def test_login_uses_iam_http_contract_and_stores_only_token(tmp_path: Path) -> None:
    calls: list[tuple[str, str, dict[str, object] | None, str | None]] = []

    def transport(method, url, payload, token):
        calls.append((method, url, payload, token))
        return _success_payload()

    store = IAMTokenStore(tmp_path / 'auth-session.json')
    auth = AuthService(IAMHTTPClient(transport=transport), token_store=store)

    identity = auth.login('origin', 'secret-password')

    assert identity == _identity()
    assert calls == [(
        'POST',
        IAM_BASE_URL + '/api/login.php',
        {'username': 'origin', 'password': 'secret-password'},
        None,
    )]
    raw = (tmp_path / 'auth-session.json').read_text(encoding='utf-8')
    assert 'secret-password' not in raw
    assert 'opaque-token' in raw
    assert (tmp_path / 'auth-session.json').stat().st_mode & 0o777 == 0o600


def test_current_identity_restores_session_through_me(tmp_path: Path) -> None:
    calls: list[tuple[str, str, dict[str, object] | None, str | None]] = []

    def transport(method, url, payload, token):
        calls.append((method, url, payload, token))
        return _success_payload(token=False)

    store = IAMTokenStore(tmp_path / 'auth-session.json')
    store.save(_session())
    auth = AuthService(IAMHTTPClient(transport=transport), token_store=store)

    identity = auth.current_identity()

    assert identity == _identity()
    assert calls == [(
        'GET',
        IAM_BASE_URL + '/api/me.php',
        None,
        'opaque-token',
    )]


def test_unauthorized_me_clears_local_token(tmp_path: Path) -> None:
    def transport(method, url, payload, token):
        raise AuthenticationError('invalid or expired session', status=401)

    store = IAMTokenStore(tmp_path / 'auth-session.json')
    store.save(_session())
    auth = AuthService(IAMHTTPClient(transport=transport), token_store=store)

    with pytest.raises(AuthenticationError, match='expired'):
        auth.current_identity()

    assert not (tmp_path / 'auth-session.json').exists()


def test_register_propagates_locked_invite_error(tmp_path: Path) -> None:
    def transport(method, url, payload, token):
        assert method == 'POST'
        assert url == IAM_BASE_URL + '/api/register.php'
        raise AuthenticationError('Invite code not valid.', status=400)

    auth = AuthService(
        IAMHTTPClient(transport=transport),
        token_store=IAMTokenStore(tmp_path / 'auth-session.json'),
    )

    with pytest.raises(AuthenticationError, match=r'^Invite code not valid\.$'):
        auth.register('wrong', 'tester', 'tester-password')


def test_logout_revokes_remote_session_and_deletes_local_token(tmp_path: Path) -> None:
    calls: list[tuple[str, str, dict[str, object] | None, str | None]] = []

    def transport(method, url, payload, token):
        calls.append((method, url, payload, token))
        return {
            'ok': True,
            'contract': 'iam.light',
            'version': '1.0',
        }

    store = IAMTokenStore(tmp_path / 'auth-session.json')
    store.save(_session())
    auth = AuthService(IAMHTTPClient(transport=transport), token_store=store)

    auth.logout()

    assert calls == [(
        'POST',
        IAM_BASE_URL + '/api/logout.php',
        None,
        'opaque-token',
    )]
    assert not (tmp_path / 'auth-session.json').exists()


def test_origin_identity_semantics_are_preserved() -> None:
    assert is_origin('0')
    assert not is_origin('usr_x')


def test_token_store_rejects_wrong_endpoint(tmp_path: Path) -> None:
    path = tmp_path / 'auth-session.json'
    path.write_text(json.dumps({
        'schema_version': 1,
        'base_url': 'https://example.invalid/iam',
        'token': 'opaque-token',
        'expires_at': '2026-10-22T18:00:00Z',
    }), encoding='utf-8')

    with pytest.raises(AuthenticationError, match='another IAM endpoint'):
        IAMTokenStore(path).load()
