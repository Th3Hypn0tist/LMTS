from __future__ import annotations

import json
from pathlib import Path

import pytest

from lmts.dvs.registry import DVSRegistry
from lmts.dvs.studio import DVSStudioStore


def _template(item_id: str, *, column: str = 'value', source_format: str = 'example/1.0') -> dict:
    return {
        'format': 's3d.dvs.input-template',
        'version': '1.0',
        'id': item_id,
        'source_format': source_format,
        'reader': 'json',
        'rows': 'records[*]',
        'columns': [{'name': column, 'selector': column, 'type': 'number'}],
    }


def _preset(item_id: str, template_id: str, *, column: str = 'value', source_format: str = 'example/1.0') -> dict:
    return {
        'format': 's3d.dvs.visualization-preset',
        'version': '1.0',
        'id': item_id,
        'source_format': source_format,
        'input_template_ref': template_id,
        'generations': [{
            'id': 'root',
            'primitive': 'box',
            'bindings': {'scale.y': {'column': column, 'interpretation': 'number'}},
        }],
    }


def _write(root: Path, filename: str, payload: dict) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / filename
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path.resolve()


def _store(tmp_path: Path) -> tuple[DVSRegistry, DVSStudioStore]:
    registry = DVSRegistry(
        templates_root=tmp_path / 'system-templates',
        presets_root=tmp_path / 'system-presets',
        studio_root=tmp_path / 'studio',
    )
    return registry, DVSStudioStore(registry)


def test_studio_creates_canonical_template_and_encoded_filename(tmp_path: Path) -> None:
    registry, store = _store(tmp_path)
    item = store.create_input_template(_template('user/template'))

    assert item.id == 'user/template'
    origin = registry.templates.origin(item.id)
    assert origin.parent == registry.studio_templates_root
    assert origin.name == 'user%2Ftemplate.json'
    persisted = json.loads(origin.read_text(encoding='utf-8'))
    assert persisted == item.to_dict()
    assert origin.read_text(encoding='utf-8').endswith('\n')


def test_studio_updates_only_user_owned_template(tmp_path: Path) -> None:
    registry, store = _store(tmp_path)
    store.create_input_template(_template('user.template'))
    updated = store.update_input_template('user.template', _template('user.template', column='score'))
    assert [column.name for column in updated.columns] == ['score']

    system_path = _write(
        tmp_path / 'system-templates',
        'system.template.json',
        _template('system.template'),
    )
    registry.reload()
    before = system_path.read_bytes()
    with pytest.raises(PermissionError, match='read-only'):
        store.update_input_template('system.template', _template('system.template', column='score'))
    assert system_path.read_bytes() == before


def test_template_update_rejects_breaking_dependent_preset_without_writing(tmp_path: Path) -> None:
    registry, store = _store(tmp_path)
    store.create_input_template(_template('table'))
    store.create_visualization_preset(_preset('view', 'table'))
    origin = registry.templates.origin('table')
    before = origin.read_bytes()

    with pytest.raises(ValueError):
        store.update_input_template('table', _template('table', column='renamed'))

    assert origin.read_bytes() == before
    assert [column.name for column in registry.templates.get('table').columns] == ['value']
    assert registry.presets.get('view').input_template_ref == 'table'


def test_studio_preset_requires_existing_compatible_template(tmp_path: Path) -> None:
    registry, store = _store(tmp_path)
    with pytest.raises(KeyError, match="has no item 'missing'"):
        store.create_visualization_preset(_preset('view', 'missing'))
    assert registry.presets.list() == ()

    store.create_input_template(_template('table'))
    with pytest.raises(ValueError):
        store.create_visualization_preset(_preset('view', 'table', column='missing-column'))
    assert registry.presets.list() == ()


def test_studio_create_rejects_existing_system_id(tmp_path: Path) -> None:
    _write(tmp_path / 'system-templates', 'system.json', _template('system'))
    registry = DVSRegistry(
        templates_root=tmp_path / 'system-templates',
        presets_root=tmp_path / 'system-presets',
        studio_root=tmp_path / 'studio',
    )
    store = DVSStudioStore(registry)

    with pytest.raises(ValueError, match='already exists'):
        store.create_input_template(_template('system'))
    assert not (tmp_path / 'studio' / 'templates').exists()


def test_studio_update_requires_matching_path_and_payload_id(tmp_path: Path) -> None:
    _, store = _store(tmp_path)
    store.create_input_template(_template('table'))
    with pytest.raises(ValueError, match='path id must match payload id'):
        store.update_input_template('table', _template('different'))


def test_studio_preset_create_and_update_round_trip(tmp_path: Path) -> None:
    registry, store = _store(tmp_path)
    store.create_input_template(_template('table'))
    created = store.create_visualization_preset(_preset('view', 'table'))
    assert created.id == 'view'
    origin = registry.presets.origin('view')
    assert origin.parent == registry.studio_presets_root

    payload = _preset('view', 'table')
    payload['generations'][0]['bindings'] = {
        'position.y': {'column': 'value', 'interpretation': 'number'},
    }
    updated = store.update_visualization_preset('view', payload)
    assert list(updated.generations[0].bindings) == ['position.y']
