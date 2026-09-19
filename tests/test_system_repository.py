from __future__ import annotations

import json

import lmts.repositories.system as system_module
from lmts.core.settings import MySQLSettings
from lmts.repositories.system import SystemRepository, system_id_for


def _mysql() -> MySQLSettings:
    return MySQLSettings(
        host='db.example',
        database='lmts',
        username='lmts',
        password='secret',
        publish_key='unused',
    )


def test_system_id_is_stable_per_user_and_fingerprint() -> None:
    first = system_id_for('usr_a', 'abc')
    assert first == system_id_for('usr_a', 'abc')
    assert first != system_id_for('usr_b', 'abc')
    assert first != system_id_for('usr_a', 'def')
    assert first.startswith('sys_')


def test_ensure_system_upserts_user_owned_profile(monkeypatch) -> None:
    seen = {}

    def fake_run(mysql, query):
        seen['query'] = query
        return json.dumps({
            'system_id': system_id_for('usr_test', 'fingerprint'),
            'user_id': 'usr_test',
            'label': 'System fingerprint',
        }) + '\n'

    monkeypatch.setattr(system_module, '_run', fake_run)
    record = SystemRepository(_mysql()).ensure_system(
        user_id='usr_test',
        fingerprint='fingerprint',
        profile_schema_version=6,
    )

    assert record.user_id == 'usr_test'
    assert record.fingerprint == 'fingerprint'
    assert 'ON DUPLICATE KEY UPDATE' in seen['query']
