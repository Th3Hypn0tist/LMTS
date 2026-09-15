from __future__ import annotations

from typing import Any

from .model import InputTemplate, VisualizationPreset
from .registry import DVSRegistry
from .runtime import project_visualization


def _require_object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be a JSON object')
    return value


def _preview_request(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    if set(payload) != {'definition', 'source'}:
        raise ValueError('Studio preview requires exactly definition and source')
    definition = _require_object(payload['definition'], 'definition')
    source = _require_object(payload['source'], 'source')
    return definition, source


def validate_input_template(payload: dict[str, Any]) -> dict[str, Any]:
    return InputTemplate.from_dict(_require_object(payload, 'Input Template')).to_dict()


def preview_input_template(payload: dict[str, Any]) -> dict[str, Any]:
    definition, source = _preview_request(payload)
    template = InputTemplate.from_dict(definition)
    extracted = template.extract(source)
    return {
        'input_template': template.to_dict(),
        'columns': list(extracted.columns),
        'rows': [list(row) for row in extracted.rows],
    }


def validate_visualization_preset(payload: dict[str, Any], registry: DVSRegistry) -> dict[str, Any]:
    preset = VisualizationPreset.from_dict(_require_object(payload, 'Visualization Preset'))
    template = registry.templates.get(preset.input_template_ref)
    preset.validate_against(template)
    return preset.to_dict()


def preview_visualization_preset(payload: dict[str, Any], registry: DVSRegistry) -> dict[str, Any]:
    definition, source = _preview_request(payload)
    preset = VisualizationPreset.from_dict(definition)
    template = registry.templates.get(preset.input_template_ref)
    preset.validate_against(template)
    return {
        'visualization_preset': preset.to_dict(),
        'visual_plan': project_visualization(source, template, preset),
    }
