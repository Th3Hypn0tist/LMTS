from __future__ import annotations

import re
from typing import Any


REPORT_FORMAT = 'lmts.report'
REPORT_VERSION = '1.0'

_TEST_REF_RE = re.compile(r'^(?P<namespace>[A-Za-z0-9_.-]+)@(?P<version>[^#]+)#(?P<instance>.+)$')

_METRIC_UNITS: dict[str, tuple[str, str | None]] = {
    'input_tokens': ('input_tokens', 'tokens'),
    'output_tokens': ('output_tokens', 'tokens'),
    'ttft_ms': ('ttft', 'ms'),
    'total_ms': ('total_time', 'ms'),
    'workspace_protocol_steps': ('workspace_protocol_steps', 'steps'),
    'output_file_count': ('output_file_count', 'files'),
    'exact_output_match': ('exact_output_match', None),
}


def _test_entity(test_ref: str) -> dict[str, Any]:
    match = _TEST_REF_RE.fullmatch(test_ref)
    if match is None:
        raise ValueError(f'invalid canonical test_ref: {test_ref!r}')
    instance = match.group('instance')
    return {
        'label': instance.replace('-', ' ').replace('_', ' ').strip().capitalize(),
        'properties': {
            'namespace': match.group('namespace'),
            'version': match.group('version'),
            'instance': instance,
        },
    }


def _model_entity(run: dict[str, Any]) -> dict[str, Any]:
    metadata = run.get('model_metadata')
    if not isinstance(metadata, dict):
        raise ValueError(f"run {run.get('run_id')!r} has no model_metadata object")
    details = metadata.get('details')
    if not isinstance(details, dict):
        raise ValueError(f"run {run.get('run_id')!r} has no model_metadata.details object")
    properties = {
        'provider': run['provider_ref'],
        'digest': metadata.get('digest'),
        'size_bytes': metadata.get('size'),
        'family': details.get('family'),
        'parameter_size': details.get('parameter_size'),
        'quantization': details.get('quantization_level'),
        'context_length': details.get('context_length'),
        'embedding_length': details.get('embedding_length'),
    }
    return {
        'label': run['model_ref'],
        'properties': {key: value for key, value in properties.items() if value is not None},
    }


def _outcome(run: dict[str, Any]) -> dict[str, str]:
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
    return {'status': status, 'result': result}


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

    model_entities: dict[str, Any] = {}
    test_entities: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    outcomes = {'pass': 0, 'fail': 0, 'error': 0, 'cancelled': 0, 'unknown': 0}

    for run in runs:
        if not isinstance(run, dict):
            raise ValueError('every bundle.runs item must be an object')
        for key in ('run_id', 'model_id', 'model_ref', 'provider_ref', 'test_ref', 'status', 'passed', 'metrics'):
            if key not in run:
                raise ValueError(f"run {run.get('run_id')!r} missing required field: {key}")
        run_id = str(run['run_id'])
        model_id = str(run['model_id'])
        test_ref = str(run['test_ref'])
        if model_id not in model_entities:
            model_entities[model_id] = _model_entity(run)
        if test_ref not in test_entities:
            test_entities[test_ref] = _test_entity(test_ref)

        raw_metrics = run['metrics']
        if not isinstance(raw_metrics, dict):
            raise ValueError(f'run {run_id!r} metrics must be an object')
        metrics: dict[str, Any] = {}
        for name, value in raw_metrics.items():
            projected_name, unit = _METRIC_UNITS.get(str(name), (str(name), None))
            metric: dict[str, Any] = {'value': value}
            if unit is not None:
                metric['unit'] = unit
            metrics[projected_name] = metric

        outcome = _outcome(run)
        outcomes[outcome['result']] += 1
        record: dict[str, Any] = {
            'id': run_id,
            'coordinates': {'model': model_id, 'test': test_ref},
            'outcome': outcome,
            'metrics': metrics,
        }
        raw_error = run.get('error')
        if raw_error is not None:
            if not isinstance(raw_error, dict):
                raise ValueError(f'run {run_id!r} error must be an object or null')
            record['error'] = {
                'type': str(raw_error.get('type') or 'Error'),
                'message': str(raw_error.get('message') or ''),
            }
        records.append(record)

    created_at = matrix.get('completed_at') or matrix.get('started_at')
    if not isinstance(created_at, str) or not created_at:
        raise ValueError('matrix must contain completed_at or started_at')

    return {
        'format': REPORT_FORMAT,
        'version': REPORT_VERSION,
        'report': {
            'id': matrix_id,
            'type': 'test_matrix',
            'title': 'LMTS Test Matrix',
            'created_at': created_at,
        },
        'source': {
            'type': 'lmts.matrix_bundle',
            'id': matrix_id,
            'schema_version': bundle.get('schema_version', 1),
            'exported_at': bundle.get('exported_at', created_at),
        },
        'dimensions': {
            'model': {'label': 'Model', 'entity_type': 'model'},
            'test': {'label': 'Test', 'entity_type': 'test'},
        },
        'entities': {'model': model_entities, 'test': test_entities},
        'records': records,
        'summary': {'records': len(records), 'outcomes': outcomes},
        'views': [{
            'id': 'results',
            'type': 'matrix',
            'title': 'Results',
            'row_dimension': 'model',
            'column_dimension': 'test',
            'value': 'outcome.result',
        }],
        'extensions': {},
    }
