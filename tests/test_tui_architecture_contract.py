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


def test_tui_application_owns_one_event_bus_and_interactive_host_boundary() -> None:
    text = APP.read_text(encoding='utf-8')
    assert 'UIEventBus()' in text
    assert 'host_class = LMTSInteractiveHost' in text
    assert 'self.host_class(' in text
    assert 'RegistrySplitCursesViewHost(' not in text
    assert 'events=self.state.events' in text


def test_actions_do_not_bypass_message_or_modal_boundaries() -> None:
    base = Path('lmts/view/actions/base.py').read_text(encoding='utf-8')
    benchmark = Path('lmts/view/actions/benchmark.py').read_text(encoding='utf-8')
    settings = Path('lmts/view/actions/settings.py').read_text(encoding='utf-8')
    assert 'self.host.message =' not in base
    assert "publish('ui.message'" in base
    assert 'from lmts.lib.view import choose_with_preview' not in benchmark
    assert 'self.host.choose_with_preview(' in benchmark
    assert 'from lmts.lib.view import choose_directory' not in settings
    assert 'self.host.choose_directory(' in settings


def test_tui_uses_settings_service_as_persistence_boundary() -> None:
    app = APP.read_text(encoding='utf-8')
    settings = Path('lmts/view/actions/settings.py').read_text(encoding='utf-8')
    assert 'SettingsService()' in app
    assert 'load_settings' not in app
    assert 'load_shortcut_overrides' not in app
    assert 'save_settings' not in settings
    assert 'save_shortcut_overrides' not in settings
    assert 'self.settings_service.save_core(' in settings
    assert 'self.settings_service.save_shortcuts(' in settings


def test_remote_server_deploy_is_not_implemented_in_tui_entrypoint_or_settings_action() -> None:
    entrypoint = TUI.read_text(encoding='utf-8')
    settings = Path('lmts/view/actions/settings.py').read_text(encoding='utf-8')
    assert 'deploy_web_root' not in entrypoint
    assert 'deploy_mysql_config' not in entrypoint
    assert 'settings.mysql' not in settings.split('def server_setup', 1)[1].split('def shortcut_editor', 1)[0]
    assert 'manage_server_setup' in settings
