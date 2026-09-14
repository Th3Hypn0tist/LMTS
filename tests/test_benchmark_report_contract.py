from pathlib import Path

from lmts.reporting import REPORT_FORMAT, REPORT_VERSION, project_matrix_bundle
from lmts.tools.web_deploy import REPORT_CONTRACT_NAME, REPORT_PHP, APP_JS, web_root_files


def _bundle() -> dict:
    return {
        'schema_version': 1,
        'export_type': 'lmts.matrix_bundle',
        'exported_at': '2026-09-14T10:00:00+00:00',
        'matrix': {
            'matrix_id': 'matrix-contract',
            'started_at': '2026-09-14T09:59:00+00:00',
            'completed_at': '2026-09-14T10:00:00+00:00',
            'status': 'completed',
            'target_ids': ['model-a'],
            'test_refs': ['core.text_generation@1.0.0#text-generation'],
        },
        'runs': [{
            'run_id': 'run-contract',
            'executor_id': 'model-a',
            'executor_kind': 'model',
            'test_ref': 'core.text_generation@1.0.0#text-generation',
            'started_at': '2026-09-14T09:59:10+00:00',
            'completed_at': '2026-09-14T09:59:11+00:00',
            'status': 'completed',
            'passed': True,
            'metrics': {'ttft_ms': 10.0, 'custom_metric': 42},
            'score': {'percent': 100.0, 'dimensions': []},
            'artifacts': {'answer': 'ok'},
            'responses': [],
            'workspace_trace': [],
            'system_context': {'profile_id': 'profile-a'},
            'telemetry': {'gpu': {'peak_memory_bytes': 123}},
            'evaluation_subject': {
                'id': 'model-a',
                'kind': 'model',
                'label': 'Model A',
                'members': [],
                'configuration': {},
                'fingerprint': 'subject-fingerprint',
            },
            'execution_metadata': {
                'runtime_configuration_fingerprint': 'runtime-fingerprint',
                'test_minimum_level': 'quick',
                'test_mandatory': False,
            },
            'model_id': 'model-a',
            'model_ref': 'model-a:latest',
            'provider_ref': 'ollama-local',
            'model_metadata': {
                'digest': 'digest-a',
                'size': 100,
                'details': {
                    'family': 'test',
                    'parameter_size': '1B',
                    'quantization_level': 'Q4',
                },
            },
            'error': None,
        }],
    }


def test_projector_emits_open_world_benchmark_report_v11() -> None:
    report = project_matrix_bundle(_bundle())
    assert report['format'] == REPORT_FORMAT == 'lmts.report'
    assert report['version'] == REPORT_VERSION == '1.1'
    assert report['report']['type'] == 'benchmark'
    assert report['report']['benchmark']['test_refs'] == ['core.text_generation@1.0.0#text-generation']
    assert report['metric_definitions']['custom_metric']['value_type'] == 'int'
    assert report['records'][0]['metrics']['custom_metric'] == {'value': 42}
    assert report['records'][0]['evidence']['artifacts'] == {'answer': 'ok'}
    assert report['records'][0]['evidence']['system_context'] == {'profile_id': 'profile-a'}
    assert report['summary']['targets'] == 1
    assert report['summary']['tests'] == 1


def test_results_server_and_dvs_share_report_v11_contract() -> None:
    files = web_root_files()
    contract_path = f'public/contracts/{REPORT_CONTRACT_NAME}'
    assert contract_path in files
    assert 'LMTS_REPORT_VERSION = \'1.1\'' in REPORT_PHP
    assert "report?.version !== '1.1'" in APP_JS
    assert 'report id already exists with different content' in REPORT_PHP
    assert 'ON DUPLICATE KEY UPDATE' not in REPORT_PHP
    assert '"const": "1.1"' in files[contract_path]


def test_dvs_input_template_targets_same_report_contract() -> None:
    path = Path('lmts/dvs/templates/lmts-report-v1.1.json')
    text = path.read_text(encoding='utf-8')
    assert '"source_format": "lmts.report/1.1"' in text
    assert '"selector": "metrics.score_percent.value"' in text
