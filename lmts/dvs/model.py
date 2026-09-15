from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any


DVS_INPUT_TEMPLATE_FORMAT = 's3d.dvs.input-template'
DVS_VISUALIZATION_PRESET_FORMAT = 's3d.dvs.visualization-preset'
DVS_FORMAT_VERSION = '1.0'
INPUT_COLUMN_TYPES = frozenset({'string', 'number', 'boolean'})

_SEGMENT_RE = re.compile(r'^(?P<name>[^.\[\]]+)(?P<wildcard>\[\*\])?$')


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{label} must be a non-empty string')
    return value.strip()


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f'{label} must be an object')
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{label} must be a finite number')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f'{label} must be a finite number')
    return result


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


def _parse_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f'{label} must be a string')
    return value


def _parse_number(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a finite number or numeric string')
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValueError(f'{label} must be a finite number or numeric string')
        try:
            result = float(raw)
        except ValueError as exc:
            raise ValueError(f'{label} must be a finite number or numeric string') from exc
    else:
        raise ValueError(f'{label} must be a finite number or numeric string')
    if not math.isfinite(result):
        raise ValueError(f'{label} must be finite')
    return result


def _parse_boolean(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        raw = value.strip().casefold()
        if raw == 'true':
            return True
        if raw == 'false':
            return False
    raise ValueError(f'{label} must be boolean or the string true/false')


def parse_input_value(value: Any, value_type: str, label: str) -> Any:
    if value_type == 'string':
        return _parse_string(value, label)
    if value_type == 'number':
        return _parse_number(value, label)
    if value_type == 'boolean':
        return _parse_boolean(value, label)
    raise ValueError(f'{label} has unsupported Input Column type {value_type!r}')


@dataclass(frozen=True, slots=True)
class InputScale:
    low: float
    high: float
    power: float = 1.0

    def __post_init__(self) -> None:
        low = _number(self.low, 'InputScale.low')
        high = _number(self.high, 'InputScale.high')
        power = _number(self.power, 'InputScale.power')
        if high <= low:
            raise ValueError('InputScale.high must be greater than InputScale.low')
        if power <= 0:
            raise ValueError('InputScale.power must be greater than zero')
        object.__setattr__(self, 'low', low)
        object.__setattr__(self, 'high', high)
        object.__setattr__(self, 'power', power)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'InputScale':
        payload = _object(payload, 'InputScale')
        _require_keys(payload, {'low', 'high'}, {'low', 'high', 'power'}, 'InputScale')
        return cls(
            low=_number(payload['low'], 'InputScale.low'),
            high=_number(payload['high'], 'InputScale.high'),
            power=_number(payload.get('power', 1.0), 'InputScale.power'),
        )

    def apply(self, value: float) -> float:
        input_value = _number(value, 'scaled input')
        normalized = (input_value - self.low) / (self.high - self.low)
        if normalized < 0 and not self.power.is_integer():
            raise ValueError('scaled input below low cannot use a non-integer power')
        output = normalized ** self.power
        if isinstance(output, complex) or not math.isfinite(float(output)):
            raise ValueError('scaled output must be a finite real number')
        return float(output)

    def to_dict(self) -> dict[str, float]:
        return {'low': self.low, 'high': self.high, 'power': self.power}


@dataclass(frozen=True, slots=True)
class InputColumn:
    name: str
    selector: str
    type: str
    nullable: bool = False
    scale: InputScale | None = None

    def __post_init__(self) -> None:
        if self.type not in INPUT_COLUMN_TYPES:
            raise ValueError(f'InputColumn.type must be one of: {", ".join(sorted(INPUT_COLUMN_TYPES))}')
        if not isinstance(self.nullable, bool):
            raise ValueError('InputColumn.nullable must be boolean')
        if self.scale is not None and self.type != 'number':
            raise ValueError('InputColumn.scale requires type number')

    @property
    def scale_parameter_id(self) -> str | None:
        return None if self.scale is None else f'scale.{self.name}'

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'InputColumn':
        payload = _object(payload, 'InputColumn')
        _require_keys(
            payload,
            {'name', 'selector', 'type'},
            {'name', 'selector', 'type', 'nullable', 'scale'},
            'InputColumn',
        )
        raw_scale = payload.get('scale')
        nullable = payload.get('nullable', False)
        if not isinstance(nullable, bool):
            raise ValueError('InputColumn.nullable must be boolean')
        return cls(
            name=_text(payload['name'], 'InputColumn.name'),
            selector=_text(payload['selector'], 'InputColumn.selector'),
            type=_text(payload['type'], 'InputColumn.type'),
            nullable=nullable,
            scale=None if raw_scale is None else InputScale.from_dict(raw_scale),
        )

    def parse(self, value: Any) -> Any:
        if value is None:
            if self.nullable:
                return None
            raise ValueError(f'InputColumn {self.name!r} does not allow null')
        return parse_input_value(value, self.type, f'InputColumn {self.name!r}')

    def project(self, value: Any) -> Any:
        typed_value = self.parse(value)
        if typed_value is None:
            return None
        return self.scale.apply(typed_value) if self.scale is not None else typed_value

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            'name': self.name,
            'selector': self.selector,
            'type': self.type,
        }
        if self.nullable:
            result['nullable'] = True
        if self.scale is not None:
            result['scale'] = self.scale.to_dict()
        return result


@dataclass(frozen=True, slots=True)
class _InputTable:
    columns: tuple[str, ...]
    column_types: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    parameters: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.columns or any(not isinstance(value, str) or not value for value in self.columns):
            raise ValueError('runtime input table requires non-empty string column names')
        if len(set(self.columns)) != len(self.columns):
            raise ValueError('runtime input table column names must be unique')
        if len(self.column_types) != len(self.columns):
            raise ValueError('runtime input table column type width must match columns')
        if any(value not in INPUT_COLUMN_TYPES for value in self.column_types):
            raise ValueError('runtime input table contains unsupported column type')
        width = len(self.columns)
        for row in self.rows:
            if len(row) != width:
                raise ValueError('runtime input table row width must match columns')
        for name in self.parameters:
            _text(name, 'runtime input parameter name')

    def to_dict(self) -> dict[str, Any]:
        return {
            'columns': list(self.columns),
            'column_types': list(self.column_types),
            'rows': [list(row) for row in self.rows],
            'parameters': dict(self.parameters),
        }


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

    def column(self, column_name: str) -> InputColumn:
        name = _text(column_name, 'Input Template column name')
        for column in self.columns:
            if column.name == name:
                return column
        raise KeyError(f'InputTemplate {self.id!r} has no column {name!r}')

    def find_typed_range(self, source: Any, column_name: str) -> tuple[float, float]:
        column = self.column(column_name)
        if column.type != 'number':
            raise ValueError(f'InputTemplate range scan requires numeric column, got {column.type!r}')
        rows = select_many(source, self.rows_selector)
        if not rows:
            raise ValueError(f'InputTemplate {self.id!r} has no source rows to scan')
        values: list[float] = []
        for row_index, row in enumerate(rows):
            try:
                raw_value = select_one(row, column.selector)
                typed_value = column.parse(raw_value)
                if typed_value is not None:
                    values.append(float(typed_value))
            except (KeyError, ValueError) as exc:
                raise ValueError(
                    f'InputTemplate {self.id!r} row {row_index} column {column.name!r}: {exc}'
                ) from exc
        if not values:
            raise ValueError(f'InputTemplate {self.id!r} column {column.name!r} has no numeric values to scan')
        return min(values), max(values)

    def extract(self, source: Any) -> _InputTable:
        rows = select_many(source, self.rows_selector)
        projected: list[tuple[Any, ...]] = []
        for row_index, row in enumerate(rows):
            values: list[Any] = []
            for column in self.columns:
                try:
                    raw_value = select_one(row, column.selector)
                    values.append(column.project(raw_value))
                except (KeyError, ValueError) as exc:
                    raise ValueError(
                        f'InputTemplate {self.id!r} row {row_index} column {column.name!r}: {exc}'
                    ) from exc
            projected.append(tuple(values))
        parameters = {
            column.scale_parameter_id: column.scale.to_dict()
            for column in self.columns
            if column.scale is not None and column.scale_parameter_id is not None
        }
        return _InputTable(
            tuple(column.name for column in self.columns),
            tuple(column.type for column in self.columns),
            tuple(projected),
            parameters,
        )


@dataclass(frozen=True, slots=True)
class VisualBinding:
    column: str
    interpretation: str
    transform: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'VisualBinding':
        payload = _object(payload, 'VisualBinding')
        _require_keys(
            payload,
            {'column', 'interpretation'},
            {'column', 'interpretation', 'transform'},
            'VisualBinding',
        )
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
    parameters: dict[str, str] = field(default_factory=dict)
    children: tuple['VisualizationGeneration', ...] = ()

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> 'VisualizationGeneration':
        payload = _object(payload, 'VisualizationGeneration')
        _require_keys(
            payload,
            {'id', 'primitive', 'bindings'},
            {'id', 'primitive', 'group_by', 'bindings', 'parameters', 'children'},
            'VisualizationGeneration',
        )
        raw_group_by = payload.get('group_by', [])
        if not isinstance(raw_group_by, list) or any(not isinstance(item, str) or not item for item in raw_group_by):
            raise ValueError('VisualizationGeneration.group_by must be a string array')
        raw_bindings = payload['bindings']
        if not isinstance(raw_bindings, dict):
            raise ValueError('VisualizationGeneration.bindings must be an object')
        raw_parameters = payload.get('parameters', {})
        if not isinstance(raw_parameters, dict):
            raise ValueError('VisualizationGeneration.parameters must be an object')
        raw_children = payload.get('children', [])
        if not isinstance(raw_children, list):
            raise ValueError('VisualizationGeneration.children must be an array')
        bindings: dict[str, VisualBinding] = {}
        for channel, binding in raw_bindings.items():
            bindings[_text(channel, 'visual channel')] = VisualBinding.from_dict(binding)
        parameters: dict[str, str] = {}
        for local_name, parameter_ref in raw_parameters.items():
            parameters[_text(local_name, 'generation parameter name')] = _text(
                parameter_ref,
                'generation parameter reference',
            )
        return cls(
            id=_text(payload['id'], 'VisualizationGeneration.id'),
            primitive=_text(payload['primitive'], 'VisualizationGeneration.primitive'),
            group_by=tuple(raw_group_by),
            bindings=bindings,
            parameters=parameters,
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
        if self.parameters:
            result['parameters'] = dict(self.parameters)
        if self.children:
            result['children'] = [child.to_dict() for child in self.children]
        return result

    def validate_sources(self, available_columns: set[str], available_parameters: set[str]) -> None:
        unknown_groups = sorted(set(self.group_by) - available_columns)
        if unknown_groups:
            raise ValueError(f'generation {self.id!r} group_by references unknown columns: {", ".join(unknown_groups)}')
        unknown_bindings = sorted({binding.column for binding in self.bindings.values()} - available_columns)
        if unknown_bindings:
            raise ValueError(f'generation {self.id!r} bindings reference unknown columns: {", ".join(unknown_bindings)}')
        unknown_parameters = sorted(set(self.parameters.values()) - available_parameters)
        if unknown_parameters:
            raise ValueError(
                f'generation {self.id!r} parameters reference unknown input parameters: {", ".join(unknown_parameters)}'
            )
        child_ids = [child.id for child in self.children]
        if len(set(child_ids)) != len(child_ids):
            raise ValueError(f'generation {self.id!r} child ids must be unique')
        for child in self.children:
            child.validate_sources(available_columns, available_parameters)


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
        available_columns = {column.name for column in template.columns}
        available_parameters = {
            column.scale_parameter_id
            for column in template.columns
            if column.scale_parameter_id is not None
        }
        for generation in self.generations:
            generation.validate_sources(available_columns, available_parameters)

    def to_dict(self) -> dict[str, Any]:
        return {
            'format': DVS_VISUALIZATION_PRESET_FORMAT,
            'version': DVS_FORMAT_VERSION,
            'id': self.id,
            'source_format': self.source_format,
            'input_template_ref': self.input_template_ref,
            'generations': [generation.to_dict() for generation in self.generations],
        }
