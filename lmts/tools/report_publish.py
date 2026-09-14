from __future__ import annotations

import json
from typing import Any
from urllib.request import Request, urlopen

from lmts.reporting import REPORT_FORMAT, REPORT_VERSION

from .report_profiles import ReportProfile


def publish_report(report: dict[str, Any], profile: ReportProfile, *, timeout: float = 20.0) -> str:
    report_meta = report.get('report')
    if report.get('format') != REPORT_FORMAT or report.get('version') != REPORT_VERSION or not isinstance(report_meta, dict):
        raise ValueError(f'payload is not an LMTS Benchmark Report {REPORT_VERSION} document')
    report_id = str(report_meta.get('id') or '').strip()
    if not report_id:
        raise ValueError('LMTS report is missing report.id')

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
    with urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode('utf-8'))
    if not isinstance(payload, dict) or payload.get('ok') is not True:
        raise RuntimeError(f'LMTS report server rejected report: {payload!r}')
    returned_id = str(payload.get('id') or '')
    if returned_id != report_id:
        raise RuntimeError(f'LMTS report server returned unexpected id: {returned_id!r}')
    return returned_id
