from __future__ import annotations
from pathlib import Path
from lmts.core.settings import LMTSSettings, MySQLSettings, save_settings
from lmts.dvs.database_sources import CORE_DATABASE_SOURCE_ID, load_all_dvs_database_sources

def test_legacy_database_source_adapter_uses_first_lmts_mysql_connection(tmp_path: Path) -> None:
    settings_path = tmp_path / 'settings.json'
    sources_path = tmp_path / 'dvs-databases.json'
    save_settings(
        LMTSSettings(
            mysql_connections=(
                MySQLSettings(
                    id='primary',
                    label='Primary',
                    host='db.internal',
                    port=3307,
                    database='results',
                    username='reader',
                    password='secret',
                    publish_key='publish',
                ),
            ),
        ),
        settings_path,
    )
    sources = load_all_dvs_database_sources(sources_path, settings_path)
    assert sources[0].id == CORE_DATABASE_SOURCE_ID
    assert sources[0].host == 'db.internal'
    assert sources[0].database == 'results'
    assert sources[0].username == 'reader'
