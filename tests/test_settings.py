from pathlib import Path
from lmts.core.settings import DEFAULT_OUTPUT_FOLDER, LMTSSettings, MySQLSettings, PHPAPISettings, load_settings, save_settings

def test_missing_settings_use_defaults(tmp_path: Path) -> None:
    settings = load_settings(tmp_path / 'missing.json')
    assert settings.output_folder == DEFAULT_OUTPUT_FOLDER
    assert settings.mysql_connections == (MySQLSettings(),)
    assert settings.php_api_connections == ()
    assert settings.auto_publish_targets == ()

def test_settings_round_trip_multiple_connections_and_auto_publish(tmp_path: Path) -> None:
    path = tmp_path / '.lmts' / 'settings.json'
    saved = LMTSSettings(
        output_folder='custom-exports',
        mysql_connections=(
            MySQLSettings(id='local', label='Local', host='db.local', port=3307, database='results', username='writer', password='secret', publish_key='legacy'),
            MySQLSettings(id='archive', label='Archive', host='archive.local', database='archive', username='reader', password='secret2', publish_key='legacy2'),
        ),
        php_api_connections=(
            PHPAPISettings(id='studio', label='Studio', base_url='https://studio.example', publish_key='studio-publish'),
            PHPAPISettings(id='visualizer', label='Visualizer', base_url='https://visualizer.example', publish_key='visualizer-publish'),
        ),
        auto_publish_targets=('mysql:local', 'mysql:archive', 'php_api:studio'),
    )
    save_settings(saved, path)
    assert load_settings(path) == saved

def test_schema_v6_migrates_without_dvs_runtime_configuration(tmp_path: Path) -> None:
    path = tmp_path / 'settings.json'
    path.write_text('{"schema_version":6,"output_folder":"exports","mysql_connections":[{"id":"local","label":"Local","host":"db","database":"lmts","username":"u","password":"p","publish_key":"k"}],"php_api_connections":[],"auto_publish_targets":[],"dvs":{"host":"127.0.0.1","port":8775}}', encoding='utf-8')
    settings = load_settings(path)
    assert settings.schema_version == 7
    assert not hasattr(settings, 'dvs')

def test_schema_v5_migrates_destination_owned_outputs(tmp_path: Path) -> None:
    path = tmp_path / 'settings.json'
    path.write_text('{"schema_version":5,"output_folder":"exports","mysql":{"host":"db","database":"lmts","username":"u","password":"p","publish_key":"k"},"dvstudio_php_api":{"base_url":"https://one.example","publish_key":"one"},"dvisualizer_php_api":{"base_url":"https://two.example","publish_key":"two"},"auto_publish_target":"dvisualizer.php_api","dvs":{"host":"0.0.0.0","port":8775,"s3d_root":"../S3D","studio_root":".lmts/dvs"}}', encoding='utf-8')
    settings = load_settings(path)
    assert [item.id for item in settings.mysql_connections] == ['local']
    assert [item.base_url for item in settings.php_api_connections] == ['https://one.example', 'https://two.example']
    assert settings.auto_publish_targets == ('php_api:legacy-dvisualizer',)
