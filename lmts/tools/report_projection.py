from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from lmts.core.settings import MySQLSettings
from lmts.tests.identity import parse_test_ref

from .mysql_reports import _hex_text, _mysql_datetime, _run


_TELEMETRY_UNITS: dict[str, str | None] = {
    'input_tokens': 'tokens',
    'output_tokens': 'tokens',
    'ttft': 'ms',
    'total_time': 'ms',
    'score_percent': 'percent',
    'workspace_protocol_steps': 'steps',
    'output_file_count': 'files',
    'exact_output_match': None,
    'cpu_util_percent': 'percent',
    'memory_used_bytes': 'bytes',
    'gpu_util_percent': 'percent',
    'gpu_memory_util_percent': 'percent',
    'gpu_memory_used_mib': 'MiB',
    'gpu_temperature_c': 'C',
    'gpu_power_w': 'W',
}


@dataclass(frozen=True, slots=True)
class TestProjection:
    test_definition_id: str
    test_version_id: str
    namespace: str
    version: str
    title: str
    description: str | None
    telemetry_types: tuple[str, ...]
    definition_json: str
    fingerprint: str


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _stable_id(prefix: str, *parts: str, size: int = 40) -> str:
    digest = hashlib.sha256('\0'.join(parts).encode('utf-8')).hexdigest()
    return prefix + digest[:size]


def _nullable_text(value: str | None) -> str:
    return 'NULL' if value is None else _hex_text(value)


def _numeric(value: object) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _sql_number(value: object) -> str:
    number = _numeric(value)
    return 'NULL' if number is None else repr(number)


def _sql_bool(value: object) -> str:
    if value is True:
        return 'TRUE'
    if value is False:
        return 'FALSE'
    return 'NULL'


def _sql_datetime(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        return 'NULL'
    return _hex_text(_mysql_datetime(value))


def _duration_ms(started: object, completed: object) -> float | None:
    if not isinstance(started, str) or not isinstance(completed, str):
        return None
    try:
        start = datetime.fromisoformat(started.replace('Z', '+00:00'))
        end = datetime.fromisoformat(completed.replace('Z', '+00:00'))
    except ValueError:
        return None
    return max(0.0, (end - start).total_seconds() * 1000.0)


def _test_projection(test_ref: str, entity: dict[str, Any]) -> TestProjection | None:
    identity = parse_test_ref(test_ref)
    props = entity.get('properties') if isinstance(entity.get('properties'), dict) else {}
    namespace = str(props.get('namespace') or identity.type_id).strip()
    version = str(props.get('version') or identity.version).strip()
    title = str(props.get('title') or entity.get('label') or namespace).strip()
    description_raw = props.get('description')
    description = None if description_raw is None else str(description_raw)
    raw_telemetry = props.get('telemetry_types')
    if not isinstance(raw_telemetry, list):
        return None
    telemetry_types = tuple(
        str(item).strip()
        for item in raw_telemetry
        if isinstance(item, str) and item.strip()
    )
    definition = {
        'namespace': namespace,
        'version': version,
        'title': title,
        'description': description,
        'minimum_level': props.get('minimum_level'),
        'mandatory': props.get('mandatory'),
        'taxonomy': props.get('taxonomy'),
        'telemetry_types': list(telemetry_types),
    }
    definition_json = _canonical_json(definition)
    fingerprint = hashlib.sha256(definition_json.encode('utf-8')).hexdigest()
    definition_id = _stable_id('testdef_', namespace)
    version_id = _stable_id('testver_', namespace, version, fingerprint)
    return TestProjection(
        test_definition_id=definition_id,
        test_version_id=version_id,
        namespace=namespace,
        version=version,
        title=title,
        description=description,
        telemetry_types=telemetry_types,
        definition_json=definition_json,
        fingerprint=fingerprint,
    )


def _metric_value(record: dict[str, Any], name: str) -> object:
    metrics = record.get('metrics') if isinstance(record.get('metrics'), dict) else {}
    metric = metrics.get(name)
    return metric.get('value') if isinstance(metric, dict) else None


def _context_json(source: str, **values: object) -> str:
    return _canonical_json({'source': source, **values})


def _telemetry_insert(
    *,
    report_id: str,
    record_id: str,
    user_id: str,
    system_id: str,
    compute_profile_id: str | None,
    test: TestProjection,
    telemetry_type_id: str,
    sample_ordinal: int,
    value: object,
    observed_at: str | None = None,
    context: str,
) -> str | None:
    if telemetry_type_id not in test.telemetry_types or value is None:
        return None
    value_number = 'NULL'
    value_text = 'NULL'
    value_boolean = 'NULL'
    value_json = 'NULL'
    if isinstance(value, bool):
        value_boolean = 'TRUE' if value else 'FALSE'
    elif isinstance(value, (int, float)):
        value_number = repr(value)
    elif isinstance(value, str):
        value_text = _hex_text(value)
    else:
        value_json = _hex_text(_canonical_json(value))
    unit = _TELEMETRY_UNITS.get(telemetry_type_id)
    return f"""
INSERT INTO LMTS_telemetry_values (
  report_id, record_id, user_id, system_id, compute_profile_id,
  test_definition_id, test_version_id, telemetry_type_id,
  sample_ordinal, observed_at,
  value_number, value_text, value_boolean, value_json,
  unit_snapshot, context_json
)
SELECT
  {_hex_text(report_id)},
  {_hex_text(record_id)},
  {_hex_text(user_id)},
  {_hex_text(system_id)},
  {_nullable_text(compute_profile_id)},
  {_hex_text(test.test_definition_id)},
  {_hex_text(test.test_version_id)},
  {_hex_text(telemetry_type_id)},
  {int(sample_ordinal)},
  {_sql_datetime(observed_at)},
  {value_number},
  {value_text},
  {value_boolean},
  {value_json},
  {_nullable_text(unit)},
  {_hex_text(context)}
WHERE NOT EXISTS (
  SELECT 1
  FROM LMTS_telemetry_values
  WHERE report_id = {_hex_text(report_id)}
    AND record_id = {_hex_text(record_id)}
    AND telemetry_type_id = {_hex_text(telemetry_type_id)}
    AND sample_ordinal = {int(sample_ordinal)}
    AND context_json = {_hex_text(context)}
)
""".strip()


def _record_telemetry(
    report_id: str,
    record: dict[str, Any],
    test: TestProjection,
) -> list[str]:
    provenance = record.get('provenance') if isinstance(record.get('provenance'), dict) else {}
    user_id = str(provenance.get('tester_user_id') or '').strip()
    system_id = str(provenance.get('system_id') or '').strip()
    compute_profile_id = str(provenance.get('compute_profile_id') or '').strip() or None
    if not user_id or not system_id:
        return []
    record_id = str(record.get('id') or '').strip()
    statements: list[str] = []

    evidence = record.get('evidence') if isinstance(record.get('evidence'), dict) else {}
    responses = evidence.get('responses') if isinstance(evidence.get('responses'), list) else []
    for index, response in enumerate(responses):
        if not isinstance(response, dict):
            continue
        usage = response.get('usage') if isinstance(response.get('usage'), dict) else {}
        timing = response.get('timing') if isinstance(response.get('timing'), dict) else {}
        for key, value in (
            ('input_tokens', usage.get('input_tokens')),
            ('output_tokens', usage.get('output_tokens')),
            ('ttft', timing.get('ttft_ms')),
            ('total_time', timing.get('total_ms')),
        ):
            sql = _telemetry_insert(
                report_id=report_id,
                record_id=record_id,
                user_id=user_id,
                system_id=system_id,
                compute_profile_id=compute_profile_id,
                test=test,
                telemetry_type_id=key,
                sample_ordinal=index,
                value=value,
                context=_context_json('response', response_index=index),
            )
            if sql:
                statements.append(sql)

    for key in ('score_percent', 'workspace_protocol_steps', 'output_file_count', 'exact_output_match'):
        value = _metric_value(record, key)
        sql = _telemetry_insert(
            report_id=report_id,
            record_id=record_id,
            user_id=user_id,
            system_id=system_id,
            compute_profile_id=compute_profile_id,
            test=test,
            telemetry_type_id=key,
            sample_ordinal=0,
            value=value,
            context=_context_json('record_metric'),
        )
        if sql:
            statements.append(sql)

    telemetry = evidence.get('telemetry') if isinstance(evidence.get('telemetry'), dict) else {}
    samples = telemetry.get('samples') if isinstance(telemetry.get('samples'), list) else []
    gpu_map = (
        ('gpu_util_percent', 'gpu_util_percent'),
        ('memory_util_percent', 'gpu_memory_util_percent'),
        ('memory_used_mib', 'gpu_memory_used_mib'),
        ('temperature_c', 'gpu_temperature_c'),
        ('power_w', 'gpu_power_w'),
    )
    for sample_index, sample in enumerate(samples):
        if not isinstance(sample, dict):
            continue
        observed_at = str(sample.get('measured_at') or '').strip() or None
        memory = sample.get('memory') if isinstance(sample.get('memory'), dict) else {}
        for key, value in (
            ('cpu_util_percent', sample.get('cpu_util_percent')),
            ('memory_used_bytes', memory.get('used_bytes')),
        ):
            sql = _telemetry_insert(
                report_id=report_id,
                record_id=record_id,
                user_id=user_id,
                system_id=system_id,
                compute_profile_id=compute_profile_id,
                test=test,
                telemetry_type_id=key,
                sample_ordinal=sample_index,
                value=value,
                observed_at=observed_at,
                context=_context_json('tester_system'),
            )
            if sql:
                statements.append(sql)
        gpus = sample.get('gpus') if isinstance(sample.get('gpus'), list) else []
        for gpu_index, gpu in enumerate(gpus):
            if not isinstance(gpu, dict):
                continue
            gpu_context = _context_json(
                'tester_system_gpu',
                gpu_index=gpu.get('index', gpu_index),
                gpu_uuid=gpu.get('uuid'),
                gpu_name=gpu.get('name'),
            )
            for raw_key, canonical_key in gpu_map:
                sql = _telemetry_insert(
                    report_id=report_id,
                    record_id=record_id,
                    user_id=user_id,
                    system_id=system_id,
                    compute_profile_id=compute_profile_id,
                    test=test,
                    telemetry_type_id=canonical_key,
                    sample_ordinal=sample_index,
                    value=gpu.get(raw_key),
                    observed_at=observed_at,
                    context=gpu_context,
                )
                if sql:
                    statements.append(sql)
    return statements


def rebuild_report_projection(mysql: MySQLSettings, report: dict[str, Any]) -> None:
    report_meta = report.get('report') if isinstance(report.get('report'), dict) else {}
    report_id = str(report_meta.get('id') or '').strip()
    records = report.get('records')
    if records is None:
        records = []
    entities = report.get('entities') if isinstance(report.get('entities'), dict) else {}
    test_entities = entities.get('test') if isinstance(entities.get('test'), dict) else {}
    if not report_id or not isinstance(records, list):
        raise ValueError('report projection requires report.id and records array')

    tests: dict[str, TestProjection] = {}
    for test_ref, entity in test_entities.items():
        if isinstance(test_ref, str) and isinstance(entity, dict):
            projected = _test_projection(test_ref, entity)
            if projected is not None:
                tests[test_ref] = projected

    statements = ['START TRANSACTION']

    for test in tests.values():
        statements.append(f"""
INSERT IGNORE INTO LMTS_test_definitions (
  test_definition_id, namespace, name, description, category
) VALUES (
  {_hex_text(test.test_definition_id)},
  {_hex_text(test.namespace)},
  {_hex_text(test.title)},
  {_nullable_text(test.description)},
  NULL
)
""".strip())
        statements.append(f"""
INSERT IGNORE INTO LMTS_test_versions (
  test_version_id, test_definition_id, version, kind,
  definition_json, fingerprint, status
) VALUES (
  {_hex_text(test.test_version_id)},
  {_hex_text(test.test_definition_id)},
  {_hex_text(test.version)},
  'standard',
  {_hex_text(test.definition_json)},
  {_hex_text(test.fingerprint)},
  'candidate'
)
""".strip())
        for ordinal, telemetry_type in enumerate(test.telemetry_types):
            statements.append(f"""
INSERT IGNORE INTO LMTS_test_version_telemetry_types (
  test_version_id, telemetry_type_id, required, ordinal
) VALUES (
  {_hex_text(test.test_version_id)},
  {_hex_text(telemetry_type)},
  FALSE,
  {ordinal}
)
""".strip())

    for record in records:
        if not isinstance(record, dict):
            continue
        record_id = str(record.get('id') or '').strip()
        coordinates = record.get('coordinates') if isinstance(record.get('coordinates'), dict) else {}
        test_ref = str(coordinates.get('test') or '').strip()
        test = tests.get(test_ref)
        if not record_id:
            continue
        provenance = record.get('provenance') if isinstance(record.get('provenance'), dict) else {}
        tester = str(provenance.get('tester_user_id') or '').strip() or None
        system_id = str(provenance.get('system_id') or '').strip() or None
        compute_profile_id = str(provenance.get('compute_profile_id') or '').strip() or None
        timing = record.get('timing') if isinstance(record.get('timing'), dict) else {}
        outcome = record.get('outcome') if isinstance(record.get('outcome'), dict) else {}
        target_id = str(coordinates.get('target') or '').strip()
        targets = entities.get('target') if isinstance(entities.get('target'), dict) else {}
        target_entity = targets.get(target_id) if isinstance(targets.get(target_id), dict) else {}
        target_props = target_entity.get('properties') if isinstance(target_entity.get('properties'), dict) else {}
        target_kind = str(target_props.get('kind') or '').strip() or 'unknown'
        evidence = record.get('evidence') if isinstance(record.get('evidence'), dict) else {}
        execution_metadata = evidence.get('execution_metadata') if isinstance(evidence.get('execution_metadata'), dict) else {}
        runtime_configuration = execution_metadata.get('runtime_configuration')
        runtime_json = None if runtime_configuration is None else _canonical_json(runtime_configuration)
        duration = _duration_ms(timing.get('started_at'), timing.get('completed_at'))
        statements.append(f"""
INSERT IGNORE INTO LMTS_report_record_index (
  report_id, record_id, tester_user_id, target_kind,
  test_version_id, system_id, compute_profile_id,
  started_at, completed_at, duration_ms, ttft_ms,
  outcome, passed, score_percent, runtime_configuration_json
) VALUES (
  {_hex_text(report_id)},
  {_hex_text(record_id)},
  {_nullable_text(tester)},
  {_hex_text(target_kind)},
  {_nullable_text(None if test is None else test.test_version_id)},
  {_nullable_text(system_id)},
  {_nullable_text(compute_profile_id)},
  {_sql_datetime(timing.get('started_at'))},
  {_sql_datetime(timing.get('completed_at'))},
  {_sql_number(duration)},
  {_sql_number(_metric_value(record, 'ttft'))},
  {_nullable_text(str(outcome.get('result')) if outcome.get('result') is not None else None)},
  {_sql_bool(outcome.get('passed'))},
  {_sql_number(_metric_value(record, 'score_percent'))},
  {_nullable_text(runtime_json)}
)
""".strip())
        if test is not None:
            statements.extend(_record_telemetry(report_id, record, test))

    statements.append('COMMIT')
    _run(mysql, ';\n'.join(statements))


def rebuild_all_report_projections(mysql: MySQLSettings) -> int:
    """Rebuild all derived report indexes from immutable report_json documents."""
    from .mysql_reports import read_report

    raw = _run(mysql, 'SELECT report_id FROM LMTS_reports ORDER BY created_at, report_id')
    report_ids = [line.strip() for line in raw.splitlines() if line.strip()]
    for report_id in report_ids:
        rebuild_report_projection(mysql, read_report(mysql, report_id))
    return len(report_ids)
