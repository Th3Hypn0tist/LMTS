from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmts.dvs.registry import DVSRegistry
from lmts.dvs.studio_preview import (
    find_input_template_range,
    preview_input_template,
    preview_visualization_preset,
    validate_input_template,
    validate_visualization_preset,
)


def _template(item_id: str = 'table') -> dict:
    return {
        'format': 's3d.dvs.input-template',
        'version': '1.0',
        'id': item_id,
        'source_format': 'example/1.0',
        'reader': 'json',
        'rows': 'records[*]',
        'columns': [
            {'name': 'kind', 'selector': 'kind', 'type': 'string'},
            {'name': 'value', 'selector': 'value', 'type': 'number', 'nullable': True},
        ],
    }


def _preset(item_id: str = 'view', template_id: str = 'table') -> dict:
    return {
        'format': 's3d.dvs.visualization-preset',
        'version': '1.0',
        'id': item_id,
        'source_format': 'example/1.0',
        'input_template_ref': template_id,
        'generations': [{
            'id': 'root',
            'primitive': 'box',
            'bindings': {
                'position.x': {'column': 'kind', 'interpretation': 'categorical-index'},
                'scale.y': {
                    'column': 'value',
                    'interpretation': 'number-or-null',
                    'transform': {'null': 'not-rendered'},
                },
            },
        }],
    }


def _registry(tmp_path: Path) -> DVSRegistry:
    templates = tmp_path / 'templates'
    templates.mkdir(parents=True)
    (templates / 'table.json').write_text(json.dumps(_template()), encoding='utf-8')
    return DVSRegistry(templates_root=templates, presets_root=tmp_path / 'presets')


def test_validate_input_template_is_non_persistent() -> None:
    result = validate_input_template(_template('draft'))
    assert result['id'] == 'draft'
    assert [column['name'] for column in result['columns']] == ['kind', 'value']
    assert [column['type'] for column in result['columns']] == ['string', 'number']


def test_preview_input_template_projects_typed_draft_definition() -> None:
    result = preview_input_template({
        'definition': _template('draft'),
        'source': {
            'records': [
                {'kind': 'a', 'value': '1.5'},
                {'kind': 'b', 'value': None},
            ],
        },
    })
    assert result['input_template']['id'] == 'draft'
    assert result['columns'] == ['kind', 'value']
    assert result['column_types'] == ['string', 'number']
    assert result['rows'] == [['a', 1.5], ['b', None]]
    assert result['parameters'] == {}


def test_preview_input_template_rejects_missing_source_field() -> None:
    with pytest.raises(ValueError):
        preview_input_template({
            'definition': _template('draft'),
            'source': {'records': [{'kind': 'a'}]},
        })


def test_find_input_template_range_uses_typed_values_before_scale() -> None:
    definition = _template('draft')
    definition['columns'][1]['scale'] = {'low': 0, 'high': 100, 'power': 2}
    result = find_input_template_range({
        'definition': definition,
        'source': {
            'records': [
                {'kind': 'a', 'value': '5.5'},
                {'kind': 'b', 'value': None},
                {'kind': 'c', 'value': 12},
            ],
        },
        'column': 'value',
    })
    assert result == {
        'input_template_id': 'draft',
        'column': 'value',
        'low': 5.5,
        'high': 12.0,
    }


def test_validate_visualization_preset_uses_registered_template(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    result = validate_visualization_preset(_preset('draft-view'), registry)
    assert result['id'] == 'draft-view'
    assert result['input_template_ref'] == 'table'


def test_validate_visualization_preset_rejects_unknown_column(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    payload = _preset('bad-view')
    payload['generations'][0]['bindings']['scale.y']['column'] = 'missing'
    with pytest.raises(ValueError):
        validate_visualization_preset(payload, registry)


def test_preview_visualization_preset_returns_visual_plan_without_registry_mutation(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    before = registry.presets.list()
    result = preview_visualization_preset({
        'definition': _preset('draft-view'),
        'source': {
            'records': [
                {'kind': 'alpha', 'value': 2},
                {'kind': 'beta', 'value': 4},
            ],
        },
    }, registry)
    assert result['visualization_preset']['id'] == 'draft-view'
    assert result['visual_plan']['format'] == 's3d.dvs.visual-plan'
    assert result['visual_plan']['row_count'] == 2
    assert registry.presets.list() == before == ()


def test_preview_request_is_closed_shape(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    with pytest.raises(ValueError, match='requires exactly definition and source'):
        preview_visualization_preset({
            'definition': _preset('draft-view'),
            'source': {'records': []},
            'extra': True,
        }, registry)
