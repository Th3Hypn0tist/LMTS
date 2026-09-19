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
                'system_id': 'sys_test',
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
    assert 'INSERT INTO test_definitions' in query
    assert 'INSERT INTO test_versions' in query
    assert 'INSERT INTO test_version_telemetry_types' in query
    assert 'INSERT INTO report_record_index' in query
    assert 'INSERT INTO telemetry_values' in query
    assert 'input_tokens' in query
    assert 'gpu_memory_used_mib' in query
    assert 'usr_test' not in query
    assert '7573725f74657374' in query
    assert query.strip().endswith('COMMIT;')


def test_projection_without_provenance_indexes_result_but_not_telemetry(monkeypatch) -> None:
    report = _report()
    report['records'][0]['provenance'] = {}
    captured = {}

    def fake_run(mysql, query):
        captured['query'] = query
        return ''

    monkeypatch.setattr(projection, '_run', fake_run)
    projection.rebuild_report_projection(_mysql(), report)

    assert 'INSERT INTO report_record_index' in captured['query']
    assert 'INSERT INTO telemetry_values' not in captured['query']
