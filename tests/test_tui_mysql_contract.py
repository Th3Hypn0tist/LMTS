from __future__ import annotations

from pathlib import Path


SETTINGS_ACTIONS = Path('lmts/view/actions/settings.py')


def test_mysql_settings_menu_exposes_connection_test_and_schema_install_actions() -> None:
    text = SETTINGS_ACTIONS.read_text(encoding='utf-8')
    assert 'from lmts.tools.mysql_reports import test_mysql_connection' in text
    assert 'from lmts.tools.mysql_schema import install_mysql_schema' in text
    assert "['Edit connection', 'Test connection', 'Install LMTS schema']" in text.replace('\n', '').replace('            ', '')
    assert 'test_mysql_connection(mysql)' in text
    assert 'install_mysql_schema(mysql)' in text
    assert "Install into {mysql.username}@{mysql.host}/{mysql.database}" in text


def test_mysql_schema_install_uses_saved_connection_without_sudo() -> None:
    text = SETTINGS_ACTIONS.read_text(encoding='utf-8')
    block = text.split('def edit_mysql', 1)[1].split('def edit_dvs', 1)[0]
    assert 'sudo' not in block
    assert 'CREATE USER' not in block
    assert 'GRANT ' not in block
