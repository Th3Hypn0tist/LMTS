from __future__ import annotations

import json
from dataclasses import dataclass

from lmts.core.settings import MySQLSettings
from lmts.tools.mysql_reports import _hex_text, _run


@dataclass(frozen=True, slots=True)
class UserRecord:
    user_id: str
    username: str
    tier: int
    status: str
    verified: bool


@dataclass(frozen=True, slots=True)
class AccountRecord:
    user: UserRecord
    password_hash: str
    account_status: str
    email: str | None



@dataclass(frozen=True, slots=True)
class UserActivityRecord:
    reports: int
    submissions: int
    result_records: int
    pass_records: int
    fail_records: int
    error_records: int
    cancelled_records: int
    unknown_records: int
    test_definitions: int
    test_versions: int
    telemetry_values: int
    models: int
    compositions: int
    systems: int
    compute_profiles: int
    hardware_nodes: int

    def to_dict(self) -> dict[str, int]:
        return {
            'reports': self.reports,
            'submissions': self.submissions,
            'result_records': self.result_records,
            'pass': self.pass_records,
            'fail': self.fail_records,
            'error': self.error_records,
            'cancelled': self.cancelled_records,
            'unknown': self.unknown_records,
            'test_definitions': self.test_definitions,
            'test_versions': self.test_versions,
            'telemetry_values': self.telemetry_values,
            'models': self.models,
            'compositions': self.compositions,
            'systems': self.systems,
            'compute_profiles': self.compute_profiles,
            'hardware_nodes': self.hardware_nodes,
        }


@dataclass(frozen=True, slots=True)
class InviteRecord:
    invite_id: str
    owner_user_id: str
    status: str
    claimed_by_user_id: str | None
    expires_at: str | None
    expired: bool


def _json_last(raw: str) -> dict[str, object] | None:
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        return None
    payload = json.loads(lines[-1])
    if not isinstance(payload, dict):
        raise RuntimeError('MySQL user query did not return an object')
    return payload


def _nullable_text(value: str | None) -> str:
    return 'NULL' if value is None else _hex_text(value)


def _user_from_payload(payload: dict[str, object]) -> UserRecord:
    return UserRecord(
        user_id=str(payload['user_id']),
        username=str(payload['username']),
        tier=int(payload['tier']),
        status=str(payload['status']),
        verified=bool(payload['verified']),
    )


class UserRepository:
    """MariaDB persistence boundary for users, accounts and invites."""

    def __init__(self, mysql: MySQLSettings) -> None:
        self.mysql = mysql

    def user_by_id(self, user_id: str) -> UserRecord | None:
        query = f"""
SELECT JSON_OBJECT(
  'user_id', user_id,
  'username', username,
  'tier', tier,
  'status', status,
  'verified', verified
)
FROM users
WHERE user_id = {_hex_text(user_id)}
LIMIT 1
""".strip()
        payload = _json_last(_run(self.mysql, query))
        return None if payload is None else _user_from_payload(payload)

    def user_by_username(self, username: str) -> UserRecord | None:
        query = f"""
SELECT JSON_OBJECT(
  'user_id', user_id,
  'username', username,
  'tier', tier,
  'status', status,
  'verified', verified
)
FROM users
WHERE username = {_hex_text(username)}
LIMIT 1
""".strip()
        payload = _json_last(_run(self.mysql, query))
        return None if payload is None else _user_from_payload(payload)

    def _account(self, where_sql: str) -> AccountRecord | None:
        query = f"""
SELECT JSON_OBJECT(
  'user_id', u.user_id,
  'username', u.username,
  'tier', u.tier,
  'status', u.status,
  'verified', u.verified,
  'password_hash', a.password_hash,
  'account_status', a.account_status,
  'email', a.email
)
FROM users u
JOIN user_accounts a ON a.user_id = u.user_id
WHERE {where_sql}
LIMIT 1
""".strip()
        payload = _json_last(_run(self.mysql, query))
        if payload is None:
            return None
        return AccountRecord(
            user=_user_from_payload(payload),
            password_hash=str(payload['password_hash']),
            account_status=str(payload['account_status']),
            email=None if payload.get('email') is None else str(payload['email']),
        )

    def account_by_username(self, username: str) -> AccountRecord | None:
        return self._account(f"u.username = {_hex_text(username)}")

    def account_by_user_id(self, user_id: str) -> AccountRecord | None:
        return self._account(f"u.user_id = {_hex_text(user_id)}")

    def attach_account(self, user_id: str, password_hash: str, email: str | None = None) -> bool:
        query = f"""
INSERT INTO user_accounts (user_id, password_hash, email, account_status)
SELECT {_hex_text(user_id)}, {_hex_text(password_hash)}, {_nullable_text(email)}, 'active'
FROM users
WHERE user_id = {_hex_text(user_id)}
  AND NOT EXISTS (SELECT 1 FROM user_accounts WHERE user_id = {_hex_text(user_id)});
SELECT ROW_COUNT()
""".strip()
        return _run(self.mysql, query).strip().splitlines()[-1:] == ['1']


    def activity_for_user(self, user_id: str) -> UserActivityRecord:
        user_sql = _hex_text(user_id)
        query = f"""
SELECT JSON_OBJECT(
  'reports', (SELECT COUNT(DISTINCT report_id) FROM report_record_index WHERE tester_user_id = {user_sql}),
  'submissions', (SELECT COUNT(*) FROM report_submissions WHERE submitter_user_id = {user_sql}),
  'result_records', (SELECT COUNT(*) FROM report_record_index WHERE tester_user_id = {user_sql}),
  'pass_records', (SELECT COUNT(*) FROM report_record_index WHERE tester_user_id = {user_sql} AND outcome = 'pass'),
  'fail_records', (SELECT COUNT(*) FROM report_record_index WHERE tester_user_id = {user_sql} AND outcome = 'fail'),
  'error_records', (SELECT COUNT(*) FROM report_record_index WHERE tester_user_id = {user_sql} AND outcome = 'error'),
  'cancelled_records', (SELECT COUNT(*) FROM report_record_index WHERE tester_user_id = {user_sql} AND outcome = 'cancelled'),
  'unknown_records', (
    SELECT COUNT(*) FROM report_record_index
    WHERE tester_user_id = {user_sql}
      AND (outcome IS NULL OR outcome NOT IN ('pass','fail','error','cancelled'))
  ),
  'test_definitions', (
    SELECT COUNT(DISTINCT tv.test_definition_id)
    FROM report_record_index rri
    JOIN test_versions tv ON tv.test_version_id = rri.test_version_id
    WHERE rri.tester_user_id = {user_sql}
  ),
  'test_versions', (
    SELECT COUNT(DISTINCT test_version_id)
    FROM report_record_index
    WHERE tester_user_id = {user_sql} AND test_version_id IS NOT NULL
  ),
  'telemetry_values', (SELECT COUNT(*) FROM telemetry_values WHERE user_id = {user_sql}),
  'models', (
    SELECT COUNT(DISTINCT model_node_id)
    FROM report_record_index
    WHERE tester_user_id = {user_sql} AND model_node_id IS NOT NULL
  ),
  'compositions', (
    SELECT COUNT(DISTINCT composition_id)
    FROM report_record_index
    WHERE tester_user_id = {user_sql} AND composition_id IS NOT NULL
  ),
  'systems', (
    SELECT COUNT(DISTINCT system_id)
    FROM report_record_index
    WHERE tester_user_id = {user_sql} AND system_id IS NOT NULL
  ),
  'compute_profiles', (
    SELECT COUNT(DISTINCT compute_profile_id)
    FROM report_record_index
    WHERE tester_user_id = {user_sql} AND compute_profile_id IS NOT NULL
  ),
  'hardware_nodes', (
    SELECT COUNT(DISTINCT rrhi.hardware_id)
    FROM report_record_hardware_index rrhi
    JOIN report_record_index rri
      ON rri.report_id = rrhi.report_id
     AND rri.record_id = rrhi.record_id
    WHERE rri.tester_user_id = {user_sql}
  )
)
""".strip()
        payload = _json_last(_run(self.mysql, query))
        if payload is None:
            raise RuntimeError('user activity query returned no data')
        names = (
            'reports', 'submissions', 'result_records',
            'pass_records', 'fail_records', 'error_records', 'cancelled_records', 'unknown_records',
            'test_definitions', 'test_versions', 'telemetry_values',
            'models', 'compositions', 'systems', 'compute_profiles', 'hardware_nodes',
        )
        values: dict[str, int] = {}
        for name in names:
            raw = payload.get(name)
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise RuntimeError(f'invalid user activity count for {name}: {raw!r}')
            values[name] = int(raw)
        return UserActivityRecord(**values)

    def create_invite(
        self,
        *,
        invite_id: str,
        owner_user_id: str,
        token_hash: str,
        expires_in_seconds: int | None,
    ) -> InviteRecord:
        if expires_in_seconds is not None and expires_in_seconds <= 0:
            raise ValueError('invite expiry must be positive')
        expires_sql = (
            'NULL'
            if expires_in_seconds is None
            else f'DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL {int(expires_in_seconds)} SECOND)'
        )
        query = f"""
INSERT INTO invites (invite_id, owner_user_id, token_hash, expires_at, status)
VALUES (
  {_hex_text(invite_id)},
  {_hex_text(owner_user_id)},
  {_hex_text(token_hash)},
  {expires_sql},
  'active'
)
""".strip()
        _run(self.mysql, query)
        record = self.invite_by_token_hash(token_hash)
        if record is None:
            raise RuntimeError('created invite could not be read back')
        return record

    def invite_by_token_hash(self, token_hash: str) -> InviteRecord | None:
        query = f"""
SELECT JSON_OBJECT(
  'invite_id', invite_id,
  'owner_user_id', owner_user_id,
  'status', status,
  'claimed_by_user_id', claimed_by_user_id,
  'expires_at', IF(expires_at IS NULL, NULL, DATE_FORMAT(expires_at, '%Y-%m-%dT%H:%i:%s.%f')),
  'expired', IF(expires_at IS NOT NULL AND expires_at <= CURRENT_TIMESTAMP(6), 1, 0)
)
FROM invites
WHERE token_hash = {_hex_text(token_hash)}
LIMIT 1
""".strip()
        payload = _json_last(_run(self.mysql, query))
        if payload is None:
            return None
        return InviteRecord(
            invite_id=str(payload['invite_id']),
            owner_user_id=str(payload['owner_user_id']),
            status=str(payload['status']),
            claimed_by_user_id=None if payload.get('claimed_by_user_id') is None else str(payload['claimed_by_user_id']),
            expires_at=None if payload.get('expires_at') is None else str(payload['expires_at']),
            expired=bool(payload['expired']),
        )

    def register_from_invite(
        self,
        *,
        token_hash: str,
        user_id: str,
        username: str,
        password_hash: str,
        email: str | None,
    ) -> bool:
        if user_id == '0':
            raise ValueError("normal registration may not allocate Origin user_id '0'")
        query = f"""
START TRANSACTION;
SELECT invite_id
FROM invites
WHERE token_hash = {_hex_text(token_hash)}
FOR UPDATE;
INSERT INTO users (user_id, username, tier, status, verified)
SELECT {_hex_text(user_id)}, {_hex_text(username)}, 3, 'active', FALSE
FROM invites
WHERE token_hash = {_hex_text(token_hash)}
  AND status = 'active'
  AND claimed_by_user_id IS NULL
  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP(6))
LIMIT 1;
INSERT INTO user_accounts (user_id, password_hash, email, account_status)
SELECT {_hex_text(user_id)}, {_hex_text(password_hash)}, {_nullable_text(email)}, 'active'
FROM users
WHERE user_id = {_hex_text(user_id)};
UPDATE invites
SET status = 'claimed',
    claimed_by_user_id = {_hex_text(user_id)},
    claimed_at = CURRENT_TIMESTAMP(6)
WHERE token_hash = {_hex_text(token_hash)}
  AND status = 'active'
  AND claimed_by_user_id IS NULL
  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP(6))
  AND EXISTS (SELECT 1 FROM users WHERE user_id = {_hex_text(user_id)});
COMMIT;
SELECT JSON_OBJECT(
  'created', EXISTS(SELECT 1 FROM users WHERE user_id = {_hex_text(user_id)}),
  'claimed', EXISTS(
    SELECT 1
    FROM invites
    WHERE token_hash = {_hex_text(token_hash)}
      AND status = 'claimed'
      AND claimed_by_user_id = {_hex_text(user_id)}
  )
)
""".strip()
        payload = _json_last(_run(self.mysql, query))
        return bool(payload and payload.get('created') and payload.get('claimed'))
