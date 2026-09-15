from __future__ import annotations

from typing import Any

from .projector import project_matrix_bundle


def project_run_result(run: dict[str, Any]) -> dict[str, Any]:
    run_id = str(run.get('run_id') or '').strip()
    target_id = str(run.get('executor_id') or '').strip()
    target_kind = str(run.get('executor_kind') or '').strip()
    test_ref = str(run.get('test_ref') or '').strip()
    started_at = str(run.get('started_at') or '').strip()
    completed_at = str(run.get('completed_at') or '').strip()
    status = str(run.get('status') or '').strip()
    if not all((run_id, target_id, target_kind, test_ref, started_at, completed_at, status)):
        raise ValueError('canonical run is missing identity, timing or status fields')

    bundle = {
        'schema_version': 1,
        'export_type': 'lmts.matrix_bundle',
        'exported_at': completed_at,
        'matrix': {
            'matrix_id': run_id,
            'started_at': started_at,
            'completed_at': completed_at,
            'status': status,
            'target_ids': [target_id],
            'target_kinds': {target_id: target_kind},
            'test_refs': [test_ref],
            'cells': [{
                'target_id': target_id,
                'target_kind': target_kind,
                'test_ref': test_ref,
                'run_id': run_id,
                'status': status,
                'passed': run.get('passed'),
                'result_path': '',
            }],
            'passed': 1 if run.get('passed') is True else 0,
            'failed': 1 if run.get('passed') is False and status == 'completed' else 0,
            'errors': 1 if status not in {'completed', 'cancelled'} else 0,
            'cancelled': 1 if status == 'cancelled' else 0,
        },
        'runs': [run],
    }
    report = project_matrix_bundle(bundle)
    report['report']['title'] = 'LMTS Test Report'
    report['source'] = {
        'type': 'lmts.run',
        'id': run_id,
        'schema_version': 1,
        'exported_at': completed_at,
    }
    return report
