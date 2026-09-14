from __future__ import annotations

import json
import os
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any

from .model import InputTemplate, VisualizationPreset
from .registry import DVSRegistry, JsonRegistry


def _definition_filename(item_id: str) -> str:
    encoded = urllib.parse.quote(item_id, safe='._-')
    if not encoded:
        raise ValueError('DVS definition id must not be empty')
    return f'{encoded}.json'


def _canonical_json(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def _is_direct_child(path: Path, root: Path) -> bool:
    return path.resolve().parent == root.resolve()


class DVSStudioStore:
    def __init__(self, registry: DVSRegistry) -> None:
        if registry.studio_root is None:
            raise ValueError('DVSStudioStore requires DVSRegistry with studio_root')
        self.registry = registry
        self.root = registry.studio_root
        self.templates_root = registry.studio_templates_root
        self.presets_root = registry.studio_presets_root
        assert self.templates_root is not None
        assert self.presets_root is not None

    def _path(self, root: Path, item_id: str) -> Path:
        return (root / _definition_filename(item_id)).resolve()

    def _assert_create(self, registry: JsonRegistry[Any], item_id: str) -> None:
        if registry.contains(item_id):
            raise ValueError(f'DVS definition {item_id!r} already exists')

    def _assert_update(self, registry: JsonRegistry[Any], root: Path, item_id: str) -> Path:
        if not registry.contains(item_id):
            raise KeyError(f'DVS registry has no item {item_id!r}')
        origin = registry.origin(item_id)
        if not _is_direct_child(origin, root):
            raise PermissionError(f'DVS system definition {item_id!r} is read-only')
        return origin

    def _write_and_reload(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        old_bytes = path.read_bytes() if path.exists() else None
        raw = _canonical_json(payload)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode='wb',
                prefix=f'.{path.name}.',
                suffix='.tmp',
                dir=path.parent,
                delete=False,
            ) as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
                temp_path = Path(handle.name)
            os.replace(temp_path, path)
            temp_path = None
            self.registry.reload()
        except Exception:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)
            if old_bytes is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(old_bytes)
            self.registry.reload()
            raise

    def create_input_template(self, payload: dict[str, Any]) -> InputTemplate:
        item = InputTemplate.from_dict(payload)
        self._assert_create(self.registry.templates, item.id)
        path = self._path(self.templates_root, item.id)
        if path.exists():
            raise ValueError(f'DVS Studio file already exists for {item.id!r}')
        self._write_and_reload(path, item.to_dict())
        return self.registry.templates.get(item.id)

    def update_input_template(self, item_id: str, payload: dict[str, Any]) -> InputTemplate:
        item = InputTemplate.from_dict(payload)
        if item.id != item_id:
            raise ValueError('Input Template path id must match payload id')
        path = self._assert_update(self.registry.templates, self.templates_root, item.id)
        for preset in self.registry.presets.list():
            if preset.input_template_ref == item.id:
                preset.validate_against(item)
        self._write_and_reload(path, item.to_dict())
        return self.registry.templates.get(item.id)

    def create_visualization_preset(self, payload: dict[str, Any]) -> VisualizationPreset:
        item = VisualizationPreset.from_dict(payload)
        self._assert_create(self.registry.presets, item.id)
        template = self.registry.templates.get(item.input_template_ref)
        item.validate_against(template)
        path = self._path(self.presets_root, item.id)
        if path.exists():
            raise ValueError(f'DVS Studio file already exists for {item.id!r}')
        self._write_and_reload(path, item.to_dict())
        return self.registry.presets.get(item.id)

    def update_visualization_preset(self, item_id: str, payload: dict[str, Any]) -> VisualizationPreset:
        item = VisualizationPreset.from_dict(payload)
        if item.id != item_id:
            raise ValueError('Visualization Preset path id must match payload id')
        path = self._assert_update(self.registry.presets, self.presets_root, item.id)
        template = self.registry.templates.get(item.input_template_ref)
        item.validate_against(template)
        self._write_and_reload(path, item.to_dict())
        return self.registry.presets.get(item.id)
