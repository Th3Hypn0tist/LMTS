from pathlib import Path

from lmts.core.settings import DEFAULT_OUTPUT_FOLDER, LMTSSettings, load_settings, save_settings


def test_missing_settings_use_defaults(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / 'missing.json')
    assert settings.output_folder == DEFAULT_OUTPUT_FOLDER


def test_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / '.lmts' / 'settings.json'
    saved = LMTSSettings(output_folder='custom-exports')
    save_settings(saved, path)
    assert load_settings(path) == saved
