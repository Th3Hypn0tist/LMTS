from __future__ import annotations
from pathlib import Path

SETTINGS_ACTIONS = Path('lmts/view/actions/settings.py')

def test_mysql_connection_manager_exposes_test_and_schema_install() -> None:
    text = SETTINGS_ACTIONS.read_text(encoding='utf-8')
    assert 'from lmts.tools.mysql_reports import test_mysql_connection' in text
    assert 'from lmts.tools.mysql_schema import install_mysql_schema' in text
    assert "['Edit connection', 'Test connection', 'Install LMTS schema', 'Delete']" in text
    assert 'test_mysql_connection(current)' in text
    assert 'install_mysql_schema(current)' in text

def test_auto_publish_output_selection_is_multi_select() -> None:
    text = SETTINGS_ACTIONS.read_text(encoding='utf-8')
    block = text.split('def edit_auto_publish_targets', 1)[1].split('def edit_dvs', 1)[0]
    assert 'choose_many(' in block
    assert 'All report outputs' in block
    assert 'auto_publish_targets' in block
