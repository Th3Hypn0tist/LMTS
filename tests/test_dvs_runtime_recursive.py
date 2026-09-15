from __future__ import annotations

from lmts.dvs.model import InputTemplate, VisualizationPreset
from lmts.dvs.runtime import project_visualization


def _template() -> InputTemplate:
    return InputTemplate.from_dict({
        'format': 's3d.dvs.input-template',
        'version': '1.0',
        'id': 'recursive-table',
        'source_format': 'example/1.0',
        'reader': 'json',
        'rows': 'records[*]',
        'columns': [
            {'name': 'target', 'selector': 'target', 'type': 'string'},
            {'name': 'test', 'selector': 'test', 'type': 'string'},
            {'name': 'run', 'selector': 'run', 'type': 'string'},
            {'name': 'score', 'selector': 'score', 'type': 'number'},
        ],
    })


def _preset() -> VisualizationPreset:
    return VisualizationPreset.from_dict({
        'format': 's3d.dvs.visualization-preset',
        'version': '1.0',
        'id': 'recursive-plan',
        'source_format': 'example/1.0',
        'input_template_ref': 'recursive-table',
        'generations': [{
            'id': 'targets',
            'primitive': 'group',
            'group_by': ['target'],
            'bindings': {},
            'children': [{
                'id': 'tests',
                'primitive': 'group',
                'group_by': ['test'],
                'bindings': {},
                'children': [{
                    'id': 'runs',
                    'primitive': 'box',
                    'group_by': ['run'],
                    'bindings': {
                        'scale.y': {
                            'column': 'score',
                            'interpretation': 'number',
                        },
                    },
                }],
            }],
        }],
    })


def test_recursive_generations_receive_only_parent_row_subset() -> None:
    source = {
        'records': [
            {'target': 'model-a', 'test': 'test-1', 'run': 'a1', 'score': 10},
            {'target': 'model-a', 'test': 'test-2', 'run': 'a2', 'score': 20},
            {'target': 'model-b', 'test': 'test-1', 'run': 'b1', 'score': 30},
            {'target': 'model-b', 'test': 'test-1', 'run': 'b2', 'score': 40},
        ],
    }

    plan = project_visualization(source, _template(), _preset())
    targets = plan['generations'][0]['groups']

    assert [group['key'] for group in targets] == [
        {'target': 'model-a'},
        {'target': 'model-b'},
    ]
    assert [group['source_rows'] for group in targets] == [[0, 1], [2, 3]]

    model_a_tests = targets[0]['children'][0]['groups']
    assert [group['key'] for group in model_a_tests] == [
        {'test': 'test-1'},
        {'test': 'test-2'},
    ]
    assert [group['source_rows'] for group in model_a_tests] == [[0], [1]]

    model_b_tests = targets[1]['children'][0]['groups']
    assert [group['key'] for group in model_b_tests] == [{'test': 'test-1'}]
    assert model_b_tests[0]['source_rows'] == [2, 3]

    model_b_runs = model_b_tests[0]['children'][0]['groups']
    assert [group['key'] for group in model_b_runs] == [
        {'run': 'b1'},
        {'run': 'b2'},
    ]
    assert [group['source_rows'] for group in model_b_runs] == [[2], [3]]
    assert [group['channels']['scale.y'] for group in model_b_runs] == [30.0, 40.0]


def test_recursive_source_rows_remain_original_input_indices_at_every_depth() -> None:
    source = {
        'records': [
            {'target': 'model-x', 'test': 'test-a', 'run': 'r0', 'score': 1},
            {'target': 'model-y', 'test': 'test-a', 'run': 'r1', 'score': 2},
            {'target': 'model-x', 'test': 'test-b', 'run': 'r2', 'score': 3},
        ],
    }

    plan = project_visualization(source, _template(), _preset())
    model_x = plan['generations'][0]['groups'][0]
    assert model_x['key'] == {'target': 'model-x'}
    assert model_x['source_rows'] == [0, 2]

    test_b = model_x['children'][0]['groups'][1]
    assert test_b['key'] == {'test': 'test-b'}
    assert test_b['source_rows'] == [2]

    run = test_b['children'][0]['groups'][0]
    assert run['key'] == {'run': 'r2'}
    assert run['source_rows'] == [2]
    assert run['channels']['scale.y'] == 3.0
