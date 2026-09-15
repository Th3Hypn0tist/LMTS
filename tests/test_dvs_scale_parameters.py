from __future__ import annotations

from lmts.dvs.model import InputTemplate, VisualizationPreset
from lmts.dvs.runtime import project_visualization


def test_input_scale_propagates_as_one_bindable_visual_parameter() -> None:
    template = InputTemplate.from_dict({
        'format': 's3d.dvs.input-template',
        'version': '1.0',
        'id': 'scaled-input',
        'source_format': 'example/1.0',
        'reader': 'json',
        'rows': 'records[*]',
        'columns': [{
            'name': 'wind_speed',
            'selector': 'wind_speed',
            'type': 'number',
            'scale': {'low': 0.2, 'high': 5.9, 'power': 1.0},
        }],
    })
    preset = VisualizationPreset.from_dict({
        'format': 's3d.dvs.visualization-preset',
        'version': '1.0',
        'id': 'scaled-view',
        'source_format': 'example/1.0',
        'input_template_ref': 'scaled-input',
        'generations': [{
            'id': 'bars',
            'primitive': 'box',
            'bindings': {
                'scale.y': {'column': 'wind_speed', 'interpretation': 'number'},
            },
            'parameters': {
                'scale': 'scale.wind_speed',
            },
        }],
    })

    plan = project_visualization(
        {'records': [{'wind_speed': 1.4}]},
        template,
        preset,
    )

    expected_scale = {'low': 0.2, 'high': 5.9, 'power': 1.0}
    assert plan['parameters'] == {'scale.wind_speed': expected_scale}
    group = plan['generations'][0]['groups'][0]
    assert group['parameters'] == {'scale': expected_scale}
    assert group['channels']['scale.y'] == (1.4 - 0.2) / (5.9 - 0.2)


def test_visual_parameter_binding_rejects_missing_scale_parameter() -> None:
    template = InputTemplate.from_dict({
        'format': 's3d.dvs.input-template',
        'version': '1.0',
        'id': 'plain-input',
        'source_format': 'example/1.0',
        'reader': 'json',
        'rows': 'records[*]',
        'columns': [{
            'name': 'value',
            'selector': 'value',
            'type': 'number',
        }],
    })
    preset = VisualizationPreset.from_dict({
        'format': 's3d.dvs.visualization-preset',
        'version': '1.0',
        'id': 'bad-view',
        'source_format': 'example/1.0',
        'input_template_ref': 'plain-input',
        'generations': [{
            'id': 'axis',
            'primitive': 'group',
            'bindings': {},
            'parameters': {'scale': 'scale.value'},
        }],
    })

    try:
        preset.validate_against(template)
    except ValueError as exc:
        assert 'parameters reference unknown input parameters: scale.value' in str(exc)
    else:
        raise AssertionError('missing scale parameter must not be invented')
