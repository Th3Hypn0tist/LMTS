import json
from pathlib import Path

from lmts.core.result_export import export_matrix_bundle, export_run_json


def test_single_run_export_is_canonical_run_json(tmp_path: Path) -> None:
    run = {'run_id': 'run-123', 'executor_id': 'bot.demo', 'executor_kind': 'bot', 'status': 'completed'}
    path = export_run_json(run, tmp_path / 'exports')
    assert json.loads(path.read_text(encoding='utf-8')) == run
    assert '-run-run-123.json' in path.name


def test_matrix_export_contains_manifest_and_referenced_runs(tmp_path: Path) -> None:
    results_root = tmp_path / 'results'
    run_path = results_root / 'subjects' / 'bot' / 'bot.demo' / 'fingerprint' / 'tests' / 't' / 'runs' / 'run-1.json'
    run_path.parent.mkdir(parents=True)
    run = {
        'run_id': 'run-1',
        'executor_id': 'bot.demo',
        'executor_kind': 'bot',
        'test_ref': 't',
        'status': 'completed',
        'passed': True,
    }
    run_path.write_text(json.dumps(run), encoding='utf-8')
    matrix = {
        'matrix_id': 'matrix-1',
        'target_ids': ['bot.demo'],
        'target_kinds': {'bot.demo': 'bot'},
        'test_refs': ['t'],
        'cells': [
            {
                'target_id': 'bot.demo',
                'target_kind': 'bot',
                'test_ref': 't',
                'run_id': 'run-1',
                'status': 'completed',
                'passed': True,
                'result_path': str(run_path),
            }
        ],
    }

    path = export_matrix_bundle(matrix, tmp_path / 'exports', results_root=results_root)
    payload = json.loads(path.read_text(encoding='utf-8'))
    assert payload['matrix'] == matrix
    assert payload['runs'] == [run]


def test_matrix_export_never_reconstructs_missing_run(tmp_path: Path) -> None:
    results_root = tmp_path / 'results'
    matrix = {
        'matrix_id': 'matrix-1',
        'target_ids': ['bot.demo'],
        'target_kinds': {'bot.demo': 'bot'},
        'test_refs': ['t'],
        'cells': [
            {
                'target_id': 'bot.demo',
                'target_kind': 'bot',
                'test_ref': 't',
                'run_id': 'run-1',
                'status': 'completed',
                'passed': True,
                'result_path': str(results_root / 'does-not-exist.json'),
            }
        ],
    }
    try:
        export_matrix_bundle(matrix, tmp_path / 'exports', results_root=results_root)
    except FileNotFoundError:
        pass
    else:
        raise AssertionError('matrix export reconstructed a missing canonical run')


def test_matrix_export_rejects_run_outside_results_root(tmp_path: Path) -> None:
    results_root = tmp_path / 'results'
    matrix = {
        'matrix_id': 'matrix-1',
        'target_ids': ['bot.demo'],
        'target_kinds': {'bot.demo': 'bot'},
        'test_refs': ['t'],
        'cells': [
            {
                'target_id': 'bot.demo',
                'target_kind': 'bot',
                'test_ref': 't',
                'run_id': 'run-1',
                'status': 'completed',
                'passed': True,
                'result_path': str(tmp_path / 'outside-results.json'),
            }
        ],
    }
    try:
        export_matrix_bundle(matrix, tmp_path / 'exports', results_root=results_root)
    except ValueError as exc:
        assert 'escapes results root' in str(exc)
    else:
        raise AssertionError('matrix export accepted a canonical run outside results root')
