from __future__ import annotations

from pathlib import Path


TUI = Path('lmts/view/tui.py')


def test_mysql_settings_menu_exposes_schema_install_action() -> None:
    text = TUI.read_text(encoding='utf-8')
    assert "from lmts.tools.mysql_schema import install_mysql_schema" in text
    assert "['Edit connection', 'Install LMTS schema']" in text
    assert "install_mysql_schema(mysql)" in text
    assert "Install into {mysql.username}@{mysql.host}/{mysql.database}" in text


def test_mysql_schema_install_uses_saved_connection_without_sudo() -> None:
    text = TUI.read_text(encoding='utf-8')
    block = text.split('def edit_mysql', 1)[1].split('def ftp_settings', 1)[0]
    assert 'sudo' not in block
    assert 'CREATE USER' not in block
    assert 'GRANT ' not in block
