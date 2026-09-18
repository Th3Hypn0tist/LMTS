from pathlib import Path

from lmts.core.settings import (
    DEFAULT_OUTPUT_FOLDER,
    DVSSettings,
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


def test_schema_v3_legacy_dvs_default_migrates_to_all_interfaces(tmp_path: Path) -> None:
    path = tmp_path / 'settings.json'
    path.write_text(
        '{"schema_version":3,"output_folder":"exports","mysql":{},'
        '"dvs":{"host":"127.0.0.1","port":8775,"s3d_root":"../S3D","studio_root":".lmts/dvs"}}',
        encoding='utf-8',
    )
    settings = load_settings(path)
    assert settings.schema_version == 4
    assert settings.dvs == DVSSettings()
    assert settings.dvs.host == '0.0.0.0'


def test_schema_v3_explicit_custom_loopback_dvs_is_preserved(tmp_path: Path) -> None:
    path = tmp_path / 'settings.json'
    path.write_text(
        '{"schema_version":3,"output_folder":"exports","mysql":{},'
        '"dvs":{"host":"127.0.0.1","port":8776,"s3d_root":"../S3D","studio_root":".lmts/dvs"}}',
        encoding='utf-8',
    )
    settings = load_settings(path)
    assert settings.schema_version == 4
    assert settings.dvs.host == '127.0.0.1'
    assert settings.dvs.port == 8776
