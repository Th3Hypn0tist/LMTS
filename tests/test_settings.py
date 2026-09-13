from pathlib import Path

from lmts.core.settings import (
    DEFAULT_OUTPUT_FOLDER,
    LMTSSettings,
    MySQLSettings,
    load_settings,
    save_settings,
)


def test_missing_settings_use_defaults(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / 'missing.json')
    assert settings.output_folder == DEFAULT_OUTPUT_FOLDER
    assert settings.mysql == MySQLSettings()


def test_settings_round_trip(tmp_path: Path) -> None:
    path = tmp_path / '.lmts' / 'settings.json'
    saved = LMTSSettings(
        output_folder='custom-exports',
        mysql=MySQLSettings(
            host='db.local',
            database='results',
            username='writer',
            password='secret',
            publish_key='publish',
        ),
    )
    save_settings(saved, path)
    assert load_settings(path) == saved


def test_schema_v1_settings_migrate_output_folder(tmp_path: Path) -> None:
    path = tmp_path / 'settings.json'
    path.write_text('{"schema_version":1,"output_folder":"old-exports"}', encoding='utf-8')
    settings = load_settings(path)
    assert settings.output_folder == 'old-exports'
    assert settings.mysql == MySQLSettings()
