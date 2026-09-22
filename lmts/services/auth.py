from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from lmts.core.paths import AUTH_SESSION_PATH


IAM_BASE_URL = 'https://aigm.fi/iam'
IAM_CONTRACT = 'iam.light'
IAM_VERSION = '1.0'
SESSION_SCHEMA_VERSION = 1
DEFAULT_TIMEOUT_SECONDS = 15


class AuthenticationError(RuntimeError):
    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class UserIdentity:
    user_id: str
    username: str
    tier: int
    verified: bool
    status: str = 'active'


def is_origin(user_id: str) -> bool:
    return str(user_id) == '0'


@dataclass(frozen=True, slots=True)
class IAMSession:
    token: str
    expires_at: str
    identity: UserIdentity


Transport = Callable[[str, str, dict[str, object] | None, str | None], dict[str, object]]


class IAMHTTPClient:
    """Dependency-free client for the fixed iam.light HTTP boundary."""

    def __init__(
        self,
        base_url: str = IAM_BASE_URL,
        *,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        transport: Transport | None = None,
    ) -> None:
        normalized = base_url.rstrip('/')
        if normalized != IAM_BASE_URL:
            raise ValueError(f'IAM base URL is fixed to {IAM_BASE_URL}')
        if timeout_seconds <= 0:
            raise ValueError('IAM timeout must be positive')
        self.base_url = normalized
        self.timeout_seconds = int(timeout_seconds)
        self._transport = transport

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
        *,
        token: str | None = None,
    ) -> dict[str, object]:
        if self._transport is not None:
            response = self._transport(method, self.base_url + path, payload, token)
            if not isinstance(response, dict):
                raise AuthenticationError('IAM returned an invalid response')
            return self._validate_response(response)

        body = None
        headers = {
            'Accept': 'application/json',
            'User-Agent': 'LMTS/iam.light',
        }
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            headers['Content-Type'] = 'application/json'
        if token is not None:
            headers['Authorization'] = f'Bearer {token}'

        request = Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            try:
                error_payload = json.loads(exc.read().decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError):
                error_payload = {}
            message = (
                str(error_payload.get('error') or '').strip()
                if isinstance(error_payload, dict)
                else ''
            )
            raise AuthenticationError(
                message or f'IAM request failed with HTTP {exc.code}',
                status=int(exc.code),
            ) from None
        except (URLError, TimeoutError, OSError) as exc:
            raise AuthenticationError(f'IAM is unreachable: {exc}') from None

        try:
            decoded = json.loads(raw.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise AuthenticationError('IAM returned invalid JSON') from None
        if not isinstance(decoded, dict):
            raise AuthenticationError('IAM returned an invalid response')
        return self._validate_response(decoded)

    @staticmethod
    def _validate_response(payload: dict[str, object]) -> dict[str, object]:
        if payload.get('ok') is not True:
            raise AuthenticationError(str(payload.get('error') or 'IAM request failed'))
        if payload.get('contract') != IAM_CONTRACT:
            raise AuthenticationError('IAM contract mismatch')
        if payload.get('version') != IAM_VERSION:
            raise AuthenticationError('IAM version mismatch')
        return payload

    @staticmethod
    def _identity(payload: dict[str, object]) -> UserIdentity:
        user = payload.get('user')
        claims = payload.get('claims')
        if not isinstance(user, dict) or not isinstance(claims, dict):
            raise AuthenticationError('IAM identity payload is incomplete')
        try:
            user_id = str(user['id'])
            username = str(user['username'])
            tier = int(claims['tier'])
            status = str(user['status'])
            verified = bool(user['verified'])
        except (KeyError, TypeError, ValueError):
            raise AuthenticationError('IAM identity payload is invalid') from None
        if not user_id or not username:
            raise AuthenticationError('IAM identity payload is invalid')
        return UserIdentity(
            user_id=user_id,
            username=username,
            tier=tier,
            verified=verified,
            status=status,
        )

    def login(self, username: str, password: str) -> IAMSession:
        payload = self._request(
            'POST',
            '/api/login.php',
            {'username': username, 'password': password},
        )
        return self._session(payload)

    def register(
        self,
        invite_code: str,
        username: str,
        password: str,
        *,
        email: str | None = None,
    ) -> IAMSession:
        request_payload: dict[str, object] = {
            'invite_code': invite_code,
            'username': username,
            'password': password,
        }
        if email:
            request_payload['email'] = email
        payload = self._request('POST', '/api/register.php', request_payload)
        return self._session(payload)

    def me(self, token: str) -> UserIdentity:
        return self._identity(self._request('GET', '/api/me.php', token=token))

    def logout(self, token: str) -> None:
        self._request('POST', '/api/logout.php', token=token)

    def _session(self, payload: dict[str, object]) -> IAMSession:
        token = str(payload.get('token') or '')
        expires_at = str(payload.get('expires_at') or '')
        if not token or not expires_at:
            raise AuthenticationError('IAM session payload is incomplete')
        return IAMSession(
            token=token,
            expires_at=expires_at,
            identity=self._identity(payload),
        )


class IAMTokenStore:
    """Private local storage for the opaque IAM bearer token."""

    def __init__(self, path: Path = AUTH_SESSION_PATH) -> None:
        self.path = path

    def save(self, session: IAMSession) -> None:
        payload = {
            'schema_version': SESSION_SCHEMA_VERSION,
            'base_url': IAM_BASE_URL,
            'token': session.token,
            'expires_at': session.expires_at,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + '.tmp')
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding='utf-8',
        )
        os.chmod(temp, 0o600)
        temp.replace(self.path)
        os.chmod(self.path, 0o600)

    def load(self) -> tuple[str, str] | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthenticationError('local IAM session is invalid') from exc
        if not isinstance(payload, dict):
            raise AuthenticationError('local IAM session is invalid')
        if payload.get('schema_version') != SESSION_SCHEMA_VERSION:
            raise AuthenticationError('local IAM session schema is invalid')
        if payload.get('base_url') != IAM_BASE_URL:
            raise AuthenticationError('local IAM session belongs to another IAM endpoint')
        token = str(payload.get('token') or '')
        expires_at = str(payload.get('expires_at') or '')
        if not token or not expires_at:
            raise AuthenticationError('local IAM session is incomplete')
        return token, expires_at

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class AuthService:
    """LMTS authentication boundary backed exclusively by IAM HTTP."""

    def __init__(
        self,
        client: IAMHTTPClient | None = None,
        *,
        token_store: IAMTokenStore | None = None,
    ) -> None:
        self.client = client or IAMHTTPClient()
        self.token_store = token_store or IAMTokenStore()
        self._current: UserIdentity | None = None

    def login(self, username: str, password: str) -> UserIdentity:
        session = self.client.login(username.strip(), password)
        self.token_store.save(session)
        self._current = session.identity
        return session.identity

    def register(
        self,
        raw_invite_token: str,
        username: str,
        password: str,
        *,
        email: str | None = None,
    ) -> UserIdentity:
        session = self.client.register(
            raw_invite_token.strip(),
            username.strip(),
            password,
            email=None if email is None else email.strip(),
        )
        self.token_store.save(session)
        self._current = session.identity
        return session.identity

    def current_identity(self) -> UserIdentity | None:
        if self._current is not None:
            return self._current
        stored = self.token_store.load()
        if stored is None:
            return None
        token, _expires_at = stored
        try:
            identity = self.client.me(token)
        except AuthenticationError as exc:
            if exc.status == 401:
                self.token_store.clear()
            raise
        self._current = identity
        return identity

    def require_identity(self) -> UserIdentity:
        identity = self.current_identity()
        if identity is None:
            raise AuthenticationError('not authenticated')
        return identity

    def logout(self) -> None:
        stored = self.token_store.load()
        token = None if stored is None else stored[0]
        try:
            if token is not None:
                self.client.logout(token)
        finally:
            self._current = None
            self.token_store.clear()
