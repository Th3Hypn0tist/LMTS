from pathlib import Path

from lmts.core.settings import LMTSSettings, MySQLSettings, PHPAPISettings, save_settings
from lmts.dvs.report_sources import load_all_dvs_report_sources


def test_dvs_report_sources_use_settings_owned_destinations(tmp_path: Path) -> None:
    settings_path = tmp_path / 'settings.json'
    sources_path = tmp_path / 'dvs-databases.json'
    save_settings(
        LMTSSettings(
            mysql=MySQLSettings(
                host='db.internal',
                database='results',
                username='reader',
                password='secret',
                publish_key='legacy',
            ),
            dvstudio_php_api=PHPAPISettings(
                base_url='https://studio.example',
                publish_key='studio-key',
            ),
            dvisualizer_php_api=PHPAPISettings(
                base_url='https://visualizer.example',
                publish_key='visualizer-key',
            ),
        ),
        settings_path,
    )
    sources = load_all_dvs_report_sources(sources_path, settings_path)
    assert [source.id for source in sources] == [
        'dvstudio.mysql',
        'dvstudio.php_api',
        'dvisualizer.php_api',
    ]
    public = [source.public_dict() for source in sources]
    assert public[0]['address'] == 'reader@db.internal:3306/results'
    assert public[1]['address'] == 'https://studio.example'
    assert public[2]['address'] == 'https://visualizer.example'
    assert all('password' not in item and 'publish_key' not in item for item in public)
