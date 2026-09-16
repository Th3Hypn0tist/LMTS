from __future__ import annotations

from pathlib import Path


TUI = Path('lmts/view/tui.py')
APP = Path('lmts/view/tui_app.py')


def test_tui_entrypoint_is_only_a_composition_launcher() -> None:
    text = TUI.read_text(encoding='utf-8')
    assert 'from .tui_app import TUIApplication' in text
    assert 'LMTSViewController' not in text
    assert 'lmts.core' not in text
    assert 'lmts.tools' not in text
    assert len(text.splitlines()) <= 20


def test_tui_application_uses_extracted_action_domains() -> None:
    text = APP.read_text(encoding='utf-8')
    for module in (
        'BenchmarkActions',
        'NavigationActions',
        'ProfileActions',
        'ResultActions',
        'SettingsActions',
        'TUIRenderer',
        'TUIState',
    ):
        assert module in text


def test_remote_server_deploy_is_not_implemented_in_tui_entrypoint_or_settings_action() -> None:
    entrypoint = TUI.read_text(encoding='utf-8')
    settings = Path('lmts/view/actions/settings.py').read_text(encoding='utf-8')
    assert 'deploy_web_root' not in entrypoint
    assert 'deploy_mysql_config' not in entrypoint
    assert 'settings.mysql' not in settings.split('def server_setup', 1)[1].split('def shortcut_editor', 1)[0]
    assert 'manage_server_setup' in settings
