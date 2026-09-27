from lmts.reporting import project_matrix_bundle


def test_matrix_bundle_projects_generic_target_report() -> None:
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
            'executor_id': 'bot.writer',
            'executor_kind': 'bot',
            'test_ref': 'core.text_generation@1.0.0#text-generation',
            'status': 'completed',
            'passed': True,
            'metrics': {'ttft_ms': 12.5},
            'score': {'percent': 100.0},
            'error': None,
            'evaluation_subject': {
                'id': 'bot.writer',
                'kind': 'bot',
                'label': 'Writer',
                'members': [],
                'configuration': {'mode': 'standalone'},
                'fingerprint': 'subject-fingerprint',
            },
            'execution_metadata': {
                'runtime_configuration_fingerprint': 'runtime-fingerprint',
            },
        }],
    }
    report = project_matrix_bundle(bundle)
    assert report['format'] == 'lmts.report'
    assert report['report']['id'] == 'matrix-1'
    assert report['summary']['outcomes']['pass'] == 1
    metrics = report['records'][0]['metrics']
    assert metrics['ttft'] == {'value': 12.5, 'unit': 'ms'}
    assert metrics['score_percent'] == {'value': 100.0, 'unit': 'percent'}
    assert metrics['input_tokens'] == {'value': None, 'unit': 'tokens'}
    assert metrics['output_tokens'] == {'value': None, 'unit': 'tokens'}
    assert metrics['total_time'] == {'value': None, 'unit': 'ms'}
    assert metrics['workspace_protocol_steps'] == {'value': None, 'unit': 'steps'}
    assert metrics['output_file_count'] == {'value': None, 'unit': 'files'}
    assert metrics['exact_output_match'] == {'value': None}
    assert report['views'][0]['row_dimension'] == 'target'
    assert report['entities']['target']['bot.writer']['properties']['configuration'] == {'mode': 'standalone'}



def test_matrix_report_excludes_error_cancelled_and_unknown_runs() -> None:
    def run(run_id, status, passed, error=None):
        return {
            'run_id': run_id,
            'executor_id': 'model-a',
            'executor_kind': 'model',
            'test_ref': 'core.text_generation@1.0.0',
            'status': status,
            'passed': passed,
            'metrics': {},
            'error': error,
        }

    bundle = {
        'schema_version': 1,
        'export_type': 'lmts.matrix_bundle',
        'exported_at': '2026-09-13T12:00:00+00:00',
        'matrix': {
            'matrix_id': 'matrix-filter',
            'started_at': '2026-09-13T11:59:00+00:00',
            'completed_at': '2026-09-13T12:00:00+00:00',
        },
        'runs': [
            run('pass-1', 'completed', True),
            run('fail-1', 'completed', False),
            run('error-1', 'failed', False, {'type': 'RuntimeError', 'message': 'boom'}),
            run('cancelled-1', 'cancelled', None),
            run('unknown-1', 'completed', None),
        ],
    }

    report = project_matrix_bundle(bundle)

    assert [record['id'] for record in report['records']] == ['pass-1', 'fail-1']
    assert report['summary']['records'] == 2
    assert report['summary']['outcomes'] == {
        'pass': 1,
        'fail': 1,
        'error': 0,
        'cancelled': 0,
        'unknown': 0,
    }
