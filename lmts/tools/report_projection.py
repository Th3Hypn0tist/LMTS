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



def _has_identity_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple)):
        return bool(value)
    return True


def _identity_resolution(identity: dict[str, object], required: tuple[str, ...]) -> str:
    if all(_has_identity_value(identity.get(key)) for key in required):
        return 'exact'
    if any(_has_identity_value(value) for value in identity.values()):
        return 'partial'
    return 'unknown'


def _hardware_spec(category: str, probe: dict[str, Any]) -> dict[str, str | None] | None:
    if category == 'cpu':
        identity: dict[str, object] = {
            'architecture': probe.get('architecture'),
            'vendor_id': probe.get('vendor_id'),
            'model_name': probe.get('model_name'),
        }
        required = ('architecture', 'vendor_id', 'model_name')
        label = str(probe.get('model_name') or '').strip() or 'Unknown CPU'
        vendor = str(probe.get('vendor_id') or '').strip() or None
    elif category == 'gpu':
        identity = {
            'vendor': probe.get('vendor'),
            'model': probe.get('model'),
            'vram_bytes': probe.get('vram_bytes'),
            'memory_type': probe.get('memory_type'),
        }
        required = ('vendor', 'model', 'vram_bytes')
        label = str(probe.get('model') or probe.get('vendor') or '').strip() or 'Unknown GPU'
        vendor = str(probe.get('vendor') or '').strip() or None
    elif category == 'npu':
        identity = {
            'class': probe.get('class'),
            'vendor_id': probe.get('vendor_id'),
            'device_id': probe.get('device_id'),
            'subsystem_vendor_id': probe.get('subsystem_vendor_id'),
            'subsystem_device_id': probe.get('subsystem_device_id'),
            'modalias': probe.get('modalias'),
        }
        required = ('vendor_id', 'device_id')
        label = str(probe.get('name') or '').strip()
        if not label:
            vendor_id = str(probe.get('vendor_id') or '').strip()
            device_id = str(probe.get('device_id') or '').strip()
            label = ':'.join(part for part in (vendor_id, device_id) if part) or 'Unknown NPU'
        vendor = str(probe.get('vendor_id') or '').strip() or None
    else:
        raise ValueError(f'unsupported hardware category: {category}')

    if not any(_has_identity_value(value) for value in identity.values()):
        return None
    identity_json = _canonical_json(identity)
    digest = hashlib.sha256((category + '\0' + identity_json).encode('utf-8')).hexdigest()
    return {
        'hardware_id': 'hw_' + digest[:40],
        'category': category,
        'canonical_key': category + ':' + digest,
        'label': label,
        'vendor': vendor,
        'resolution_type': _identity_resolution(identity, required),
        'identity_json': identity_json,
        'profile_json': _canonical_json(probe),
    }


def _hardware_statements(system_id: str, profile: dict[str, Any]) -> list[str]:
    statements: list[str] = []

    def add_resource(category: str, local_key: str, probe: dict[str, Any]) -> None:
        hardware = _hardware_spec(category, probe)
        if hardware is None:
            return
        statements.append(f"""
INSERT INTO LMTS_hardware_nodes (
  hardware_id, category, level, parent_id, canonical_key,
  label, vendor, resolution_type, identity_json, profile_json
) VALUES (
  {_hex_text(str(hardware['hardware_id']))},
  {_hex_text(str(hardware['category']))},
  'component',
  NULL,
  {_hex_text(str(hardware['canonical_key']))},
  {_hex_text(str(hardware['label']))},
  {_nullable_text(None if hardware['vendor'] is None else str(hardware['vendor']))},
  {_hex_text(str(hardware['resolution_type']))},
  {_hex_text(str(hardware['identity_json']))},
  {_hex_text(str(hardware['profile_json']))}
)
ON DUPLICATE KEY UPDATE
  label = VALUES(label),
  vendor = VALUES(vendor),
  resolution_type = VALUES(resolution_type),
  profile_json = VALUES(profile_json)
""".strip())
        resource_id = _stable_id('sysres_', system_id, local_key)
        statements.append(f"""
INSERT INTO LMTS_system_resources (
  system_resource_id, system_id, local_key, resource_kind,
  hardware_id, resolution_status, probe_data_json
) VALUES (
  {_hex_text(resource_id)},
  {_hex_text(system_id)},
  {_hex_text(local_key)},
  {_hex_text(category)},
  {_hex_text(str(hardware['hardware_id']))},
  {_hex_text(str(hardware['resolution_type']))},
  {_hex_text(_canonical_json(probe))}
)
ON DUPLICATE KEY UPDATE
  hardware_id = VALUES(hardware_id),
  resolution_status = VALUES(resolution_status),
  probe_data_json = VALUES(probe_data_json),
  updated_at = CURRENT_TIMESTAMP(6)
""".strip())

    cpu = profile.get('cpu')
    if isinstance(cpu, dict) and cpu:
        add_resource('cpu', 'cpu:0', cpu)

    gpus = profile.get('gpu')
    if isinstance(gpus, list):
        for index, gpu in enumerate(gpus):
            if isinstance(gpu, dict):
                add_resource('gpu', f'gpu:{index}', gpu)

    npus = profile.get('npu')
    if isinstance(npus, list):
        for index, npu in enumerate(npus):
            if isinstance(npu, dict):
                add_resource('npu', f'npu:{index}', npu)

    memory = profile.get('memory')
    if isinstance(memory, dict):
        capacity = memory.get('total_bytes')
        if isinstance(capacity, int) and not isinstance(capacity, bool) and capacity > 0:
            pool_id = _stable_id('mempool_', system_id, 'system')
            statements.append(f"""
INSERT INTO LMTS_system_memory_pools (
  memory_pool_id, system_id, pool_kind, capacity_bytes, properties_json
) VALUES (
  {_hex_text(pool_id)},
  {_hex_text(system_id)},
  'system',
  {capacity},
  {_hex_text(_canonical_json(memory))}
)
ON DUPLICATE KEY UPDATE
  capacity_bytes = VALUES(capacity_bytes),
  properties_json = VALUES(properties_json)
""".strip())

    return statements


def _system_statements(record: dict[str, Any]) -> list[str]:
    provenance = record.get('provenance') if isinstance(record.get('provenance'), dict) else {}
    user_id = str(provenance.get('tester_user_id') or '').strip()
    system_id = str(provenance.get('system_id') or '').strip()
    if not user_id or not system_id:
        return []

    evidence = record.get('evidence') if isinstance(record.get('evidence'), dict) else {}
    context = evidence.get('system_context') if isinstance(evidence.get('system_context'), dict) else None
    if context is None:
        raise ValueError(f'report references system {system_id} without system_context evidence')

    fingerprint = str(context.get('fingerprint') or '').strip()
    schema_version = context.get('schema_version')
    identity = context.get('identity')
    profile = context.get('profile')
    if (
        not fingerprint
        or isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or not isinstance(identity, dict)
        or not isinstance(profile, dict)
    ):
        raise ValueError(f'system_context for {system_id} has invalid canonical identity')

    identity_json = _canonical_json(identity)
    calculated = hashlib.sha256(identity_json.encode('utf-8')).hexdigest()
    if calculated != fingerprint:
        raise ValueError('system_context fingerprint does not match canonical hardware identity')
    expected_id = _stable_id('sys_', user_id, fingerprint)
    if expected_id != system_id:
        raise ValueError(f'system_id {system_id} does not match report system_context fingerprint')

    configuration_id = 'cfg_' + fingerprint[:40]
    hardware_profile = {
        key: profile[key]
        for key in ('cpu', 'memory', 'gpu', 'npu')
        if key in profile
    }
    profiled_at = context.get('profiled_at')
    profiled_sql = _sql_datetime(profiled_at)
    probe_version = f'profile-v{schema_version}'
    statements = [f"""
INSERT INTO LMTS_hardware_configurations (
  configuration_id, fingerprint, label, identity_json, profile_json
) VALUES (
  {_hex_text(configuration_id)},
  {_hex_text(fingerprint)},
  {_hex_text('Configuration ' + fingerprint[:12])},
  {_hex_text(identity_json)},
  {_hex_text(_canonical_json(hardware_profile))}
)
ON DUPLICATE KEY UPDATE
  label = VALUES(label),
  identity_json = VALUES(identity_json),
  profile_json = VALUES(profile_json),
  updated_at = CURRENT_TIMESTAMP(6)
""".strip(), f"""
INSERT INTO LMTS_systems (
  system_id, user_id, label, system_class, configuration_id, probe_version, last_probed_at
) VALUES (
  {_hex_text(system_id)},
  {_hex_text(user_id)},
  {_hex_text('System ' + fingerprint[:12])},
  'local',
  {_hex_text(configuration_id)},
  {_hex_text(probe_version)},
  {profiled_sql}
)
ON DUPLICATE KEY UPDATE
  configuration_id = VALUES(configuration_id),
  probe_version = VALUES(probe_version),
  last_probed_at = CASE
    WHEN VALUES(last_probed_at) IS NULL THEN last_probed_at
    WHEN last_probed_at IS NULL OR last_probed_at < VALUES(last_probed_at) THEN VALUES(last_probed_at)
    ELSE last_probed_at
  END
""".strip()]
    statements.extend(_hardware_statements(system_id, profile))
    return statements



def _variance_statements(
    *,
    report_id: str,
    record: dict[str, Any],
    test: TestProjection,
    target_kind: str,
    target_ref: str,
) -> list[str]:
    provenance = record.get('provenance') if isinstance(record.get('provenance'), dict) else {}
    user_id = str(provenance.get('tester_user_id') or '').strip() or None
    system_id = str(provenance.get('system_id') or '').strip()
    if not system_id or not target_kind or not target_ref:
        return []

    evidence = record.get('evidence') if isinstance(record.get('evidence'), dict) else {}
    context = evidence.get('system_context') if isinstance(evidence.get('system_context'), dict) else {}
    fingerprint = str(context.get('fingerprint') or '').strip()
    if not fingerprint:
        return []
    configuration_id = 'cfg_' + fingerprint[:40]

    outcome = record.get('outcome') if isinstance(record.get('outcome'), dict) else {}
    full_outcome = str(outcome.get('result') or '').strip()
    if full_outcome not in {'pass', 'fail'}:
        return []

    timing = record.get('timing') if isinstance(record.get('timing'), dict) else {}
    samples: list[dict[str, object]] = [{
        'outcome': full_outcome,
        'observed_at': timing.get('completed_at'),
    }]
    extras = evidence.get('variance_samples')
    if extras is not None:
        if not isinstance(extras, list):
            raise ValueError('variance_samples evidence must be an array')
        for sample in extras:
            if not isinstance(sample, dict):
                raise ValueError('variance sample must be an object')
            sample_outcome = str(sample.get('outcome') or '').strip()
            if sample_outcome not in {'pass', 'fail'}:
                raise ValueError('variance sample outcome must be pass or fail')
            samples.append({
                'outcome': sample_outcome,
                'observed_at': sample.get('observed_at'),
            })

    record_id = str(record.get('id') or '').strip()
    target_hash = hashlib.sha256((target_kind + '\0' + target_ref).encode('utf-8')).hexdigest()
    statements: list[str] = []
    for ordinal, sample in enumerate(samples):
        sample_id = _stable_id('var_', report_id, record_id, str(ordinal))
        statements.append(f"""
INSERT INTO LMTS_variance_samples (
  variance_sample_id, target_kind, target_ref, target_identity_hash,
  test_version_id, configuration_id, tester_user_id, outcome,
  observed_at, source_report_id, source_record_id, sample_ordinal
) VALUES (
  {_hex_text(sample_id)},
  {_hex_text(target_kind)},
  {_hex_text(target_ref)},
  {_hex_text(target_hash)},
  {_hex_text(test.test_version_id)},
  {_hex_text(configuration_id)},
  {_nullable_text(user_id)},
  {_hex_text(str(sample['outcome']))},
  {_sql_datetime(sample.get('observed_at'))},
  {_hex_text(report_id)},
  {_hex_text(record_id)},
  {ordinal}
)
ON DUPLICATE KEY UPDATE
  target_kind = VALUES(target_kind),
  target_ref = VALUES(target_ref),
  target_identity_hash = VALUES(target_identity_hash),
  test_version_id = VALUES(test_version_id),
  configuration_id = VALUES(configuration_id),
  tester_user_id = VALUES(tester_user_id),
  outcome = VALUES(outcome),
  observed_at = VALUES(observed_at)
""".strip())
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
    projected_system_ids: set[str] = set()

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
        if system_id is not None and system_id not in projected_system_ids:
            statements.extend(_system_statements(record))
            projected_system_ids.add(system_id)
        compute_profile_id = str(provenance.get('compute_profile_id') or '').strip() or None
        timing = record.get('timing') if isinstance(record.get('timing'), dict) else {}
        outcome = record.get('outcome') if isinstance(record.get('outcome'), dict) else {}
        target_id = str(coordinates.get('target') or '').strip()
        targets = entities.get('target') if isinstance(entities.get('target'), dict) else {}
        target_entity = targets.get(target_id) if isinstance(targets.get(target_id), dict) else {}
        target_props = target_entity.get('properties') if isinstance(target_entity.get('properties'), dict) else {}
        target_kind = str(target_props.get('kind') or '').strip() or 'unknown'
        target_ref = target_id or None
        target_label = str(target_entity.get('label') or '').strip() or target_ref
        evidence = record.get('evidence') if isinstance(record.get('evidence'), dict) else {}
        execution_metadata = evidence.get('execution_metadata') if isinstance(evidence.get('execution_metadata'), dict) else {}
        runtime_configuration = execution_metadata.get('runtime_configuration')
        runtime_json = None if runtime_configuration is None else _canonical_json(runtime_configuration)
        duration = _duration_ms(timing.get('started_at'), timing.get('completed_at'))
        statements.append(f"""
INSERT INTO LMTS_report_record_index (
  report_id, record_id, tester_user_id, target_kind, target_ref, target_label,
  test_version_id, system_id, compute_profile_id,
  started_at, completed_at, duration_ms, ttft_ms,
  outcome, passed, score_percent, runtime_configuration_json
) VALUES (
  {_hex_text(report_id)},
  {_hex_text(record_id)},
  {_nullable_text(tester)},
  {_hex_text(target_kind)},
  {_nullable_text(target_ref)},
  {_nullable_text(target_label)},
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
ON DUPLICATE KEY UPDATE
  target_kind = VALUES(target_kind),
  target_ref = VALUES(target_ref),
  target_label = VALUES(target_label),
  test_version_id = VALUES(test_version_id),
  system_id = VALUES(system_id),
  compute_profile_id = VALUES(compute_profile_id),
  started_at = VALUES(started_at),
  completed_at = VALUES(completed_at),
  duration_ms = VALUES(duration_ms),
  ttft_ms = VALUES(ttft_ms),
  outcome = VALUES(outcome),
  passed = VALUES(passed),
  score_percent = VALUES(score_percent),
  runtime_configuration_json = VALUES(runtime_configuration_json)
""".strip())
        if test is not None:
            statements.extend(_variance_statements(
                report_id=report_id,
                record=record,
                test=test,
                target_kind=target_kind,
                target_ref=target_id,
            ))
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
