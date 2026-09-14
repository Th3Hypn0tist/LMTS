from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from lmts.reporting import project_matrix_bundle
from lmts.tools.report_contract_php import REPORT_CONTRACT_VALIDATOR_PHP


PHP = shutil.which('php')


def _bundle() -> dict:
    return {
        'schema_version': 1,
        'export_type': 'lmts.matrix_bundle',
        'exported_at': '2026-09-14T10:00:00+00:00',
        'matrix': {
            'matrix_id': 'matrix-contract-php',
            'started_at': '2026-09-14T09:59:00+00:00',
            'completed_at': '2026-09-14T10:00:00+00:00',
            'status': 'completed',
            'target_ids': ['model-a'],
            'test_refs': ['core.text_generation@1.0.0#text-generation'],
        },
        'runs': [{
            'run_id': 'run-contract-php',
            'executor_id': 'model-a',
            'executor_kind': 'model',
            'test_ref': 'core.text_generation@1.0.0#text-generation',
            'started_at': '2026-09-14T09:59:10+00:00',
            'completed_at': '2026-09-14T09:59:11+00:00',
            'status': 'completed',
            'passed': True,
            'metrics': {'ttft_ms': 10.0, 'custom_metric': 42},
            'score': {'percent': 100.0, 'dimensions': []},
            'artifacts': {},
            'responses': [],
            'workspace_trace': [],
            'system_context': {'profile_id': 'profile-a'},
            'telemetry': {},
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


def _validator_process(tmp_path: Path, report: dict) -> subprocess.CompletedProcess[str]:
    if PHP is None:
        pytest.skip('PHP CLI is required for report server contract integration tests')

    validator = tmp_path / 'report_contract.php'
    validator.write_text(REPORT_CONTRACT_VALIDATOR_PHP, encoding='utf-8')
    schema_source = Path('lmts/reporting/LMTS_Benchmark_Report_Template_v1.1.schema.json')
    schema = tmp_path / schema_source.name
    schema.write_text(schema_source.read_text(encoding='utf-8'), encoding='utf-8')

    runner = tmp_path / 'validate.php'
    runner.write_text(
        "<?php\n"
        "declare(strict_types=1);\n"
        "require __DIR__ . '/report_contract.php';\n"
        "$raw = stream_get_contents(STDIN);\n"
        "$document = json_decode($raw, false, 512, JSON_THROW_ON_ERROR);\n"
        "if (!($document instanceof stdClass)) { throw new RuntimeException('root'); }\n"
        "lmts_validate_report_document($document, __DIR__ . '/LMTS_Benchmark_Report_Template_v1.1.schema.json');\n"
        "fwrite(STDOUT, 'OK');\n",
        encoding='utf-8',
    )
    return subprocess.run(
        [PHP, str(runner)],
        input=json.dumps(report, ensure_ascii=False),
        text=True,
        capture_output=True,
        check=False,
    )


def test_php_contract_validator_accepts_projected_report(tmp_path: Path) -> None:
    report = project_matrix_bundle(_bundle())
    result = _validator_process(tmp_path, report)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'OK'


@pytest.mark.parametrize(
    ('mutator', 'message'),
    [
        (
            lambda report: report['records'][0]['coordinates'].__setitem__('target', 'missing-model'),
            "references missing entity 'missing-model'",
        ),
        (
            lambda report: report['metric_definitions'].pop('custom_metric'),
            'has no metric definition',
        ),
        (
            lambda report: report['summary'].__setitem__('records', 2),
            'does not match records array length',
        ),
        (
            lambda report: report['summary']['outcomes'].__setitem__('pass', 0),
            'expected 1 from records',
        ),
        (
            lambda report: report['views'][0].__setitem__('row_dimension', 'missing-dimension'),
            'references an unknown dimension',
        ),
    ],
)
def test_php_contract_validator_rejects_semantic_drift(tmp_path: Path, mutator, message: str) -> None:
    report = copy.deepcopy(project_matrix_bundle(_bundle()))
    mutator(report)
    result = _validator_process(tmp_path, report)
    assert result.returncode != 0
    assert message in result.stderr


def test_php_contract_validator_keeps_open_world_fields(tmp_path: Path) -> None:
    report = project_matrix_bundle(_bundle())
    report['future_top_level'] = {'arbitrary': ['open', 'world']}
    report['report']['future_metadata'] = {'revision': 7}
    report['records'][0]['evidence']['future_evidence'] = {'value': 123}
    report['summary']['future_aggregate'] = {'median': 12.5}
    result = _validator_process(tmp_path, report)
    assert result.returncode == 0, result.stderr
    assert result.stdout == 'OK'
