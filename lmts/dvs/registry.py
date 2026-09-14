from __future__ import annotations

import json
from pathlib import Path
from typing import Generic, Iterable, TypeVar

from .model import InputTemplate, VisualizationPreset


T = TypeVar('T')


class JsonRegistry(Generic[T]):
    def __init__(self, roots: Path | Iterable[Path], loader) -> None:
        if isinstance(roots, Path):
            resolved = (roots.resolve(),)
        else:
            resolved = tuple(Path(root).resolve() for root in roots)
        if not resolved:
            raise ValueError('JsonRegistry requires at least one root')
        if len(set(resolved)) != len(resolved):
            raise ValueError('JsonRegistry roots must be unique')
        self.roots = resolved
        self.root = resolved[0]
        self.loader = loader
        self._items: dict[str, T] = {}
        self._origins: dict[str, Path] = {}
        self.reload()

    def reload(self) -> None:
        items: dict[str, T] = {}
        origins: dict[str, Path] = {}
        for root in self.roots:
            if not root.exists():
                continue
            for path in sorted(root.glob('*.json')):
                payload = json.loads(path.read_text(encoding='utf-8'))
                item = self.loader(payload)
                item_id = getattr(item, 'id')
                if item_id in items:
                    raise ValueError(
                        f'duplicate DVS registry id {item_id!r}: {origins[item_id]} and {path.resolve()}'
                    )
                items[item_id] = item
                origins[item_id] = path.resolve()
        self._items = items
        self._origins = origins

    def list(self) -> tuple[T, ...]:
        return tuple(self._items[key] for key in sorted(self._items))

    def get(self, item_id: str) -> T:
        try:
            return self._items[item_id]
        except KeyError as exc:
            raise KeyError(f'DVS registry has no item {item_id!r}') from exc

    def contains(self, item_id: str) -> bool:
        return item_id in self._items

    def origin(self, item_id: str) -> Path:
        try:
            return self._origins[item_id]
        except KeyError as exc:
            raise KeyError(f'DVS registry has no item {item_id!r}') from exc


class DVSRegistry:
    def __init__(
        self,
        *,
        templates_root: Path | None = None,
        presets_root: Path | None = None,
        studio_root: Path | None = None,
    ) -> None:
        package_root = Path(__file__).resolve().parent
        template_roots = [Path(templates_root or package_root / 'templates').resolve()]
        preset_roots = [Path(presets_root or package_root / 'presets').resolve()]
        self.studio_root = Path(studio_root).resolve() if studio_root is not None else None
        if self.studio_root is not None:
            template_roots.append((self.studio_root / 'templates').resolve())
            preset_roots.append((self.studio_root / 'presets').resolve())
        self.templates = JsonRegistry(template_roots, InputTemplate.from_dict)
        self.presets = JsonRegistry(preset_roots, VisualizationPreset.from_dict)
        self.validate_presets()

    @property
    def studio_templates_root(self) -> Path | None:
        return None if self.studio_root is None else (self.studio_root / 'templates').resolve()

    @property
    def studio_presets_root(self) -> Path | None:
        return None if self.studio_root is None else (self.studio_root / 'presets').resolve()

    def reload(self) -> None:
        self.templates.reload()
        self.presets.reload()
        self.validate_presets()

    def validate_presets(self) -> None:
        for preset in self.presets.list():
            template = self.templates.get(preset.input_template_ref)
            preset.validate_against(template)
