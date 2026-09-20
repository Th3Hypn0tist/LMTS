from __future__ import annotations

import json
from typing import Any


DATASET_FORMAT = 'lmts.dvs.report-telemetry-percent'
DATASET_VERSION = '1.0'
DATASET_SOURCE_FORMAT = f'{DATASET_FORMAT}/{DATASET_VERSION}'


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _summary_rows(summary: object) -> tuple[tuple[str, float], ...]:
    if not isinstance(summary, dict):
        return ()
    result: list[tuple[str, float]] = []
    for aggregation in ('minimum', 'mean', 'maximum'):
        value = _number(summary.get(aggregation))
        if value is not None:
            result.append((aggregation, value))
    return tuple(result)


def _row(
    *,
    source_id: str,
    report_id: str,
    record_id: str,
    target: str,
    test: str,
    result: str,
    resource: str,
    metric: str,
    aggregation: str,
    value: float,
) -> dict[str, object]:
    run_key = f'{report_id}/{record_id}'
    metric_key = f'{resource}/{metric}/{aggregation}'
    return {
        'report_source_id': source_id,
        'report_id': report_id,
        'record_id': record_id,
        'run_key': run_key,
        'target': target,
        'test': test,
        'result': result,
        'resource': resource,
        'metric': metric,
        'aggregation': aggregation,
        'metric_key': metric_key,
        'value': value,
        'unit': 'percent',
    }


def project_percent_telemetry_dataset(
    reports: list[tuple[str, str, dict[str, Any]]],
) -> dict[str, object]:
    """Project multiple immutable LMTS reports into one percent-only DVS dataset.

    Telemetry aggregation is never invented here. Runtime telemetry rows are emitted
    only from the explicit minimum/mean/maximum summaries already stored in report
    evidence. Score percent is a record-level metric.
    """
    if not reports:
        raise ValueError('percent telemetry dataset requires at least one report')

    seen_reports: dict[str, str] = {}
    rows: list[dict[str, object]] = []
    source_record_count = 0

    for source_id, requested_report_id, report in reports:
        if report.get('format') != 'lmts.report' or report.get('version') != '1.1':
            raise ValueError(f'unsupported report contract for DVS dataset: {requested_report_id}')
        report_meta = report.get('report') if isinstance(report.get('report'), dict) else {}
        report_id = str(report_meta.get('id') or '').strip()
        if not report_id:
            raise ValueError('LMTS report dataset source is missing report.id')
        if report_id != requested_report_id:
            raise ValueError(
                f'report source returned id {report_id!r} for requested report {requested_report_id!r}'
            )

        canonical = _canonical_json(report)
        previous = seen_reports.get(report_id)
        if previous is not None:
            if previous != canonical:
                raise ValueError(f'conflicting immutable report content for id {report_id}')
            continue
        seen_reports[report_id] = canonical

        records = report.get('records')
        if not isinstance(records, list):
            raise ValueError(f'LMTS report {report_id} records must be an array')

        for record in records:
            if not isinstance(record, dict):
                raise ValueError(f'LMTS report {report_id} contains a non-object record')
            record_id = str(record.get('id') or '').strip()
            if not record_id:
                raise ValueError(f'LMTS report {report_id} contains a record without id')
            source_record_count += 1

            coordinates = record.get('coordinates') if isinstance(record.get('coordinates'), dict) else {}
            target = str(coordinates.get('target') or '').strip() or 'unknown-target'
            test = str(coordinates.get('test') or '').strip() or 'unknown-test'
            outcome = record.get('outcome') if isinstance(record.get('outcome'), dict) else {}
            result = str(outcome.get('result') or '').strip() or 'unknown'

            metrics = record.get('metrics') if isinstance(record.get('metrics'), dict) else {}
            score_metric = metrics.get('score_percent')
            score = _number(score_metric.get('value')) if isinstance(score_metric, dict) else None
            if score is not None:
                rows.append(_row(
                    source_id=source_id,
                    report_id=report_id,
                    record_id=record_id,
                    target=target,
                    test=test,
                    result=result,
                    resource='result',
                    metric='score_percent',
                    aggregation='record',
                    value=score,
                ))

            evidence = record.get('evidence') if isinstance(record.get('evidence'), dict) else {}
            telemetry = evidence.get('telemetry') if isinstance(evidence.get('telemetry'), dict) else {}
            summary = telemetry.get('summary') if isinstance(telemetry.get('summary'), dict) else {}

            for aggregation, value in _summary_rows(summary.get('cpu_util_percent')):
                rows.append(_row(
                    source_id=source_id,
                    report_id=report_id,
                    record_id=record_id,
                    target=target,
                    test=test,
                    result=result,
                    resource='system',
                    metric='cpu_util_percent',
                    aggregation=aggregation,
                    value=value,
                ))

            gpus = summary.get('gpus') if isinstance(summary.get('gpus'), dict) else {}
            for gpu_key, gpu_summary in sorted(gpus.items(), key=lambda item: str(item[0])):
                if not isinstance(gpu_summary, dict):
                    continue
                resource = f'gpu:{gpu_key}'
                for raw_metric, metric in (
                    ('gpu_util_percent', 'gpu_util_percent'),
                    ('memory_util_percent', 'gpu_memory_util_percent'),
                ):
                    for aggregation, value in _summary_rows(gpu_summary.get(raw_metric)):
                        rows.append(_row(
                            source_id=source_id,
                            report_id=report_id,
                            record_id=record_id,
                            target=target,
                            test=test,
                            result=result,
                            resource=resource,
                            metric=metric,
                            aggregation=aggregation,
                            value=value,
                        ))

    return {
        'format': DATASET_FORMAT,
        'version': DATASET_VERSION,
        'metric_family': 'percent',
        'report_count': len(seen_reports),
        'record_count': source_record_count,
        'row_count': len(rows),
        'records': rows,
    }
