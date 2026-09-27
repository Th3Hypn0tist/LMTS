from __future__ import annotations

from typing import Any

from .projector import REPORT_FORMAT, REPORT_VERSION


_VARIANCE_SAMPLE_KEYS = frozenset({'outcome', 'observed_at'})


def _validate_variance_samples(record: dict[str, Any]) -> None:
    evidence = record.get('evidence')
    if not isinstance(evidence, dict) or 'variance_samples' not in evidence:
        return
    samples = evidence['variance_samples']
    if not isinstance(samples, list):
        raise ValueError('LMTS variance_samples evidence must be an array')
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            raise ValueError(f'LMTS variance sample {index} must be an object')
        extras = sorted(set(sample) - _VARIANCE_SAMPLE_KEYS)
        if extras:
            raise ValueError(
                f'LMTS variance sample {index} contains non-lightweight field(s): '
                + ', '.join(extras)
            )
        outcome = str(sample.get('outcome') or '').strip()
        if outcome not in {'pass', 'fail'}:
            raise ValueError(
                f'LMTS variance sample {index} outcome must be pass or fail'
            )
        observed_at = sample.get('observed_at')
        if observed_at is not None and (
            not isinstance(observed_at, str) or not observed_at.strip()
        ):
            raise ValueError(
                f'LMTS variance sample {index} observed_at must be a timestamp string or null'
            )


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
        if 'passed' in outcome:
            passed = outcome.get('passed')
            if not isinstance(passed, bool):
                raise ValueError('LMTS report outcome.passed must be boolean when present')
            if passed is not (result == 'pass'):
                raise ValueError('LMTS report outcome.result and outcome.passed disagree')
        _validate_variance_samples(record)

    return report_id
