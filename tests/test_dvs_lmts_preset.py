from __future__ import annotations

import json
from pathlib import Path

from lmts.dvs.model import InputTemplate, VisualizationPreset
from lmts.dvs.registry import DVSRegistry
from lmts.dvs.runtime import project_visualization


TEMPLATE_PATH = Path('lmts/dvs/templates/lmts-report-v1.1.json')
PRESET_PATH = Path('lmts/dvs/presets/lmts-benchmark-landscape-v1.json')


def _template_and_preset() -> tuple[InputTemplate, VisualizationPreset]:
    template = InputTemplate.from_dict(json.loads(TEMPLATE_PATH.read_text(encoding='utf-8')))
    preset = VisualizationPreset.from_dict(json.loads(PRESET_PATH.read_text(encoding='utf-8')))
    return template, preset


def _record(run_id: str, target: str, test: str, result: str, score: float | None) -> dict:
    return {
        'id': run_id,
        'coordinates': {'target': target, 'test': test},
        'timing': {
            'started_at': '2026-09-15T06:00:00+00:00',
            'completed_at': '2026-09-15T06:00:01+00:00',
        },
        'outcome': {'status': 'completed', 'result': result, 'passed': result == 'pass'},
        'metrics': {
            'input_tokens': {'value': None},
            'output_tokens': {'value': None},
            'ttft': {'value': None},
            'total_time': {'value': None},
            'score_percent': {'value': score},
            'workspace_protocol_steps': {'value': None},
            'output_file_count': {'value': None},
            'exact_output_match': {'value': None},
        },
    }


def test_lmts_report_template_and_benchmark_preset_are_compatible() -> None:
    template, preset = _template_and_preset()
    preset.validate_against(template)

    assert template.source_format == 'lmts.report/1.1'
    assert preset.source_format == template.source_format
    assert preset.input_template_ref == template.id
    assert {column.type for column in template.columns} <= {'string', 'number', 'boolean'}
    score_column = template.column('score_percent')
    assert score_column.scale is not None
    assert score_column.scale.to_dict() == {'low': 0.0, 'high': 100.0, 'power': 1.0}

    generation = preset.generations[0]
    assert generation.group_by == ('target', 'test')
    assert generation.parameters == {'score_scale': 'scale.score_percent'}
    assert generation.bindings['scale.y'].column == 'score_percent'
    assert generation.bindings['scale.y'].transform['domain'] == [0.0, 1.0]
    assert generation.bindings['color.r'].column == 'result'


def test_default_dvs_registry_loads_lmts_benchmark_preset() -> None:
    registry = DVSRegistry()
    preset = registry.presets.get('lmts.benchmark.landscape.v1')
    template = registry.templates.get('lmts.report.v1.1')
    preset.validate_against(template)


def test_lmts_report_input_template_preserves_types_and_normalizes_score() -> None:
    template, _ = _template_and_preset()
    report = {'records': [_record('run-1', 'model-a', 'test-a', 'pass', 100.0)]}
    table = template.extract(report)
    row = dict(zip(table.columns, table.rows[0], strict=True))
    assert row['score_percent'] == 1.0
    assert row['ttft_ms'] is None
    assert row['started_at'] == '2026-09-15T06:00:00+00:00'
    assert row['passed'] is True
    assert table.parameters == {
        'scale.score_percent': {'low': 0.0, 'high': 100.0, 'power': 1.0},
    }


def test_lmts_benchmark_visual_plan_maps_categories_score_and_result() -> None:
    template, preset = _template_and_preset()
    report = {
        'records': [
            _record('run-1', 'model-a', 'test-a', 'pass', 100.0),
            _record('run-2', 'model-b', 'test-b', 'fail', 50.0),
        ],
    }

    plan = project_visualization(report, template, preset)
    generation = plan['generations'][0]
    first, second = generation['groups']
    expected_scale = {'low': 0.0, 'high': 100.0, 'power': 1.0}

    assert plan['format'] == 's3d.dvs.visual-plan'
    assert plan['source_format'] == 'lmts.report/1.1'
    assert plan['row_count'] == 2
    assert plan['parameters'] == {'scale.score_percent': expected_scale}

    assert first['key'] == {'target': 'model-a', 'test': 'test-a'}
    assert first['source_rows'] == [0]
    assert first['visible'] is True
    assert first['parameters'] == {'score_scale': expected_scale}
    assert first['channels']['position.x'] == 0.0
    assert first['channels']['position.z'] == 0.0
    assert first['channels']['scale.y'] == 3.0
    assert first['channels']['color.r'] == 0.15
    assert first['channels']['color.g'] == 0.85
    assert first['channels']['color.b'] == 0.30

    assert second['key'] == {'target': 'model-b', 'test': 'test-b'}
    assert second['source_rows'] == [1]
    assert second['visible'] is True
    assert second['parameters'] == {'score_scale': expected_scale}
    assert second['channels']['position.x'] == 2.0
    assert second['channels']['position.z'] == 2.0
    assert second['channels']['scale.y'] == 1.55
    assert second['channels']['color.r'] == 0.95
    assert second['channels']['color.g'] == 0.45
    assert second['channels']['color.b'] == 0.10


def test_lmts_benchmark_visual_plan_preserves_explicit_null_as_not_rendered() -> None:
    template, preset = _template_and_preset()
    report = {'records': [_record('run-null', 'model-a', 'test-a', 'unknown', None)]}

    plan = project_visualization(report, template, preset)
    group = plan['generations'][0]['groups'][0]

    assert group['visible'] is False
    assert 'scale.y' not in group['channels']
    assert group['channels']['position.x'] == 0.0
    assert group['channels']['position.z'] == 0.0


def test_lmts_benchmark_visual_plan_rejects_unknown_result_category() -> None:
    template, preset = _template_and_preset()
    report = {'records': [_record('run-invalid', 'model-a', 'test-a', 'future-result', 20.0)]}

    try:
        project_visualization(report, template, preset)
    except ValueError as exc:
        assert "map has no value for category 'future-result'" in str(exc)
    else:
        raise AssertionError('unknown category must not fall back to an invented color')
