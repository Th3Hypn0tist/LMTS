from __future__ import annotations

import json
from pathlib import Path
from typing import Generic, TypeVar

from .model import InputTemplate, VisualizationPreset


T = TypeVar('T')


class JsonRegistry(Generic[T]):
    def __init__(self, root: Path, loader) -> None:
        self.root = root
        self.loader = loader
        self._items: dict[str, T] = {}
        self.reload()

    def reload(self) -> None:
        items: dict[str, T] = {}
        if self.root.exists():
            for path in sorted(self.root.glob('*.json')):
                payload = json.loads(path.read_text(encoding='utf-8'))
                item = self.loader(payload)
                item_id = getattr(item, 'id')
                if item_id in items:
                    raise ValueError(f'duplicate DVS registry id {item_id!r} in {self.root}')
                items[item_id] = item
        self._items = items

    def list(self) -> tuple[T, ...]:
        return tuple(self._items[key] for key in sorted(self._items))

    def get(self, item_id: str) -> T:
        try:
            return self._items[item_id]
        except KeyError as exc:
            raise KeyError(f'DVS registry has no item {item_id!r}') from exc


class DVSRegistry:
    def __init__(self, *, templates_root: Path | None = None, presets_root: Path | None = None) -> None:
        package_root = Path(__file__).resolve().parent
        self.templates = JsonRegistry(templates_root or package_root / 'templates', InputTemplate.from_dict)
        self.presets = JsonRegistry(presets_root or package_root / 'presets', VisualizationPreset.from_dict)
        self.validate_presets()

    def reload(self) -> None:
        self.templates.reload()
        self.presets.reload()
        self.validate_presets()

    def validate_presets(self) -> None:
        for preset in self.presets.list():
            template = self.templates.get(preset.input_template_ref)
            preset.validate_against(template)
