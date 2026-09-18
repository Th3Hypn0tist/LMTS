from pathlib import Path
from lmts.core.settings import LMTSSettings, MySQLSettings, PHPAPISettings, save_settings
from lmts.dvs.report_sources import load_all_dvs_report_sources

def test_dvs_inherits_all_lmts_report_outputs(tmp_path: Path) -> None:
    settings_path = tmp_path / 'settings.json'
    save_settings(
        LMTSSettings(
            mysql_connections=(
                MySQLSettings(id='local', label='Local', host='db.internal', port=3307, database='results', username='reader', password='secret', publish_key='legacy'),
                MySQLSettings(id='archive', label='Archive', host='archive.internal', database='archive', username='reader2', password='secret2', publish_key='legacy2'),
            ),
            php_api_connections=(
                PHPAPISettings(id='studio', label='Studio', base_url='https://studio.example', publish_key='studio-key'),
                PHPAPISettings(id='visualizer', label='Visualizer', base_url='https://visualizer.example', publish_key='visualizer-key'),
            ),
        ),
        settings_path,
    )
    sources = load_all_dvs_report_sources(settings_path)
    assert [source.id for source in sources] == ['mysql:local', 'mysql:archive', 'php_api:studio', 'php_api:visualizer']
    public = [source.public_dict() for source in sources]
    assert public[0]['address'] == 'reader@db.internal:3307/results'
    assert public[2]['address'] == 'https://studio.example'
    assert all('password' not in item and 'publish_key' not in item for item in public)
