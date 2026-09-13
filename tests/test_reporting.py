from lmts.reporting import project_matrix_bundle


def test_matrix_bundle_projects_generic_report() -> None:
    bundle = {
        'schema_version': 1,
        'export_type': 'lmts.matrix_bundle',
        'exported_at': '2026-09-13T12:00:00+00:00',
        'matrix': {
            'matrix_id': 'matrix-1',
            'started_at': '2026-09-13T11:59:00+00:00',
            'completed_at': '2026-09-13T12:00:00+00:00',
        },
        'runs': [{
            'run_id': 'run-1',
            'model_id': 'provider:model',
            'model_ref': 'model',
            'provider_ref': 'provider',
            'test_ref': 'core.text_generation@1.0.0#text-generation',
            'status': 'completed',
            'passed': True,
            'metrics': {'ttft_ms': 12.5},
            'error': None,
            'model_metadata': {
                'digest': 'abc',
                'details': {'family': 'test', 'parameter_size': '1B'},
            },
        }],
    }
    report = project_matrix_bundle(bundle)
    assert report['format'] == 'lmts.report'
    assert report['report']['id'] == 'matrix-1'
    assert report['summary']['outcomes']['pass'] == 1
    assert report['records'][0]['metrics']['ttft'] == {'value': 12.5, 'unit': 'ms'}
    assert report['views'][0]['row_dimension'] == 'model'
