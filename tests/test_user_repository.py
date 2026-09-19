from __future__ import annotations

import json

from lmts.core.settings import MySQLSettings
from lmts.repositories.user import UserRepository


def _mysql() -> MySQLSettings:
    return MySQLSettings(
        host='db.example',
        database='lmts',
        username='lmts',
        password='secret',
        publish_key='unused',
    )


def test_registration_query_locks_invite_and_forces_tier_three(monkeypatch) -> None:
    seen = {}

    def fake_run(mysql, query):
        seen['mysql'] = mysql
        seen['query'] = query
        return 'inv_example\n' + json.dumps({'created': 1, 'claimed': 1}) + '\n'

    monkeypatch.setattr('lmts.repositories.user._run', fake_run)
    repo = UserRepository(_mysql())

    assert repo.register_from_invite(
        token_hash='abc',
        user_id='usr_test',
        username='tester',
        password_hash='hash',
        email=None,
    )

    query = seen['query']
    assert 'FOR UPDATE' in query
    assert "3, 'active', FALSE" in query
    assert "status = 'claimed'" in query
    assert 'CURRENT_TIMESTAMP(6)' in query


def test_normal_registration_rejects_origin_id() -> None:
    repo = UserRepository(_mysql())
    try:
        repo.register_from_invite(
            token_hash='abc',
            user_id='0',
            username='tester',
            password_hash='hash',
            email=None,
        )
    except ValueError as exc:
        assert 'Origin' in str(exc)
    else:
        raise AssertionError('Origin id must not be accepted by normal registration')
