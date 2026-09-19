from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

from lmts.repositories.user import InviteRecord, UserRepository

from .auth import UserIdentity, is_origin


class InviteError(RuntimeError):
    pass


def hash_invite_token(raw_token: str) -> str:
    token = raw_token.strip()
    if not token:
        raise ValueError('invite token must not be empty')
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class CreatedInvite:
    invite_id: str
    raw_token: str
    owner_user_id: str
    expires_at: str | None


class InviteService:
    def __init__(self, repository: UserRepository) -> None:
        self.repository = repository

    @staticmethod
    def can_create_invite(identity: UserIdentity) -> bool:
        return is_origin(identity.user_id) or identity.tier in {1, 2, 1337}

    def create_invite(
        self,
        owner: UserIdentity,
        *,
        expires_in: timedelta | None = None,
    ) -> CreatedInvite:
        if not self.can_create_invite(owner):
            raise InviteError('current user does not have invite authority')
        seconds = None if expires_in is None else int(expires_in.total_seconds())
        if seconds is not None and seconds <= 0:
            raise ValueError('invite expiry must be positive')
        raw_token = secrets.token_urlsafe(32)
        invite_id = f'inv_{uuid.uuid4().hex}'
        record = self.repository.create_invite(
            invite_id=invite_id,
            owner_user_id=owner.user_id,
            token_hash=hash_invite_token(raw_token),
            expires_in_seconds=seconds,
        )
        return CreatedInvite(
            invite_id=record.invite_id,
            raw_token=raw_token,
            owner_user_id=record.owner_user_id,
            expires_at=record.expires_at,
        )

    def validate_invite(self, raw_token: str) -> InviteRecord:
        record = self.repository.invite_by_token_hash(hash_invite_token(raw_token))
        if record is None:
            raise InviteError('invalid invite')
        if record.status != 'active' or record.claimed_by_user_id is not None:
            raise InviteError('invite is not active')
        if record.expired:
            raise InviteError('invite has expired')
        return record
