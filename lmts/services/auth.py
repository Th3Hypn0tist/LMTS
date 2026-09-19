from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import uuid
from dataclasses import dataclass
from pathlib import Path

from lmts.core.paths import AUTH_SESSION_PATH, AUTH_SESSION_SECRET_PATH
from lmts.repositories.user import UserRecord, UserRepository


SCRYPT_N = 1 << 14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SESSION_SCHEMA_VERSION = 1


class AuthenticationError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class UserIdentity:
    user_id: str
    username: str
    tier: int
    verified: bool


def is_origin(user_id: str) -> bool:
    return str(user_id) == '0'


def _password_bytes(password: str) -> bytes:
    if not isinstance(password, str):
        raise TypeError('password must be a string')
    if len(password) < 8:
        raise ValueError('password must be at least 8 characters')
    if len(password) > 1024:
        raise ValueError('password is too long')
    return password.encode('utf-8')


def hash_password(password: str) -> str:
    raw = _password_bytes(password)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(raw, salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=SCRYPT_DKLEN)
    return 'scrypt$' + str(SCRYPT_N) + '$' + str(SCRYPT_R) + '$' + str(SCRYPT_P) + '$' + salt.hex() + '$' + digest.hex()


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, digest_hex = encoded.split('$', 5)
        if scheme != 'scrypt':
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = hashlib.scrypt(
            password.encode('utf-8'),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (TypeError, ValueError):
        return False
    return hmac.compare_digest(actual, expected)


def _identity(user: UserRecord) -> UserIdentity:
    return UserIdentity(
        user_id=user.user_id,
        username=user.username,
        tier=user.tier,
        verified=user.verified,
    )


@dataclass(frozen=True, slots=True)
class AuthSession:
    connection_id: str
    user_id: str


class LocalAuthSessionStore:
    """Signed local session adapter for the LMTS desktop/TUI surface."""

    def __init__(
        self,
        path: Path = AUTH_SESSION_PATH,
        secret_path: Path = AUTH_SESSION_SECRET_PATH,
    ) -> None:
        self.path = path
        self.secret_path = secret_path

    def _secret(self) -> bytes:
        if self.secret_path.exists():
            raw = self.secret_path.read_text(encoding='ascii').strip()
            try:
                value = bytes.fromhex(raw)
            except ValueError as exc:
                raise AuthenticationError('local auth session secret is invalid') from exc
            if len(value) != 32:
                raise AuthenticationError('local auth session secret has invalid length')
            return value
        self.secret_path.parent.mkdir(parents=True, exist_ok=True)
        value = secrets.token_bytes(32)
        temp = self.secret_path.with_name(self.secret_path.name + '.tmp')
        temp.write_text(value.hex(), encoding='ascii')
        os.chmod(temp, 0o600)
        temp.replace(self.secret_path)
        os.chmod(self.secret_path, 0o600)
        return value

    @staticmethod
    def _message(connection_id: str, user_id: str) -> bytes:
        return (connection_id + '\0' + user_id).encode('utf-8')

    def save(self, session: AuthSession) -> None:
        signature = hmac.new(
            self._secret(),
            self._message(session.connection_id, session.user_id),
            hashlib.sha256,
        ).hexdigest()
        payload = {
            'schema_version': SESSION_SCHEMA_VERSION,
            'connection_id': session.connection_id,
            'user_id': session.user_id,
            'signature': signature,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + '.tmp')
        temp.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding='utf-8')
        os.chmod(temp, 0o600)
        temp.replace(self.path)
        os.chmod(self.path, 0o600)

    def load(self) -> AuthSession | None:
        if not self.path.exists():
            return None
        try:
            payload = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise AuthenticationError('local auth session is invalid') from exc
        if not isinstance(payload, dict) or payload.get('schema_version') != SESSION_SCHEMA_VERSION:
            raise AuthenticationError('local auth session schema is invalid')
        connection_id = str(payload.get('connection_id') or '')
        user_id = str(payload.get('user_id') or '')
        signature = str(payload.get('signature') or '')
        expected = hmac.new(
            self._secret(),
            self._message(connection_id, user_id),
            hashlib.sha256,
        ).hexdigest()
        if not connection_id or not user_id or not hmac.compare_digest(signature, expected):
            raise AuthenticationError('local auth session signature is invalid')
        return AuthSession(connection_id=connection_id, user_id=user_id)

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class AuthService:
    def __init__(
        self,
        repository: UserRepository,
        *,
        connection_id: str,
        session_store: LocalAuthSessionStore | None = None,
    ) -> None:
        if not connection_id.strip():
            raise ValueError('auth connection_id must not be empty')
        self.repository = repository
        self.connection_id = connection_id
        self.session_store = session_store or LocalAuthSessionStore()
        self._current: UserIdentity | None = None

    def bootstrap_origin(self, password: str, *, email: str | None = None) -> UserIdentity:
        origin = self.repository.user_by_id('0')
        if origin is None:
            raise AuthenticationError("Origin users row does not exist")
        if self.repository.account_by_user_id('0') is not None:
            raise AuthenticationError('Origin account already exists')
        if not self.repository.attach_account('0', hash_password(password), email):
            raise AuthenticationError('Origin account could not be created')
        identity = _identity(origin)
        self._set_current(identity)
        return identity

    def login(self, username: str, password: str) -> UserIdentity:
        account = self.repository.account_by_username(username)
        if account is None or not verify_password(password, account.password_hash):
            raise AuthenticationError('invalid username or password')
        if account.user.status != 'active' or account.account_status != 'active':
            raise AuthenticationError('account is not active')
        identity = _identity(account.user)
        self._set_current(identity)
        return identity

    def register(
        self,
        raw_invite_token: str,
        username: str,
        password: str,
        *,
        email: str | None = None,
    ) -> UserIdentity:
        from .invite import hash_invite_token

        username = username.strip()
        if not username:
            raise ValueError('username must not be empty')
        user_id = f'usr_{uuid.uuid4().hex}'
        created = self.repository.register_from_invite(
            token_hash=hash_invite_token(raw_invite_token),
            user_id=user_id,
            username=username,
            password_hash=hash_password(password),
            email=email,
        )
        if not created:
            raise AuthenticationError('invite is invalid, expired or already claimed')
        user = self.repository.user_by_id(user_id)
        if user is None:
            raise RuntimeError('registered user could not be read back')
        identity = _identity(user)
        self._set_current(identity)
        return identity

    def _set_current(self, identity: UserIdentity) -> None:
        self._current = identity
        self.session_store.save(AuthSession(connection_id=self.connection_id, user_id=identity.user_id))

    def current_identity(self) -> UserIdentity | None:
        if self._current is not None:
            return self._current
        session = self.session_store.load()
        if session is None:
            return None
        if session.connection_id != self.connection_id:
            raise AuthenticationError(
                f'local auth session belongs to MySQL connection {session.connection_id!r}, not {self.connection_id!r}'
            )
        account = self.repository.account_by_user_id(session.user_id)
        if account is None:
            raise AuthenticationError('session user account no longer exists')
        if account.user.status != 'active' or account.account_status != 'active':
            raise AuthenticationError('session user account is not active')
        self._current = _identity(account.user)
        return self._current

    def require_identity(self) -> UserIdentity:
        identity = self.current_identity()
        if identity is None:
            raise AuthenticationError('not authenticated')
        return identity

    def logout(self) -> None:
        self._current = None
        self.session_store.clear()
