from __future__ import annotations

from pathlib import Path

import pytest

from lmts.core.settings import MySQLSettings
from lmts.tools import mysql_schema


def test_schema_file_contains_result_tables() -> None:
    text = mysql_schema.SCHEMA_PATH.read_text(encoding='utf-8')
    assert 'CREATE TABLE IF NOT EXISTS lmts_schema_version' in text
    assert 'CREATE TABLE IF NOT EXISTS reports' in text
    assert "VALUES ('result_server', 1)" in text


def test_install_mysql_schema_uses_settings_and_password_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schema = tmp_path / 'schema.sql'
    schema.write_text('SELECT 1;\n', encoding='utf-8')
    seen = {}

    class Completed:
        returncode = 0
        stderr = b''

    def fake_run(command, **kwargs):
        seen['command'] = command
        seen['env'] = kwargs['env']
        seen['stdin'] = kwargs['stdin'].read()
        return Completed()

    monkeypatch.setattr(mysql_schema.shutil, 'which', lambda name: '/usr/bin/mariadb' if name == 'mariadb' else None)
    monkeypatch.setattr(mysql_schema.subprocess, 'run', fake_run)

    settings = MySQLSettings(
        host='db.example.test',
        database='benchmark',
        username='schema_owner',
        password='secret-value',
        publish_key='publish-key',
    )
    mysql_schema.install_mysql_schema(settings, schema_path=schema)

    assert seen['command'] == [
        '/usr/bin/mariadb',
        '--host=db.example.test',
        '--user=schema_owner',
        '--protocol=tcp',
        '--default-character-set=utf8mb4',
        'benchmark',
    ]
    assert seen['env']['MYSQL_PWD'] == 'secret-value'
    assert seen['stdin'] == b'SELECT 1;\n'


def test_install_mysql_schema_rejects_empty_password_before_client_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def fake_which(_name):
        nonlocal called
        called = True
        return '/usr/bin/mariadb'

    monkeypatch.setattr(mysql_schema.shutil, 'which', fake_which)
    settings = MySQLSettings(password='')
    with pytest.raises(ValueError, match='MySQL password must not be empty'):
        mysql_schema.install_mysql_schema(settings)
    assert called is False


def test_install_mysql_schema_rejects_missing_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mysql_schema.shutil, 'which', lambda _name: None)
    with pytest.raises(RuntimeError, match='mariadb/mysql client is required'):
        mysql_schema.install_mysql_schema(MySQLSettings())


def test_install_mysql_schema_surfaces_client_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schema = tmp_path / 'schema.sql'
    schema.write_text('SELECT 1;\n', encoding='utf-8')

    class Completed:
        returncode = 1
        stderr = b'permission denied'

    monkeypatch.setattr(mysql_schema.shutil, 'which', lambda _name: '/usr/bin/mariadb')
    monkeypatch.setattr(mysql_schema.subprocess, 'run', lambda *args, **kwargs: Completed())

    with pytest.raises(RuntimeError, match='permission denied'):
        mysql_schema.install_mysql_schema(MySQLSettings(), schema_path=schema)


def test_install_mysql_schema_prefers_real_error_over_warning(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    schema = tmp_path / 'schema.sql'
    schema.write_text('SELECT 1;\n', encoding='utf-8')

    class Completed:
        returncode = 1
        stderr = (
            b'WARNING: option --ssl-verify-server-cert is disabled because of an insecure passwordless login.\n'
            b'ERROR 1045 (28000): Access denied for user\n'
        )

    monkeypatch.setattr(mysql_schema.shutil, 'which', lambda _name: '/usr/bin/mariadb')
    monkeypatch.setattr(mysql_schema.subprocess, 'run', lambda *args, **kwargs: Completed())

    with pytest.raises(RuntimeError, match='Access denied for user'):
        mysql_schema.install_mysql_schema(MySQLSettings(), schema_path=schema)
