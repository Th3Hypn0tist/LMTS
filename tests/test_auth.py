from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from lmts.repositories.user import AccountRecord, InviteRecord, UserRecord
from lmts.services.auth import (
    AuthService,
    AuthenticationError,
    LocalAuthSessionStore,
    UserIdentity,
    hash_password,
    is_origin,
    verify_password,
)
from lmts.services.invite import InviteError, InviteService


class FakeRepository:
    def __init__(self) -> None:
        self.users = {
            '0': UserRecord('0', 'origin', 1337, 'active', True),
        }
        self.accounts: dict[str, AccountRecord] = {}
        self.invites: dict[str, InviteRecord] = {}

    def user_by_id(self, user_id: str):
        return self.users.get(user_id)

    def account_by_user_id(self, user_id: str):
        return self.accounts.get(user_id)

    def account_by_username(self, username: str):
        return next((item for item in self.accounts.values() if item.user.username == username), None)

    def attach_account(self, user_id: str, password_hash: str, email: str | None = None) -> bool:
        user = self.users.get(user_id)
        if user is None or user_id in self.accounts:
            return False
        self.accounts[user_id] = AccountRecord(user, password_hash, 'active', email)
        return True

    def create_invite(self, *, invite_id, owner_user_id, token_hash, expires_in_seconds):
        record = InviteRecord(invite_id, owner_user_id, 'active', None, None, False)
        self.invites[token_hash] = record
        return record

    def invite_by_token_hash(self, token_hash: str):
        return self.invites.get(token_hash)

    def register_from_invite(self, *, token_hash, user_id, username, password_hash, email):
        invite = self.invites.get(token_hash)
        if invite is None or invite.status != 'active' or invite.expired:
            return False
        user = UserRecord(user_id, username, 3, 'active', False)
        self.users[user_id] = user
        self.accounts[user_id] = AccountRecord(user, password_hash, 'active', email)
        self.invites[token_hash] = replace(invite, status='claimed', claimed_by_user_id=user_id)
        return True


def _store(tmp_path: Path) -> LocalAuthSessionStore:
    return LocalAuthSessionStore(tmp_path / 'session.json', tmp_path / 'secret')


def test_password_hash_round_trip() -> None:
    encoded = hash_password('correct horse battery staple')
    assert encoded.startswith('scrypt$')
    assert verify_password('correct horse battery staple', encoded)
    assert not verify_password('wrong password', encoded)


def test_origin_bootstrap_creates_account_without_creating_origin_user(tmp_path: Path) -> None:
    repo = FakeRepository()
    auth = AuthService(repo, connection_id='local', session_store=_store(tmp_path))

    identity = auth.bootstrap_origin('origin-password')

    assert identity == UserIdentity('0', 'origin', 1337, True)
    assert is_origin(identity.user_id)
    assert list(repo.users) == ['0']
    assert verify_password('origin-password', repo.accounts['0'].password_hash)


def test_register_from_invite_is_tier_three_and_restores_signed_session(tmp_path: Path) -> None:
    repo = FakeRepository()
    auth = AuthService(repo, connection_id='local', session_store=_store(tmp_path))
    origin = auth.bootstrap_origin('origin-password')
    invite = InviteService(repo).create_invite(origin)

    identity = auth.register(invite.raw_token, 'tester', 'tester-password')

    assert identity.tier == 3
    assert identity.user_id.startswith('usr_')
    assert identity.user_id != '0'

    restored = AuthService(repo, connection_id='local', session_store=_store(tmp_path)).current_identity()
    assert restored == identity


def test_tier_three_user_cannot_create_invites() -> None:
    repo = FakeRepository()
    service = InviteService(repo)
    with pytest.raises(InviteError, match='invite authority'):
        service.create_invite(UserIdentity('usr_x', 'reader', 3, False))


def test_session_tampering_is_rejected(tmp_path: Path) -> None:
    repo = FakeRepository()
    auth = AuthService(repo, connection_id='local', session_store=_store(tmp_path))
    auth.bootstrap_origin('origin-password')
    path = tmp_path / 'session.json'
    text = path.read_text(encoding='utf-8').replace('"user_id": "0"', '"user_id": "1337"')
    path.write_text(text, encoding='utf-8')

    with pytest.raises(AuthenticationError, match='signature'):
        AuthService(repo, connection_id='local', session_store=_store(tmp_path)).current_identity()
