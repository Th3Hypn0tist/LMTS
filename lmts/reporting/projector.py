from __future__ import annotations

import json
from typing import Any

from lmts.tests.identity import parse_test_ref


REPORT_FORMAT = 'lmts.report'
REPORT_VERSION = '1.1'

_METRIC_UNITS: dict[str, tuple[str, str | None]] = {
    'input_tokens': ('input_tokens', 'tokens'),
    'output_tokens': ('output_tokens', 'tokens'),
    'ttft_ms': ('ttft', 'ms'),
    'total_ms': ('total_time', 'ms'),
    'workspace_protocol_steps': ('workspace_protocol_steps', 'steps'),
    'output_file_count': ('output_file_count', 'files'),
    'exact_output_match': ('exact_output_match', None),
}

_STANDARD_REPORT_METRICS: dict[str, str | None] = {
    projected_name: unit for projected_name, unit in _METRIC_UNITS.values()
}
_STANDARD_REPORT_METRICS['score_percent'] = 'percent'


def _human_label(value: str) -> str:
    return value.replace('_', ' ').replace('-', ' ').strip().capitalize()


def _test_entity(test_ref: str, run: dict[str, Any]) -> dict[str, Any]:
    identity = parse_test_ref(test_ref)
    metadata = run.get('execution_metadata') if isinstance(run.get('execution_metadata'), dict) else {}
    snapshot = metadata.get('test') if isinstance(metadata.get('test'), dict) else {}
    configuration = snapshot.get('configuration') if isinstance(snapshot.get('configuration'), dict) else {}
    label_source = identity.instance_id or identity.type_id.rsplit('.', 1)[-1]
    properties: dict[str, Any] = {
        'namespace': identity.type_id,
        'version': identity.version,
        'instance': identity.instance_id,
        'minimum_level': snapshot.get('minimum_level'),
        'mandatory': snapshot.get('mandatory'),
        'configuration': configuration,
    }
    return {
        'label': _human_label(label_source),
        'properties': {key: value for key, value in properties.items() if value is not None},
    }


def _target_entity(run: dict[str, Any]) -> dict[str, Any]:
    target_id = str(run.get('executor_id') or '').strip()
    target_kind = str(run.get('executor_kind') or '').strip()
    if not target_id or not target_kind:
        raise ValueError(f"run {run.get('run_id')!r} has no executor identity")
    subject = run.get('evaluation_subject') if isinstance(run.get('evaluation_subject'), dict) else {}
    metadata = run.get('execution_metadata') if isinstance(run.get('execution_metadata'), dict) else {}
    properties: dict[str, Any] = {
        'kind': target_kind,
        'subject_fingerprint': subject.get('fingerprint'),
        'runtime_configuration_fingerprint': metadata.get('runtime_configuration_fingerprint'),
        'capabilities': metadata.get('capabilities'),
    }
    if target_kind == 'model':
        model_metadata = run.get('model_metadata') if isinstance(run.get('model_metadata'), dict) else {}
        details = model_metadata.get('details') if isinstance(model_metadata.get('details'), dict) else {}
        properties.update({
            'provider': run.get('provider_ref'),
            'model_id': run.get('model_id'),
            'model_ref': run.get('model_ref'),
            'digest': model_metadata.get('digest'),
            'size_bytes': model_metadata.get('size'),
            'family': details.get('family'),
            'parameter_size': details.get('parameter_size'),
            'quantization': details.get('quantization_level'),
            'context_length': details.get('context_length'),
            'embedding_length': details.get('embedding_length'),
        })
        label = str(run.get('model_ref') or target_id)
    else:
        label = str(subject.get('label') or target_id)
        properties['members'] = subject.get('members') or []
        properties['configuration'] = subject.get('configuration') or {}
    return {
        'label': label,
        'properties': {key: value for key, value in properties.items() if value is not None},
    }


def _outcome(run: dict[str, Any]) -> dict[str, Any]:
    status = str(run.get('status', 'unknown'))
    if status == 'cancelled':
        result = 'cancelled'
    elif run.get('error') is not None:
        result = 'error'
    elif run.get('passed') is True:
        result = 'pass'
    elif run.get('passed') is False:
        result = 'fail'
    else:
        result = 'unknown'
    return {'status': status, 'result': result, 'passed': run.get('passed')}


def _empty_standard_metrics() -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for name, unit in _STANDARD_REPORT_METRICS.items():
        metric: dict[str, Any] = {'value': None}
        if unit is not None:
            metric['unit'] = unit
        metrics[name] = metric
    return metrics


def _standard_metric_definitions() -> dict[str, dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {}
    for name, unit in _STANDARD_REPORT_METRICS.items():
        definition: dict[str, Any] = {
            'label': _human_label(name),
            'value_type': 'number_or_null' if name != 'exact_output_match' else 'boolean_or_null',
        }
        if unit is not None:
            definition['unit'] = unit
        definitions[name] = definition
    return definitions


def _record_evidence(run: dict[str, Any]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    for key in (
        'execution_metadata',
        'artifacts',
        'responses',
        'workspace_trace',
        'system_context',
        'telemetry',
    ):
        if key in run:
            evidence[key] = run[key]
    return evidence


def _system_profiles(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for run in runs:
        context = run.get('system_context')
        if not isinstance(context, dict):
            continue
        canonical = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        if canonical in seen:
            continue
        seen.add(canonical)
        profiles.append(context)
    return profiles


def project_matrix_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    if bundle.get('export_type') != 'lmts.matrix_bundle':
        raise ValueError('source is not an lmts.matrix_bundle export')
    matrix = bundle.get('matrix')
    runs = bundle.get('runs')
    if not isinstance(matrix, dict):
        raise ValueError('bundle.matrix must be an object')
    if not isinstance(runs, list):
        raise ValueError('bundle.runs must be an array')
    matrix_id = str(matrix.get('matrix_id') or '').strip()
    if not matrix_id:
        raise ValueError('bundle.matrix.matrix_id must be a non-empty string')

    target_entities: dict[str, Any] = {}
    test_entities: dict[str, Any] = {}
    metric_definitions = _standard_metric_definitions()
    records: list[dict[str, Any]] = []
    outcomes = {'pass': 0, 'fail': 0, 'error': 0, 'cancelled': 0, 'unknown': 0}

    for run in runs:
        if not isinstance(run, dict):
            raise ValueError('every bundle.runs item must be an object')
        for key in ('run_id', 'executor_id', 'executor_kind', 'test_ref', 'status', 'passed', 'metrics'):
            if key not in run:
                raise ValueError(f"run {run.get('run_id')!r} missing required field: {key}")
        run_id = str(run['run_id'])
        target_id = str(run['executor_id'])
        resolved_test_ref = str(run['test_ref'])
        if target_id not in target_entities:
            target_entities[target_id] = _target_entity(run)
        if resolved_test_ref not in test_entities:
            test_entities[resolved_test_ref] = _test_entity(resolved_test_ref, run)

        raw_metrics = run['metrics']
        if not isinstance(raw_metrics, dict):
            raise ValueError(f'run {run_id!r} metrics must be an object')
        metrics = _empty_standard_metrics()
        for raw_name, value in raw_metrics.items():
            projected_name, unit = _METRIC_UNITS.get(str(raw_name), (str(raw_name), None))
            metric: dict[str, Any] = {'value': value}
            if unit is not None:
                metric['unit'] = unit
            metrics[projected_name] = metric
            if projected_name not in metric_definitions:
                metric_definitions[projected_name] = {
                    'label': _human_label(projected_name),
                    'value_type': type(value).__name__ if value is not None else 'unknown',
                    **({'unit': unit} if unit is not None else {}),
                }

        score = run.get('score')
        if isinstance(score, dict) and isinstance(score.get('percent'), (int, float)):
            metrics['score_percent'] = {'value': float(score['percent']), 'unit': 'percent'}

        outcome = _outcome(run)
        outcomes[str(outcome['result'])] += 1
        record: dict[str, Any] = {
            'id': run_id,
            'coordinates': {'target': target_id, 'test': resolved_test_ref},
            'timing': {
                'started_at': run.get('started_at'),
                'completed_at': run.get('completed_at'),
            },
            'outcome': outcome,
            'score': score,
            'metrics': metrics,
            'evidence': _record_evidence(run),
        }
        raw_error = run.get('error')
        if raw_error is not None:
            if not isinstance(raw_error, dict):
                raise ValueError(f'run {run_id!r} error must be an object or null')
            record['error'] = {
                'type': str(raw_error.get('type') or 'Error'),
                'message': str(raw_error.get('message') or ''),
                **({'traceback': raw_error['traceback']} if raw_error.get('traceback') is not None else {}),
            }
        records.append(record)

    created_at = matrix.get('completed_at') or matrix.get('started_at')
    if not isinstance(created_at, str) or not created_at:
        raise ValueError('matrix must contain completed_at or started_at')

    system_profiles = _system_profiles([run for run in runs if isinstance(run, dict)])

    return {
        'format': REPORT_FORMAT,
        'version': REPORT_VERSION,
        'report': {
            'id': matrix_id,
            'type': 'benchmark',
            'title': 'LMTS Benchmark Report',
            'created_at': created_at,
            'benchmark': {
                'status': matrix.get('status'),
                'started_at': matrix.get('started_at'),
                'completed_at': matrix.get('completed_at'),
                'target_ids': list(matrix.get('target_ids') or []),
                'test_refs': list(matrix.get('test_refs') or []),
            },
        },
        'source': {
            'type': 'lmts.matrix_bundle',
            'id': matrix_id,
            'schema_version': bundle.get('schema_version', 1),
            'exported_at': bundle.get('exported_at', created_at),
        },
        'dimensions': {
            'target': {'label': 'Target', 'entity_type': 'target'},
            'test': {'label': 'Test', 'entity_type': 'test'},
        },
        'entities': {'target': target_entities, 'test': test_entities},
        'metric_definitions': metric_definitions,
        'records': records,
        'summary': {
            'records': len(records),
            'outcomes': outcomes,
            'targets': len(target_entities),
            'tests': len(test_entities),
            'system_profiles': system_profiles,
        },
        'views': [{
            'id': 'results',
            'type': 'matrix',
            'title': 'Results',
            'row_dimension': 'target',
            'column_dimension': 'test',
            'value': 'outcome.result',
        }],
        'extensions': {},
    }
