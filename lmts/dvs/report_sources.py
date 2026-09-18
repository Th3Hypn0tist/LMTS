from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from lmts.core.settings import DEFAULT_SETTINGS_PATH, MySQLSettings, PHPAPISettings, load_settings
from lmts.tools.mysql_reports import list_reports, read_report


@dataclass(frozen=True, slots=True)
class DVSReportSource:
    id: str
    label: str
    transport: str
    mysql: MySQLSettings | None = None
    php_api: PHPAPISettings | None = None

    def public_dict(self) -> dict[str, object]:
        if self.mysql is not None:
            return {
                'id': self.id,
                'label': self.label,
                'transport': 'mysql',
                'address': f'{self.mysql.username}@{self.mysql.host}:{self.mysql.port}/{self.mysql.database}',
            }
        assert self.php_api is not None
        return {
            'id': self.id,
            'label': self.label,
            'transport': 'php_api',
            'address': self.php_api.base_url,
        }


def load_all_dvs_report_sources(settings_path=DEFAULT_SETTINGS_PATH) -> tuple[DVSReportSource, ...]:
    settings = load_settings(settings_path)
    items: list[DVSReportSource] = []
    for mysql in settings.mysql_connections:
        items.append(DVSReportSource(
            id=f'mysql:{mysql.id}',
            label=f'MySQL  {mysql.label}',
            transport='mysql',
            mysql=mysql,
        ))
    for api in settings.php_api_connections:
        items.append(DVSReportSource(
            id=f'php_api:{api.id}',
            label=f'PHP API  {api.label}',
            transport='php_api',
            php_api=api,
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
    settings_path=DEFAULT_SETTINGS_PATH,
) -> list[dict[str, Any]]:
    if not source_ids:
        raise ValueError('select at least one DVS report source')
    if len(source_ids) != len(set(source_ids)):
        raise ValueError('DVS report source selection must not contain duplicates')
    if not 1 <= limit_per_source <= 1000:
        raise ValueError('limit_per_source must be within 1..1000')

    sources = load_all_dvs_report_sources(settings_path)
    reports: list[dict[str, Any]] = []
    for source_id in source_ids:
        source = _source(source_id, sources)
        if source.mysql is not None:
            rows = [item.to_dict() for item in list_reports(source.mysql, limit=limit_per_source)]
        else:
            assert source.php_api is not None
            rows = _php_list(source.php_api, limit=limit_per_source)
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
    settings_path=DEFAULT_SETTINGS_PATH,
) -> dict[str, Any]:
    source = _source(source_id, load_all_dvs_report_sources(settings_path))
    if source.mysql is not None:
        return read_report(source.mysql, report_id)
    assert source.php_api is not None
    return _get_json(source.php_api.report_endpoint + '?' + urlencode({'id': report_id}))


def report_source_statuses(*, settings_path=DEFAULT_SETTINGS_PATH) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in load_all_dvs_report_sources(settings_path):
        item = {
            **source.public_dict(),
            'ok': False,
            'report_count': 0,
            'latest_report_id': None,
            'error': None,
        }
        try:
            rows = list_report_source_reports([source.id], limit_per_source=1000, settings_path=settings_path)
            item['report_count'] = len(rows)
            if rows:
                item['latest_report_id'] = str(rows[0].get('report_id') or '') or None
            item['ok'] = True
        except Exception as exc:
            item['error'] = str(exc)
        result.append(item)
    return result
