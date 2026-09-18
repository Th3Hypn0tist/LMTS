from __future__ import annotations

from lmts.view.registries import build_shortcut_registry


def test_settings_footer_exposes_only_two_report_output_actions() -> None:
    registry = build_shortcut_registry()
    settings = registry.definitions(('settings',))
    labels = [item.label for item in settings if item.topic == 'Settings']
    assert 'Output folder' in labels
    assert 'Report output' in labels
    assert 'Server setup' not in labels
    assert 'MySQL' not in labels
    assert 'FTP' not in labels
    assert 'Report API' not in labels


def test_legacy_output_shortcut_overrides_do_not_break_startup() -> None:
    registry = build_shortcut_registry({
        'settings.server': ('i',),
        'settings.mysql': ('m',),
        'settings.ftp': ('f',),
        'settings.report': ('r',),
    })
    labels = [item.label for item in registry.definitions(('settings',))]
    assert 'Report output' in labels
