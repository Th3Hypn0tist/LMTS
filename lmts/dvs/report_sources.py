from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from lmts.core.settings import DEFAULT_SETTINGS_PATH, MySQLSettings, PHPAPISettings, load_settings
from lmts.tools.mysql_reports import list_reports, read_report

from .database_sources import (
    DEFAULT_DVS_DATABASE_SOURCES_PATH,
    DVSDatabaseSource,
    list_database_reports,
    load_database_report,
    load_dvs_database_sources,
)


@dataclass(frozen=True, slots=True)
class DVSReportSource:
    id: str
    label: str
    transport: str
    mysql: MySQLSettings | None = None
    php_api: PHPAPISettings | None = None
    legacy_database: DVSDatabaseSource | None = None

    def public_dict(self) -> dict[str, object]:
        if self.mysql is not None:
            return {
                'id': self.id,
                'label': self.label,
                'transport': 'mysql',
                'address': f'{self.mysql.username}@{self.mysql.host}:3306/{self.mysql.database}',
            }
        if self.php_api is not None:
            return {
                'id': self.id,
                'label': self.label,
                'transport': 'php_api',
                'address': self.php_api.base_url,
            }
        assert self.legacy_database is not None
        legacy = self.legacy_database
        return {
            'id': self.id,
            'label': self.label,
            'transport': 'mysql',
            'address': f'{legacy.username}@{legacy.host}:{legacy.port}/{legacy.database}',
        }


def load_all_dvs_report_sources(
    sources_path=DEFAULT_DVS_DATABASE_SOURCES_PATH,
    settings_path=DEFAULT_SETTINGS_PATH,
) -> tuple[DVSReportSource, ...]:
    settings = load_settings(settings_path)
    items = [
        DVSReportSource(
            id='dvstudio.mysql',
            label='DVStudio / MySQL',
            transport='mysql',
            mysql=settings.mysql,
        ),
    ]
    if settings.dvstudio_php_api.configured:
        items.append(DVSReportSource(
            id='dvstudio.php_api',
            label='DVStudio / PHP API',
            transport='php_api',
            php_api=settings.dvstudio_php_api,
        ))
    if settings.dvisualizer_php_api.configured:
        items.append(DVSReportSource(
            id='dvisualizer.php_api',
            label='DVisualizer / PHP API',
            transport='php_api',
            php_api=settings.dvisualizer_php_api,
        ))
    reserved = {item.id for item in items}
    for source in load_dvs_database_sources(sources_path):
        if source.id in reserved:
            raise ValueError(f'DVS report source id is reserved: {source.id}')
        items.append(DVSReportSource(
            id=source.id,
            label=source.label,
            transport='mysql',
            legacy_database=source,
        ))
    return tuple(items)


def _source(source_id: str, sources: tuple[DVSReportSource, ...]) -> DVSReportSource:
    for source in sources:
        if source.id == source_id:
            return source
    raise KeyError(f'unknown DVS report source: {source_id}')


def _get_json(url: str) -> dict[str, Any]:
    request = Request(url, method='GET', headers={'Accept': 'application/json'})
    with urlopen(request, timeout=20.0) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if not isinstance(payload, dict):
        raise ValueError('report source returned non-object JSON')
    return payload


def _php_list(api: PHPAPISettings, *, limit: int) -> list[dict[str, Any]]:
    payload = _get_json(api.reports_endpoint)
    reports = payload.get('reports')
    if not isinstance(reports, list):
        raise ValueError('PHP API reports endpoint must return a reports array')
    rows = []
    for item in reports[:limit]:
        if not isinstance(item, dict):
            raise ValueError('PHP API report list contains a non-object item')
        rows.append(dict(item))
    return rows


def list_report_source_reports(
    source_ids: list[str],
    *,
    limit_per_source: int = 100,
    sources_path=DEFAULT_DVS_DATABASE_SOURCES_PATH,
    settings_path=DEFAULT_SETTINGS_PATH,
) -> list[dict[str, Any]]:
    if not source_ids:
        raise ValueError('select at least one DVS report source')
    if len(source_ids) != len(set(source_ids)):
        raise ValueError('DVS report source selection must not contain duplicates')
    if not 1 <= limit_per_source <= 1000:
        raise ValueError('limit_per_source must be within 1..1000')

    sources = load_all_dvs_report_sources(sources_path, settings_path)
    reports: list[dict[str, Any]] = []
    for source_id in source_ids:
        source = _source(source_id, sources)
        if source.mysql is not None:
            rows = [item.to_dict() for item in list_reports(source.mysql, limit=limit_per_source)]
        elif source.php_api is not None:
            rows = _php_list(source.php_api, limit=limit_per_source)
        else:
            assert source.legacy_database is not None
            rows = list_database_reports(
                [source.legacy_database.id],
                limit_per_source=limit_per_source,
                sources_path=sources_path,
            )
        for row in rows:
            item = dict(row)
            item['report_source_id'] = source.id
            item['report_source_label'] = source.label
            reports.append(item)
    reports.sort(key=lambda item: str(item.get('created_at') or ''), reverse=True)
    return reports


def load_report_source_report(
    source_id: str,
    report_id: str,
    *,
    sources_path=DEFAULT_DVS_DATABASE_SOURCES_PATH,
    settings_path=DEFAULT_SETTINGS_PATH,
) -> dict[str, Any]:
    source = _source(source_id, load_all_dvs_report_sources(sources_path, settings_path))
    if source.mysql is not None:
        return read_report(source.mysql, report_id)
    if source.php_api is not None:
        url = source.php_api.report_endpoint + '?' + urlencode({'id': report_id})
        return _get_json(url)
    assert source.legacy_database is not None
    return load_database_report(source.legacy_database.id, report_id, sources_path=sources_path)


def report_source_statuses(
    *,
    sources_path=DEFAULT_DVS_DATABASE_SOURCES_PATH,
    settings_path=DEFAULT_SETTINGS_PATH,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in load_all_dvs_report_sources(sources_path, settings_path):
        item = {
            **source.public_dict(),
            'ok': False,
            'report_count': 0,
            'latest_report_id': None,
            'error': None,
        }
        try:
            rows = list_report_source_reports(
                [source.id],
                limit_per_source=1000,
                sources_path=sources_path,
                settings_path=settings_path,
            )
            item['report_count'] = len(rows)
            if rows:
                item['latest_report_id'] = str(rows[0].get('report_id') or '') or None
            item['ok'] = True
        except Exception as exc:
            item['error'] = str(exc)
        result.append(item)
    return result
