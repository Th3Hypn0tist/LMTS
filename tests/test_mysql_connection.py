from __future__ import annotations

import pytest

import lmts.tools.mysql_reports as reports
from lmts.core.settings import MySQLSettings


def _mysql() -> MySQLSettings:
    return MySQLSettings(
        host='db.example',
        database='lmts',
        username='lmts',
        password='secret',
        publish_key='unused',
    )


def test_mysql_connection_uses_saved_database_connection(monkeypatch) -> None:
    seen = {}

    def fake_run(mysql, query):
        seen['mysql'] = mysql
        seen['query'] = query
        return '1\n'

    monkeypatch.setattr(reports, '_run', fake_run)
    reports.test_mysql_connection(_mysql())

    assert seen['mysql'] == _mysql()
    assert seen['query'] == 'SELECT 1'


def test_mysql_connection_rejects_unexpected_result(monkeypatch) -> None:
    monkeypatch.setattr(reports, '_run', lambda mysql, query: '0\n')
    with pytest.raises(RuntimeError, match='unexpected result'):
        reports.test_mysql_connection(_mysql())


def test_mysql_query_is_streamed_via_stdin_not_argv(monkeypatch) -> None:
    seen = {}

    class Completed:
        returncode = 0
        stdout = b'1\n'
        stderr = b''

    monkeypatch.setattr(reports.shutil, 'which', lambda name: '/usr/bin/mariadb' if name == 'mariadb' else None)

    def fake_run(command, **kwargs):
        seen['command'] = command
        seen['input'] = kwargs['input']
        return Completed()

    monkeypatch.setattr(reports.subprocess, 'run', fake_run)

    query = 'SELECT ' + ('x' * 300000)
    reports._run(_mysql(), query)

    assert '--execute' not in seen['command']
    assert query not in seen['command']
    assert seen['input'].startswith(query.encode('utf-8'))
    assert seen['input'].endswith(b';\n')
