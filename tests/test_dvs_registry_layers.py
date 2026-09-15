from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmts.dvs.registry import DVSRegistry


def _write_template(root: Path, item_id: str, *, source_format: str = 'example/1.0') -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f'{item_id}.json'
    path.write_text(json.dumps({
        'format': 's3d.dvs.input-template',
        'version': '1.0',
        'id': item_id,
        'source_format': source_format,
        'reader': 'json',
        'rows': 'records[*]',
        'columns': [{'name': 'value', 'selector': 'value', 'type': 'number'}],
    }), encoding='utf-8')
    return path.resolve()


def _write_preset(root: Path, item_id: str, template_id: str, *, source_format: str = 'example/1.0') -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / f'{item_id}.json'
    path.write_text(json.dumps({
        'format': 's3d.dvs.visualization-preset',
        'version': '1.0',
        'id': item_id,
        'source_format': source_format,
        'input_template_ref': template_id,
        'generations': [{
            'id': 'root',
            'primitive': 'box',
            'bindings': {'scale.y': {'column': 'value', 'interpretation': 'number'}},
        }],
    }), encoding='utf-8')
    return path.resolve()


def test_registry_merges_system_and_studio_definitions_with_origins(tmp_path: Path) -> None:
    system_templates = tmp_path / 'system-templates'
    system_presets = tmp_path / 'system-presets'
    studio_root = tmp_path / 'studio'

    system_template = _write_template(system_templates, 'system.template')
    _write_preset(system_presets, 'system.preset', 'system.template')
    studio_template = _write_template(studio_root / 'templates', 'user.template')
    _write_preset(studio_root / 'presets', 'user.preset', 'user.template')

    registry = DVSRegistry(
        templates_root=system_templates,
        presets_root=system_presets,
        studio_root=studio_root,
    )

    assert [item.id for item in registry.templates.list()] == ['system.template', 'user.template']
    assert [item.id for item in registry.presets.list()] == ['system.preset', 'user.preset']
    assert registry.templates.origin('system.template') == system_template
    assert registry.templates.origin('user.template') == studio_template
    assert registry.studio_templates_root == (studio_root / 'templates').resolve()
    assert registry.studio_presets_root == (studio_root / 'presets').resolve()


def test_registry_rejects_cross_layer_id_shadowing(tmp_path: Path) -> None:
    system_templates = tmp_path / 'system-templates'
    studio_root = tmp_path / 'studio'
    _write_template(system_templates, 'shared')
    _write_template(studio_root / 'templates', 'shared')

    with pytest.raises(ValueError, match="duplicate DVS registry id 'shared'"):
        DVSRegistry(
            templates_root=system_templates,
            presets_root=tmp_path / 'system-presets',
            studio_root=studio_root,
        )


def test_registry_rejects_duplicate_root_configuration(tmp_path: Path) -> None:
    studio_root = tmp_path / 'studio'
    with pytest.raises(ValueError, match='roots must be unique'):
        DVSRegistry(
            templates_root=studio_root / 'templates',
            presets_root=tmp_path / 'presets',
            studio_root=studio_root,
        )


def test_registry_origin_rejects_unknown_id(tmp_path: Path) -> None:
    registry = DVSRegistry(
        templates_root=tmp_path / 'templates',
        presets_root=tmp_path / 'presets',
    )
    with pytest.raises(KeyError, match="has no item 'missing'"):
        registry.templates.origin('missing')
