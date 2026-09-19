from __future__ import annotations

from pathlib import Path

import pytest

from lmts.core.settings import MySQLSettings
from lmts.tools import mysql_schema


def test_schema_path_points_to_canonical_ssot() -> None:
    assert mysql_schema.SCHEMA_PATH == Path('schema/schema_v1.sql').resolve()


def test_schema_file_contains_canonical_database_tables() -> None:
    text = mysql_schema.SCHEMA_PATH.read_text(encoding='utf-8')
    assert 'CREATE TABLE IF NOT EXISTS lmts_schema_version' in text
    assert 'CREATE TABLE IF NOT EXISTS users' in text
    assert 'CREATE TABLE IF NOT EXISTS reports' in text
    assert "VALUES ('database_ssot', 1)" in text


def test_install_mysql_schema_uses_connection_port_and_password_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schema = tmp_path / 'schema.sql'
    schema.write_text('SELECT 1;\n', encoding='utf-8')
    seen = {}

    class Completed:
        returncode = 0
        stderr = b''

    def fake_run(command, **kwargs):
        seen['command'] = command
        seen['env'] = kwargs['env']
        return Completed()

    monkeypatch.setattr(mysql_schema.shutil, 'which', lambda name: '/usr/bin/mariadb' if name == 'mariadb' else None)
    monkeypatch.setattr(mysql_schema.subprocess, 'run', fake_run)
    settings = MySQLSettings(host='db.example.test', port=3307, database='benchmark', username='schema_owner', password='secret-value', publish_key='publish-key')
    mysql_schema.install_mysql_schema(settings, schema_path=schema)
    assert '--host=db.example.test' in seen['command']
    assert '--port=3307' in seen['command']
    assert '--user=schema_owner' in seen['command']
    assert 'benchmark' in seen['command']
    assert seen['env']['MYSQL_PWD'] == 'secret-value'


def test_mysql_settings_rejects_empty_password() -> None:
    with pytest.raises(ValueError, match='MySQL password must not be empty'):
        MySQLSettings(password='')


def test_install_mysql_schema_rejects_missing_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mysql_schema.shutil, 'which', lambda _name: None)
    with pytest.raises(RuntimeError, match='mariadb/mysql client is required'):
        mysql_schema.install_mysql_schema(MySQLSettings())
