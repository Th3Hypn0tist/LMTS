from __future__ import annotations

import json

import lmts.repositories.user as user_module
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


def test_user_repository_reads_only_lmts_activity(monkeypatch) -> None:
    payload = {
        'reports': 1,
        'submissions': 2,
        'result_records': 3,
        'pass_records': 1,
        'fail_records': 1,
        'error_records': 1,
        'cancelled_records': 0,
        'unknown_records': 0,
        'test_definitions': 2,
        'test_versions': 2,
        'telemetry_values': 5,
        'models': 1,
        'compositions': 0,
        'systems': 1,
        'compute_profiles': 0,
        'hardware_nodes': 1,
    }
    seen = {}

    def fake_run(mysql, query):
        seen['query'] = query
        return json.dumps(payload) + '\n'

    monkeypatch.setattr(user_module, '_run', fake_run)
    record = UserRepository(_mysql()).activity_for_user('usr_test')

    assert record.reports == 1
    assert 'LMTS_report_record_index' in seen['query']
    assert 'LMTS_telemetry_values' in seen['query']
    assert 'IAM_users' not in seen['query']
    assert 'IAM_user_accounts' not in seen['query']
    assert 'IAM_invites' not in seen['query']
