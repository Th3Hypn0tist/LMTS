from lmts.reporting.projector import project_matrix_bundle


def test_report_record_keeps_rebuildable_run_provenance():
    bundle = {
        'schema_version': 1,
        'export_type': 'lmts.matrix_bundle',
        'exported_at': '2026-09-19T12:00:01+00:00',
        'matrix': {
            'matrix_id': 'matrix-1',
            'started_at': '2026-09-19T12:00:00+00:00',
            'completed_at': '2026-09-19T12:00:01+00:00',
            'status': 'completed',
            'target_ids': ['model-a'],
            'test_refs': ['core.text_generation@1.0.0'],
        },
        'runs': [{
            'run_id': 'run-1',
            'executor_id': 'model-a',
            'executor_kind': 'model',
            'test_ref': 'core.text_generation@1.0.0',
            'status': 'completed',
            'passed': True,
            'started_at': '2026-09-19T12:00:00+00:00',
            'completed_at': '2026-09-19T12:00:01+00:00',
            'metrics': {},
            'provenance': {
                'tester_user_id': 'usr_test',
                'system_id': 'sys_test',
                'compute_profile_id': None,
            },
        }],
    }
    report = project_matrix_bundle(bundle)
    assert report['records'][0]['provenance']['tester_user_id'] == 'usr_test'
    assert report['records'][0]['provenance']['system_id'] == 'sys_test'
