from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmts.reporting import REPORT_FORMAT, REPORT_VERSION, project_matrix_bundle
from lmts.tools.report_contract_php import REPORT_CONTRACT_VALIDATOR_PHP
from lmts.tools.web_deploy import APP_JS, REPORT_CONTRACT_NAME, REPORT_PHP, web_root_files


SCHEMA = Path('lmts/reporting/LMTS_Benchmark_Report_Template_v1.1.schema.json')


def _bundle() -> dict:
    return {
        'schema_version': 1,
        'export_type': 'lmts.matrix_bundle',
        'exported_at': '2026-09-01T12:01:00+00:00',
        'matrix': {
            'matrix_id': 'matrix-1',
            'started_at': '2026-09-01T12:00:00+00:00',
            'completed_at': '2026-09-01T12:01:00+00:00',
            'status': 'completed',
            'target_ids': ['model-a'],
            'target_kinds': {'model-a': 'model'},
            'test_refs': ['core.text_generation@1.0.0'],
            'cells': [
                {
                    'target_id': 'model-a',
                    'target_kind': 'model',
                    'test_ref': 'core.text_generation@1.0.0',
                    'run_id': 'run-1',
                    'status': 'completed',
                    'passed': True,
                    'result_path': 'results/run-1.json',
                }
            ],
            'passed': 1,
            'failed': 0,
            'errors': 0,
            'cancelled': 0,
        },
        'runs': [
            {
                'run_id': 'run-1',
                'test_ref': 'core.text_generation@1.0.0',
                'executor_id': 'model-a',
                'executor_kind': 'model',
                'status': 'completed',
                'passed': True,
                'started_at': '2026-09-01T12:00:00+00:00',
                'completed_at': '2026-09-01T12:00:01+00:00',
                'score': {'total': 1.0, 'maximum': 1.0},
                'metrics': {
                    'input_tokens': 10,
                    'output_tokens': 5,
                    'ttft_ms': 100.0,
                    'total_ms': 1000.0,
                },
                'system_context': {'profile_id': 'profile-a'},
            }
        ],
    }


def test_report_template_identity() -> None:
    schema = json.loads(SCHEMA.read_text(encoding='utf-8'))
    assert schema['properties']['format']['const'] == REPORT_FORMAT
    assert schema['properties']['version']['const'] == REPORT_VERSION


def test_projector_emits_report_v11() -> None:
    report = project_matrix_bundle(_bundle())
    assert report['format'] == REPORT_FORMAT
    assert report['version'] == REPORT_VERSION
    assert report['source']['type'] == 'lmts.matrix_bundle'
    assert report['summary']['records'] == 1
    assert report['summary']['targets'] == 1
    assert report['summary']['tests'] == 1
    assert report['summary']['system_profiles'] == [{'profile_id': 'profile-a'}]


def test_projector_keeps_distinct_system_profiles_with_same_id() -> None:
    bundle = _bundle()
    first = dict(bundle['runs'][0])
    duplicate = dict(first)
    different_same_id = dict(first)
    different_same_id['run_id'] = 'run-2'
    different_same_id['system_context'] = {
        'profile_id': 'profile-a',
        'profile': {'cpu': {'model_name': 'CPU B'}},
    }
    bundle['runs'] = [first, duplicate, different_same_id]

    report = project_matrix_bundle(bundle)

    assert report['summary']['system_profiles'] == [
        {'profile_id': 'profile-a'},
        {'profile_id': 'profile-a', 'profile': {'cpu': {'model_name': 'CPU B'}}},
    ]


def test_results_server_and_dvs_share_report_v11_contract() -> None:
    files = web_root_files()
    contract_path = f'contracts/{REPORT_CONTRACT_NAME}'
    validator_path = 'lib/report_contract.php'
    assert contract_path in files
    assert validator_path in files
    assert files[validator_path] == REPORT_CONTRACT_VALIDATOR_PHP
    assert "require_once dirname(__DIR__) . '/lib/report_contract.php'" in REPORT_PHP
    assert 'lmts_validate_report_document' in REPORT_PHP
    assert "report?.version !== '1.1'" in APP_JS
    assert 'report id already exists with different content' in REPORT_PHP
    assert 'ON DUPLICATE KEY UPDATE' not in REPORT_PHP
    assert '"const": "1.1"' in files[contract_path]
    assert all(not path.startswith('public/') for path in files)


def test_result_viewer_consumes_report_system_profile_index() -> None:
    assert 'report.summary?.system_profiles' in APP_JS
    assert "text: 'System Profiles'" in APP_JS
    assert "['Systems', systemProfiles.length]" in APP_JS
    assert "JSON.stringify(profile, null, 2)" in APP_JS
