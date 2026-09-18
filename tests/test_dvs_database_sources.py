from __future__ import annotations

import json
from pathlib import Path

import lmts.dvs.database_sources as db
from lmts.core.settings import LMTSSettings, MySQLSettings, save_settings
from lmts.dvs.database_sources import (
    CORE_DATABASE_SOURCE_ID,
    DVSDatabaseSource,
    list_database_reports,
    load_all_dvs_database_sources,
    load_database_report,
    load_dvs_database_sources,
    save_dvs_database_sources,
)


def _source(source_id: str) -> DVSDatabaseSource:
    return DVSDatabaseSource(
        id=source_id,
        label=source_id.upper(),
        host='127.0.0.1',
        port=3306,
        database='lmts',
        username='lmts',
        password='secret',
    )


def test_dvs_database_sources_round_trip_and_permissions(tmp_path: Path) -> None:
    path = tmp_path / 'dvs-databases.json'
    save_dvs_database_sources((_source('b'), _source('a')), path)
    loaded = load_dvs_database_sources(path)
    assert [item.id for item in loaded] == ['a', 'b']
    assert loaded[0].password == 'secret'
    assert path.stat().st_mode & 0o777 == 0o600


def test_public_source_metadata_never_contains_password() -> None:
    public = _source('a').public_dict()
    assert public['id'] == 'a'
    assert 'password' not in public


def test_multi_source_report_listing_preserves_database_identity(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / 'dvs-databases.json'
    save_dvs_database_sources((_source('a'), _source('b')), path)

    def fake_query(source, sql):
        assert 'ORDER BY created_at DESC' in sql
        created = '2026-09-18T08:00:00.000000' if source.id == 'b' else '2026-09-18T07:00:00.000000'
        return [json.dumps({
            'report_id': f'report-{source.id}',
            'report_type': 'benchmark',
            'created_at': created,
            'source_type': 'model',
            'source_id': f'model-{source.id}',
        })]

    monkeypatch.setattr(db, '_query', fake_query)
    reports = list_database_reports(['a', 'b'], limit_per_source=10, sources_path=path)

    assert [item['report_id'] for item in reports] == ['report-b', 'report-a']
    assert reports[0]['database_source_id'] == 'b'
    assert reports[1]['database_source_id'] == 'a'


def test_database_report_load_uses_exact_source_and_decodes_json(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / 'dvs-databases.json'
    save_dvs_database_sources((_source('a'), _source('b')), path)
    report = {'format': 'lmts.report', 'version': '1.1', 'report': {'id': 'r-1'}}

    import base64
    encoded = base64.b64encode(json.dumps(report).encode('utf-8')).decode('ascii')
    seen = []

    def fake_query(source, sql):
        seen.append((source.id, sql))
        return [encoded]

    monkeypatch.setattr(db, '_query', fake_query)
    loaded = load_database_report('b', "r'1", sources_path=path)

    assert loaded == report
    assert seen[0][0] == 'b'
    assert '0x' in seen[0][1]
    assert "r'1" not in seen[0][1]


def test_all_sources_include_lmts_core_and_extra_sources(tmp_path: Path) -> None:
    settings_path = tmp_path / 'settings.json'
    sources_path = tmp_path / 'dvs-databases.json'
    save_settings(
        LMTSSettings(
            mysql=MySQLSettings(
                host='db.internal',
                database='results',
                username='reader',
                password='secret',
                publish_key='publish',
            ),
        ),
        settings_path,
    )
    save_dvs_database_sources((_source('archive'),), sources_path)

    sources = load_all_dvs_database_sources(sources_path, settings_path)
    assert [item.id for item in sources] == [CORE_DATABASE_SOURCE_ID, 'archive']
    assert sources[0].label == 'LMTS core'
    assert sources[0].host == 'db.internal'
    assert sources[0].database == 'results'
    assert sources[0].username == 'reader'


def test_reserved_lmts_core_source_id_cannot_be_persisted(tmp_path: Path) -> None:
    source = _source(CORE_DATABASE_SOURCE_ID)
    try:
        save_dvs_database_sources((source,), tmp_path / 'dvs-databases.json')
    except ValueError as exc:
        assert 'reserved' in str(exc)
    else:
        raise AssertionError('reserved LMTS core source id must be rejected')
