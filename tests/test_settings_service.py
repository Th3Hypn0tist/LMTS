from __future__ import annotations

from pathlib import Path

from lmts.core.runtime_targets import DEFAULT_RUNTIME_TARGETS_PATH
from lmts.core.shortcut_settings import DEFAULT_SHORTCUT_SETTINGS_PATH
from lmts.services.settings import SettingsService


def test_settings_service_owns_unique_stores_under_one_root(tmp_path: Path) -> None:
    root = (tmp_path / 'lmts-home').resolve()
    service = SettingsService(root)
    stores = service.stores()
    assert [store.id for store in stores] == [
        'core',
        'shortcuts',
        'runtime_targets',
        'ftp_profiles',
        'report_profiles',
    ]
    assert len({store.path for store in stores}) == len(stores)
    assert all(store.path.parent == root for store in stores)


def test_settings_service_core_and_shortcuts_round_trip(tmp_path: Path) -> None:
    service = SettingsService(tmp_path / 'lmts-home')
    core = service.load_core()
    assert core == service.load_core()

    shortcuts = {'benchmark.run': ('r', 'r')}
    service.save_shortcuts(shortcuts)
    assert service.load_shortcuts() == shortcuts


def test_runtime_and_shortcut_defaults_are_canonical_lmts_paths() -> None:
    service = SettingsService()
    assert DEFAULT_RUNTIME_TARGETS_PATH == service.path('runtime_targets')
    assert DEFAULT_SHORTCUT_SETTINGS_PATH == service.path('shortcuts')


def test_unknown_settings_store_fails_explicitly(tmp_path: Path) -> None:
    service = SettingsService(tmp_path / 'lmts-home')
    try:
        service.path('missing')
    except KeyError as exc:
        assert 'unknown settings store: missing' in str(exc)
    else:
        raise AssertionError('unknown settings store must fail')
