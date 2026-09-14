from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


DVS_INPUT_TEMPLATE_FORMAT = 's3d.dvs.input-template'
DVS_VISUALIZATION_PRESET_FORMAT = 's3d.dvs.visualization-preset'
DVS_FORMAT_VERSION = '1.0'

_SEGMENT_RE = re.compile(r'^(?P<name>[^.\[\]]+)(?P<wildcard>\[\*\])?$')


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a non-empty string')
    return value.strip()


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object')
    return value


def _require_keys(payload: dict[str, Any], required: set[str], allowed: set[str], label: str) -> None:
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f'{label} missing required field(s): {", ".join(missing)}')
    unknown = sorted(payload.keys() - allowed)
    if unknown:
        raise ValueError(f'{label} contains unknown field(s): {", ".join(unknown)}')


def _selector_parts(selector: str) -> tuple[str, ...]:
    raw = _text(selector, 'selector')
    if raw == '$':
        return ()
    if raw.startswith('$.'):
        raw = raw[2:]
    parts = tuple(raw.split('.'))
    for part in parts:
        if _SEGMENT_RE.fullmatch(part) is None:
            raise ValueError(f'invalid selector segment: {part!r}')
    return parts


def select_many(source: Any, selector: str) -> list[Any]:
    current = [source]
    for part in _selector_parts(selector):
        match = _SEGMENT_RE.fullmatch(part)
        assert match is not None
        name = match.group('name')
        wildcard = bool(match.group('wildcard'))
        next_values: list[Any] = []
        for item in current:
            if not isinstance(item, dict) or name not in item:
                raise KeyError(f'selector {selector!r} missing field {name!r}')
            value = item[name]
            if wildcard:
                if not isinstance(value, list):
                    raise TypeError(f'selector {selector!r} expected {name!r} to be an array')
                next_values.extend(value)
            else:
                next_values.append(value)
        current = next_values
    return current


def select_one(source: Any, selector: str) -> Any:
    values = select_many(source, selector)
    if len(values) != 1:
        raise ValueError(f'cell selector {selector!r} resolved to {len(values)} values; expected exactly one')
    return values[0]


def stringify_cell(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


@dataclass(frozen=True, slots=True)
class InputColumn:
    name: str
    selector: str
    on_missing: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'InputColumn':
        payload = _object(payload, 'InputColumn')
        _require_keys(payload, {'name', 'selector'}, {'name', 'selector', 'on_missing'}, 'InputColumn')
        on_missing = payload.get('on_missing')
        if on_missing is not None and not isinstance(on_missing, str):
            raise ValueError('InputColumn.on_missing must be a string when present')
        return cls(
            name=_text(payload['name'], 'InputColumn.name'),
            selector=_text(payload['selector'], 'InputColumn.selector'),
            on_missing=on_missing,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {'name': self.name, 'selector': self.selector}
        if self.on_missing is not None:
            result['on_missing'] = self.on_missing
        return result


@dataclass(frozen=True, slots=True)
class GenericStringTable:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]

    def __post_init__(self) -> None:
        if not self.columns or any(not isinstance(value, str) or not value for value in self.columns):
            raise ValueError('GenericStringTable requires non-empty string column names')
        if len(set(self.columns)) != len(self.columns):
            raise ValueError('GenericStringTable column names must be unique')
        width = len(self.columns)
        for row in self.rows:
            if len(row) != width:
                raise ValueError('GenericStringTable row width must match columns')
            if any(not isinstance(value, str) for value in row):
                raise ValueError('GenericStringTable cells must be strings')

    def to_dict(self) -> dict[str, Any]:
        return {'columns': list(self.columns), 'rows': [list(row) for row in self.rows]}


@dataclass(frozen=True, slots=True)
class InputTemplate:
    id: str
    source_format: str
    reader: str
    rows_selector: str
    columns: tuple[InputColumn, ...]

    def __post_init__(self) -> None:
        _text(self.id, 'InputTemplate.id')
        _text(self.source_format, 'InputTemplate.source_format')
        _text(self.reader, 'InputTemplate.reader')
        _text(self.rows_selector, 'InputTemplate.rows')
        if not self.columns:
            raise ValueError('InputTemplate requires at least one column')
        names = [column.name for column in self.columns]
        if len(set(names)) != len(names):
            raise ValueError('InputTemplate column names must be unique')
        if self.reader != 'json':
            raise ValueError(f'unsupported InputTemplate reader: {self.reader!r}')

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'InputTemplate':
        payload = _object(payload, 'InputTemplate')
        required = {'format', 'version', 'id', 'source_format', 'reader', 'rows', 'columns'}
        _require_keys(payload, required, required, 'InputTemplate')
        if payload['format'] != DVS_INPUT_TEMPLATE_FORMAT:
            raise ValueError(f'InputTemplate.format must be {DVS_INPUT_TEMPLATE_FORMAT!r}')
        if payload['version'] != DVS_FORMAT_VERSION:
            raise ValueError(f'InputTemplate.version must be {DVS_FORMAT_VERSION!r}')
        raw_columns = payload['columns']
        if not isinstance(raw_columns, list):
            raise ValueError('InputTemplate.columns must be an array')
        return cls(
            id=_text(payload['id'], 'InputTemplate.id'),
            source_format=_text(payload['source_format'], 'InputTemplate.source_format'),
            reader=_text(payload['reader'], 'InputTemplate.reader'),
            rows_selector=_text(payload['rows'], 'InputTemplate.rows'),
            columns=tuple(InputColumn.from_dict(item) for item in raw_columns),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'format': DVS_INPUT_TEMPLATE_FORMAT,
            'version': DVS_FORMAT_VERSION,
            'id': self.id,
            'source_format': self.source_format,
            'reader': self.reader,
            'rows': self.rows_selector,
            'columns': [column.to_dict() for column in self.columns],
        }

    def extract(self, source: Any) -> GenericStringTable:
        rows = select_many(source, self.rows_selector)
        projected: list[tuple[str, ...]] = []
        for row_index, row in enumerate(rows):
            values: list[str] = []
            for column in self.columns:
                try:
                    raw_value = select_one(row, column.selector)
                    values.append(stringify_cell(raw_value))
                except KeyError as exc:
                    if column.on_missing is None:
                        raise ValueError(
                            f'InputTemplate {self.id!r} row {row_index} column {column.name!r}: {exc}'
                        ) from exc
                    values.append(column.on_missing)
            projected.append(tuple(values))
        return GenericStringTable(tuple(column.name for column in self.columns), tuple(projected))


@dataclass(frozen=True, slots=True)
class VisualBinding:
    column: str
    interpretation: str
    transform: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'VisualBinding':
        payload = _object(payload, 'VisualBinding')
        _require_keys(payload, {'column', 'interpretation'}, {'column', 'interpretation', 'transform'}, 'VisualBinding')
        transform = payload.get('transform', {})
        if not isinstance(transform, dict):
            raise ValueError('VisualBinding.transform must be an object')
        return cls(
            column=_text(payload['column'], 'VisualBinding.column'),
            interpretation=_text(payload['interpretation'], 'VisualBinding.interpretation'),
            transform=dict(transform),
        )

    def to_dict(self) -> dict[str, Any]:
        result = {'column': self.column, 'interpretation': self.interpretation}
        if self.transform:
            result['transform'] = dict(self.transform)
        return result


@dataclass(frozen=True, slots=True)
class VisualizationGeneration:
    id: str
    primitive: str
    group_by: tuple[str, ...] = ()
    bindings: dict[str, VisualBinding] = field(default_factory=dict)
    children: tuple['VisualizationGeneration', ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'VisualizationGeneration':
        payload = _object(payload, 'VisualizationGeneration')
        _require_keys(
            payload,
            {'id', 'primitive', 'bindings'},
            {'id', 'primitive', 'group_by', 'bindings', 'children'},
            'VisualizationGeneration',
        )
        raw_group_by = payload.get('group_by', [])
        if not isinstance(raw_group_by, list) or any(not isinstance(item, str) or not item for item in raw_group_by):
            raise ValueError('VisualizationGeneration.group_by must be a string array')
        raw_bindings = payload['bindings']
        if not isinstance(raw_bindings, dict):
            raise ValueError('VisualizationGeneration.bindings must be an object')
        raw_children = payload.get('children', [])
        if not isinstance(raw_children, list):
            raise ValueError('VisualizationGeneration.children must be an array')
        bindings: dict[str, VisualBinding] = {}
        for channel, binding in raw_bindings.items():
            channel_name = _text(channel, 'visual channel')
            bindings[channel_name] = VisualBinding.from_dict(binding)
        return cls(
            id=_text(payload['id'], 'VisualizationGeneration.id'),
            primitive=_text(payload['primitive'], 'VisualizationGeneration.primitive'),
            group_by=tuple(raw_group_by),
            bindings=bindings,
            children=tuple(cls.from_dict(item) for item in raw_children),
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            'id': self.id,
            'primitive': self.primitive,
            'bindings': {channel: binding.to_dict() for channel, binding in self.bindings.items()},
        }
        if self.group_by:
            result['group_by'] = list(self.group_by)
        if self.children:
            result['children'] = [child.to_dict() for child in self.children]
        return result

    def validate_columns(self, available: set[str]) -> None:
        unknown_groups = sorted(set(self.group_by) - available)
        if unknown_groups:
            raise ValueError(f'generation {self.id!r} group_by references unknown columns: {", ".join(unknown_groups)}')
        unknown_bindings = sorted({binding.column for binding in self.bindings.values()} - available)
        if unknown_bindings:
            raise ValueError(f'generation {self.id!r} bindings reference unknown columns: {", ".join(unknown_bindings)}')
        child_ids = [child.id for child in self.children]
        if len(set(child_ids)) != len(child_ids):
            raise ValueError(f'generation {self.id!r} child ids must be unique')
        for child in self.children:
            child.validate_columns(available)


@dataclass(frozen=True, slots=True)
class VisualizationPreset:
    id: str
    source_format: str
    input_template_ref: str
    generations: tuple[VisualizationGeneration, ...]

    def __post_init__(self) -> None:
        _text(self.id, 'VisualizationPreset.id')
        _text(self.source_format, 'VisualizationPreset.source_format')
        _text(self.input_template_ref, 'VisualizationPreset.input_template_ref')
        if not self.generations:
            raise ValueError('VisualizationPreset requires at least one generation')
        ids = [generation.id for generation in self.generations]
        if len(set(ids)) != len(ids):
            raise ValueError('VisualizationPreset top-level generation ids must be unique')

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'VisualizationPreset':
        payload = _object(payload, 'VisualizationPreset')
        required = {'format', 'version', 'id', 'source_format', 'input_template_ref', 'generations'}
        _require_keys(payload, required, required, 'VisualizationPreset')
        if payload['format'] != DVS_VISUALIZATION_PRESET_FORMAT:
            raise ValueError(f'VisualizationPreset.format must be {DVS_VISUALIZATION_PRESET_FORMAT!r}')
        if payload['version'] != DVS_FORMAT_VERSION:
            raise ValueError(f'VisualizationPreset.version must be {DVS_FORMAT_VERSION!r}')
        raw_generations = payload['generations']
        if not isinstance(raw_generations, list):
            raise ValueError('VisualizationPreset.generations must be an array')
        return cls(
            id=_text(payload['id'], 'VisualizationPreset.id'),
            source_format=_text(payload['source_format'], 'VisualizationPreset.source_format'),
            input_template_ref=_text(payload['input_template_ref'], 'VisualizationPreset.input_template_ref'),
            generations=tuple(VisualizationGeneration.from_dict(item) for item in raw_generations),
        )

    def validate_against(self, template: InputTemplate) -> None:
        if self.source_format != template.source_format:
            raise ValueError(
                f'VisualizationPreset source_format {self.source_format!r} does not match InputTemplate {template.source_format!r}'
            )
        if self.input_template_ref != template.id:
            raise ValueError(
                f'VisualizationPreset input_template_ref {self.input_template_ref!r} does not match {template.id!r}'
            )
        available = {column.name for column in template.columns}
        for generation in self.generations:
            generation.validate_columns(available)

    def to_dict(self) -> dict[str, Any]:
        return {
            'format': DVS_VISUALIZATION_PRESET_FORMAT,
            'version': DVS_FORMAT_VERSION,
            'id': self.id,
            'source_format': self.source_format,
            'input_template_ref': self.input_template_ref,
            'generations': [generation.to_dict() for generation in self.generations],
        }
