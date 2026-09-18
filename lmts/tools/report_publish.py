from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from lmts.core.settings import MySQLSettings, load_settings
from lmts.reporting import REPORT_FORMAT, REPORT_VERSION

from .mysql_reports import write_report
from .report_profiles import ReportProfile


def _read_json_response(request: Request, *, timeout: float) -> tuple[int, dict[str, Any]]:
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, 'status', response.getcode()))
            raw = response.read().decode('utf-8')
    except HTTPError as exc:
        raw = exc.read().decode('utf-8', errors='replace')
        try:
            payload = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            payload = {}
        detail = payload.get('error') if isinstance(payload, dict) else None
        message = str(detail or raw.strip() or exc.reason or f'HTTP {exc.code}')
        raise RuntimeError(f'LMTS report server HTTP {exc.code}: {message}') from exc
    except URLError as exc:
        raise RuntimeError(f'LMTS report server connection failed: {exc.reason}') from exc

    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'LMTS report server returned invalid JSON (HTTP {status})') from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f'LMTS report server returned non-object JSON (HTTP {status})')
    return status, payload


def _report_lookup_url(endpoint: str, report_id: str) -> str:
    parts = urlsplit(endpoint)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query['id'] = report_id
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _validate_report_document(report: dict[str, Any]) -> str:
    report_meta = report.get('report')
    if report.get('format') != REPORT_FORMAT or report.get('version') != REPORT_VERSION or not isinstance(report_meta, dict):
        raise ValueError(f'payload is not an LMTS Benchmark Report {REPORT_VERSION} document')
    report_id = str(report_meta.get('id') or '').strip()
    if not report_id:
        raise ValueError('LMTS report is missing report.id')
    return report_id


def publish_report(
    report: dict[str, Any],
    profile: ReportProfile,
    *,
    timeout: float = 20.0,
    verify: bool = True,
    mysql: MySQLSettings | None = None,
) -> str:
    report_id = _validate_report_document(report)

    if profile.kind == 'mysql':
        returned_id = write_report(mysql or load_settings().mysql, report, verify=verify)
        if returned_id != report_id:
            raise RuntimeError(f'MySQL report target returned unexpected id: {returned_id!r}')
        return returned_id
    if profile.kind != 'php_api':
        raise ValueError(f'unsupported report target kind: {profile.kind}')

    body = json.dumps(report, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    request = Request(
        profile.endpoint,
        data=body,
        method='POST',
        headers={
            'Content-Type': 'application/json; charset=utf-8',
            'Accept': 'application/json',
            'X-LMTS-Key': profile.publish_key,
        },
    )
    status, payload = _read_json_response(request, timeout=timeout)
    if status not in {200, 201}:
        raise RuntimeError(f'LMTS report server returned unexpected HTTP status: {status}')
    if payload.get('ok') is not True:
        raise RuntimeError(f'LMTS report server rejected report: {payload!r}')
    returned_id = str(payload.get('id') or '')
    if returned_id != report_id:
        raise RuntimeError(f'LMTS report server returned unexpected id: {returned_id!r}')

    if verify:
        verify_request = Request(
            _report_lookup_url(profile.endpoint, report_id),
            method='GET',
            headers={'Accept': 'application/json'},
        )
        _, stored = _read_json_response(verify_request, timeout=timeout)
        stored_id = _validate_report_document(stored)
        if stored_id != report_id:
            raise RuntimeError(
                f'LMTS report server verification returned unexpected id: {stored_id!r}'
            )

    return returned_id
