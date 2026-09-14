from __future__ import annotations

import json
from pathlib import Path

from lmts.dvs.model import InputTemplate, VisualizationPreset
from lmts.dvs.registry import DVSRegistry


TEMPLATE_PATH = Path('lmts/dvs/templates/lmts-report-v1.1.json')
PRESET_PATH = Path('lmts/dvs/presets/lmts-benchmark-landscape-v1.json')


def test_lmts_report_template_and_benchmark_preset_are_compatible() -> None:
    template = InputTemplate.from_dict(json.loads(TEMPLATE_PATH.read_text(encoding='utf-8')))
    preset = VisualizationPreset.from_dict(json.loads(PRESET_PATH.read_text(encoding='utf-8')))
    preset.validate_against(template)

    assert template.source_format == 'lmts.report/1.1'
    assert preset.source_format == template.source_format
    assert preset.input_template_ref == template.id
    generation = preset.generations[0]
    assert generation.group_by == ('target', 'test')
    assert generation.bindings['scale.y'].column == 'score_percent'
    assert generation.bindings['color.r'].column == 'result'


def test_default_dvs_registry_loads_lmts_benchmark_preset() -> None:
    registry = DVSRegistry()
    preset = registry.presets.get('lmts.benchmark.landscape.v1')
    template = registry.templates.get('lmts.report.v1.1')
    preset.validate_against(template)


def test_lmts_report_input_template_projects_explicit_null_as_string() -> None:
    template = InputTemplate.from_dict(json.loads(TEMPLATE_PATH.read_text(encoding='utf-8')))
    report = {
        'records': [{
            'id': 'run-1',
            'coordinates': {'target': 'model-a', 'test': 'test-a'},
            'timing': {'started_at': None, 'completed_at': None},
            'outcome': {'status': 'completed', 'result': 'pass', 'passed': True},
            'metrics': {
                'input_tokens': {'value': None},
                'output_tokens': {'value': None},
                'ttft': {'value': None},
                'total_time': {'value': None},
                'score_percent': {'value': 100.0},
                'workspace_protocol_steps': {'value': None},
                'output_file_count': {'value': None},
                'exact_output_match': {'value': None},
            },
        }],
    }
    table = template.extract(report)
    row = dict(zip(table.columns, table.rows[0], strict=True))
    assert row['score_percent'] == '100.0'
    assert row['ttft_ms'] == 'null'
    assert row['started_at'] == 'null'
