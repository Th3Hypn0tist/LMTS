from __future__ import annotations

from typing import Any

from .projector import REPORT_FORMAT, REPORT_VERSION


def validate_publishable_report(report: dict[str, Any]) -> str:
    report_meta = report.get('report')
    if (
        report.get('format') != REPORT_FORMAT
        or report.get('version') != REPORT_VERSION
        or not isinstance(report_meta, dict)
    ):
        raise ValueError(f'payload is not an LMTS Benchmark Report {REPORT_VERSION} document')

    report_id = str(report_meta.get('id') or '').strip()
    if not report_id:
        raise ValueError('LMTS report is missing report.id')

    records = report.get('records')
    if not isinstance(records, list):
        raise ValueError('LMTS report records must be an array')
    if not records:
        raise ValueError('LMTS report has no publishable PASS/FAIL evidence')

    for record in records:
        if not isinstance(record, dict):
            raise ValueError('LMTS report contains an invalid record')
        outcome = record.get('outcome')
        result = str(outcome.get('result') or '').strip() if isinstance(outcome, dict) else ''
        if result not in {'pass', 'fail'}:
            raise ValueError(
                f'LMTS report contains non-publishable outcome: {result or "missing"}'
            )

    return report_id
