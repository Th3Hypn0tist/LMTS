from __future__ import annotations

import lmts.tools.report_projection as projection
from lmts.core.settings import MySQLSettings


def _mysql() -> MySQLSettings:
    return MySQLSettings(
        host='db.example',
        database='lmts',
        username='lmts',
        password='secret',
        publish_key='unused',
    )


def _report() -> dict:
    identity = {
        'cpu': {
            'architecture': 'x86_64',
            'vendor_id': 'GenuineIntel',
            'model_name': 'Test CPU',
        },
        'memory': {
            'total_bytes': 16 * 1024 ** 3,
            'memory_type': 'DDR5',
            'ecc': False,
            'speed_mt_s': 5600,
            'configured_speed_mt_s': 5200,
            'form_factor': 'DIMM',
            'modules': [],
        },
        'gpu': [],
        'npu': [],
    }
    fingerprint = projection.hashlib.sha256(
        projection._canonical_json(identity).encode('utf-8')
    ).hexdigest()
    system_id = projection._stable_id('sys_', 'usr_test', fingerprint)
    telemetry_types = [
        'input_tokens', 'output_tokens', 'ttft', 'total_time', 'score_percent',
        'workspace_protocol_steps', 'output_file_count', 'exact_output_match',
        'cpu_util_percent', 'memory_used_bytes', 'gpu_util_percent',
        'gpu_memory_util_percent', 'gpu_memory_used_mib', 'gpu_temperature_c', 'gpu_power_w',
    ]
    return {
        'report': {'id': 'report-1'},
        'entities': {
            'test': {
                'core.text_generation@1.0.0#text-generation': {
                    'label': 'Text generation',
                    'properties': {
                        'namespace': 'core.text_generation',
                        'version': '1.0.0',
                        'title': 'Text generation',
                        'description': 'Smoke test',
                        'minimum_level': 'quick',
                        'mandatory': False,
                        'telemetry_types': telemetry_types,
                    },
                },
            },
            'target': {
                'ollama-local:model': {
                    'label': 'model',
                    'properties': {'kind': 'model'},
                },
            },
        },
        'records': [{
            'id': 'run-1',
            'coordinates': {
                'target': 'ollama-local:model',
                'test': 'core.text_generation@1.0.0#text-generation',
            },
            'provenance': {
                'tester_user_id': 'usr_test',
                'system_id': system_id,
                'compute_profile_id': None,
            },
            'timing': {
                'started_at': '2026-09-19T12:00:00+00:00',
                'completed_at': '2026-09-19T12:00:01+00:00',
            },
            'outcome': {'result': 'pass', 'passed': True},
            'metrics': {
                'score_percent': {'value': 100.0, 'unit': 'percent'},
            },
            'evidence': {
                'system_context': {
                    'schema_version': 7,
                    'profiled_at': '2026-09-19T11:59:00+00:00',
                    'fingerprint': fingerprint,
                    'identity': identity,
                    'profile': {
                        'cpu': identity['cpu'],
                        'memory': identity['memory'],
                        'gpu': [],
                        'npu': [],
                        'software': {'os': 'Linux'},
                    },
                },
                'execution_metadata': {'runtime_configuration': {'temperature': 0}},
                'responses': [{
                    'usage': {'input_tokens': 10, 'output_tokens': 4},
                    'timing': {'ttft_ms': 25.0, 'total_ms': 150.0},
                }],
                'telemetry': {
                    'format': 'lmts.telemetry',
                    'version': 1,
                    'scope': 'tester_system',
                    'samples': [{
                        'measured_at': '2026-09-19T12:00:00.500000+00:00',
                        'cpu_util_percent': 12.5,
                        'memory': {'used_bytes': 123456},
                        'gpus': [{
                            'index': 0,
                            'uuid': 'GPU-test',
                            'name': 'Test GPU',
                            'gpu_util_percent': 75.0,
                            'memory_util_percent': 20.0,
                            'memory_used_mib': 1024.0,
                            'temperature_c': 60.0,
                            'power_w': 100.0,
                        }],
                    }],
                },
            },
        }],
    }


def test_projection_writes_test_record_and_telemetry(monkeypatch) -> None:
    captured = {}

    def fake_run(mysql, query):
        captured['query'] = query
        return ''

    monkeypatch.setattr(projection, '_run', fake_run)
    projection.rebuild_report_projection(_mysql(), _report())

    query = captured['query']
    assert 'INSERT INTO LMTS_test_definitions' in query
    assert 'INSERT INTO LMTS_test_versions' in query
    assert 'INSERT INTO LMTS_test_version_telemetry_types' in query
    assert 'INSERT INTO LMTS_hardware_configurations' in query
    assert 'INSERT INTO LMTS_systems' in query
    assert 'INSERT INTO LMTS_hardware_nodes' in query
    assert 'INSERT INTO LMTS_system_memory_pools' in query
    assert 'INSERT INTO LMTS_report_record_index' in query
    assert 'target_ref, target_label' in query
    assert 'ON DUPLICATE KEY UPDATE' in query
    assert '6f6c6c616d612d6c6f63616c3a6d6f64656c' in query
    assert 'INSERT INTO LMTS_variance_samples' in query
    assert 'INSERT INTO LMTS_telemetry_values' in query
    assert 'input_tokens' in query
    assert 'gpu_memory_used_mib' in query
    assert 'usr_test' not in query
    assert '7573725f74657374' in query
    assert query.strip().endswith('COMMIT')


def test_projection_backfills_observed_target_identity_on_replay(monkeypatch) -> None:
    report = _report()
    report['entities']['target']['ollama-local:model']['label'] = 'ollama-local:model'
    captured = {}

    def fake_run(mysql, query):
        captured['query'] = query
        return ''

    monkeypatch.setattr(projection, '_run', fake_run)
    projection.rebuild_report_projection(_mysql(), report)

    query = captured['query']
    assert 'target_ref = VALUES(target_ref)' in query
    assert 'target_label = VALUES(target_label)' in query
    assert '6f6c6c616d612d6c6f63616c3a6d6f64656c' in query


def test_projection_without_provenance_indexes_result_but_not_telemetry(monkeypatch) -> None:
    report = _report()
    report['records'][0]['provenance'] = {}
    captured = {}

    def fake_run(mysql, query):
        captured['query'] = query
        return ''

    monkeypatch.setattr(projection, '_run', fake_run)
    projection.rebuild_report_projection(_mysql(), report)

    assert 'INSERT INTO LMTS_report_record_index' in captured['query']
    assert 'INSERT INTO LMTS_telemetry_values' not in captured['query']



def test_projection_adds_lightweight_variance_samples_without_extra_telemetry(monkeypatch) -> None:
    report = _report()
    record = report['records'][0]
    record['evidence']['variance_samples'] = [
        {'outcome': 'pass', 'observed_at': '2026-09-19T12:00:02+00:00'},
        {'outcome': 'fail', 'observed_at': '2026-09-19T12:00:03+00:00'},
    ]
    captured = {}

    def fake_run(mysql, query):
        captured['query'] = query
        return ''

    monkeypatch.setattr(projection, '_run', fake_run)
    projection.rebuild_report_projection(_mysql(), report)

    query = captured['query']
    assert query.count('INSERT INTO LMTS_variance_samples') == 3
    assert query.count('INSERT INTO LMTS_telemetry_values') > 0
    assert "70617373" in query
    assert "6661696c" in query
