from __future__ import annotations

from collections.abc import Sequence
from math import isfinite
from typing import Any

from .model import InputTemplate, VisualBinding, VisualizationGeneration, VisualizationPreset


_NULL = object()


def _strict_transform(transform: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = sorted(set(transform) - allowed)
    if unknown:
        raise ValueError(f'{label} contains unsupported transform field(s): {", ".join(unknown)}')


def _finite_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'{label} must be numeric')
    result = float(value)
    if not isfinite(result):
        raise ValueError(f'{label} must be finite')
    return result


def _pair(value: Any, label: str) -> tuple[float, float]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f'{label} must be a two-value array')
    return (_finite_float(value[0], f'{label}[0]'), _finite_float(value[1], f'{label}[1]'))


def _categorical_maps(rows: Sequence[dict[str, Any]]) -> dict[str, dict[Any, int]]:
    result: dict[str, dict[Any, int]] = {}
    if not rows:
        return result
    for column in rows[0]:
        order: dict[Any, int] = {}
        for row in rows:
            value = row[column]
            if value not in order:
                order[value] = len(order)
        result[column] = order
    return result


def _interpret_categorical_index(
    raw: Any,
    binding: VisualBinding,
    category_map: dict[Any, int],
    label: str,
) -> float:
    if raw is None:
        raise ValueError(f'{label} does not allow null')
    _strict_transform(binding.transform, {'spacing', 'offset', 'order'}, label)
    spacing = _finite_float(binding.transform.get('spacing', 1.0), f'{label}.spacing')
    offset = _finite_float(binding.transform.get('offset', 0.0), f'{label}.offset')
    order = binding.transform.get('order')
    if order is not None:
        if not isinstance(order, list):
            raise ValueError(f'{label}.order must be an array')
        if len(set(order)) != len(order):
            raise ValueError(f'{label}.order must not contain duplicates')
        try:
            index = order.index(raw)
        except ValueError as exc:
            raise ValueError(f'{label} has no explicit category order entry for {raw!r}') from exc
    else:
        try:
            index = category_map[raw]
        except KeyError as exc:
            raise ValueError(f'{label} has no categorical index for {raw!r}') from exc
    return offset + index * spacing


def _interpret_number(raw: Any, binding: VisualBinding, label: str, *, nullable: bool) -> float | object:
    _strict_transform(binding.transform, {'domain', 'range', 'clamp', 'null'}, label)
    if raw is None:
        if not nullable:
            raise ValueError(f'{label} does not allow null')
        null_policy = binding.transform.get('null')
        if null_policy == 'not-rendered':
            return _NULL
        if null_policy == 'error' or null_policy is None:
            raise ValueError(f'{label} received null without a renderable value')
        raise ValueError(f'{label}.null unsupported policy: {null_policy!r}')

    value = _finite_float(raw, label)
    has_domain = 'domain' in binding.transform
    has_range = 'range' in binding.transform
    if has_domain != has_range:
        raise ValueError(f'{label} requires domain and range together')
    if not has_domain:
        return value

    domain_min, domain_max = _pair(binding.transform['domain'], f'{label}.domain')
    range_min, range_max = _pair(binding.transform['range'], f'{label}.range')
    if domain_min == domain_max:
        raise ValueError(f'{label}.domain must have non-zero span')
    normalized = (value - domain_min) / (domain_max - domain_min)
    clamp = binding.transform.get('clamp', False)
    if not isinstance(clamp, bool):
        raise ValueError(f'{label}.clamp must be boolean')
    if clamp:
        normalized = min(1.0, max(0.0, normalized))
    return range_min + (range_max - range_min) * normalized


def _interpret_category_channel(raw: Any, binding: VisualBinding, label: str) -> float:
    if raw is None:
        raise ValueError(f'{label} does not allow null')
    _strict_transform(binding.transform, {'map'}, label)
    mapping = binding.transform.get('map')
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError(f'{label}.map must be a non-empty object')
    key = str(raw).lower() if isinstance(raw, bool) else str(raw)
    if key not in mapping:
        raise ValueError(f'{label}.map has no value for category {raw!r}')
    return _finite_float(mapping[key], f'{label}.map[{key!r}]')


def interpret_binding(
    raw: Any,
    binding: VisualBinding,
    *,
    category_map: dict[Any, int],
    label: str,
) -> float | object:
    interpretation = binding.interpretation
    if interpretation == 'categorical-index':
        return _interpret_categorical_index(raw, binding, category_map, label)
    if interpretation == 'number':
        return _interpret_number(raw, binding, label, nullable=False)
    if interpretation == 'number-or-null':
        return _interpret_number(raw, binding, label, nullable=True)
    if interpretation == 'category-channel':
        return _interpret_category_channel(raw, binding, label)
    raise ValueError(f'{label} unsupported interpretation: {interpretation!r}')


def _rows_from_template(
    source: Any,
    template: InputTemplate,
) -> tuple[list[dict[str, Any]], list[int], dict[str, Any]]:
    extracted = template.extract(source)
    rows = [dict(zip(extracted.columns, row, strict=True)) for row in extracted.rows]
    return rows, list(range(len(rows))), dict(extracted.parameters)


def _group_rows(
    generation: VisualizationGeneration,
    rows: Sequence[dict[str, Any]],
    source_indices: Sequence[int],
) -> list[tuple[dict[str, Any], list[dict[str, Any]], list[int]]]:
    if len(rows) != len(source_indices):
        raise ValueError('DVS runtime row/index cardinality mismatch')
    if not generation.group_by:
        return [({}, [row], [source_indices[index]]) for index, row in enumerate(rows)]

    groups: dict[tuple[Any, ...], tuple[list[dict[str, Any]], list[int]]] = {}
    for index, row in enumerate(rows):
        key = tuple(row[column] for column in generation.group_by)
        group_rows, group_indices = groups.setdefault(key, ([], []))
        group_rows.append(row)
        group_indices.append(source_indices[index])
    return [
        (
            dict(zip(generation.group_by, key, strict=True)),
            group_rows,
            group_indices,
        )
        for key, (group_rows, group_indices) in groups.items()
    ]


def _constant_group_value(rows: Sequence[dict[str, Any]], column: str, label: str) -> Any:
    values = {row[column] for row in rows}
    if len(values) != 1:
        raise ValueError(
            f'{label} resolves to multiple values inside one generation group; '
            'DVS does not apply implicit aggregation'
        )
    return next(iter(values))


def _project_generation(
    generation: VisualizationGeneration,
    rows: Sequence[dict[str, Any]],
    source_indices: Sequence[int],
    categorical_maps: dict[str, dict[Any, int]],
    input_parameters: dict[str, Any],
) -> dict[str, Any]:
    projected_groups: list[dict[str, Any]] = []
    bound_parameters = {
        local_name: input_parameters[parameter_ref]
        for local_name, parameter_ref in generation.parameters.items()
    }
    for key, group_rows, group_indices in _group_rows(generation, rows, source_indices):
        channels: dict[str, float] = {}
        visible = True
        for channel, binding in generation.bindings.items():
            label = f'generation {generation.id!r} channel {channel!r}'
            raw = _constant_group_value(group_rows, binding.column, label)
            interpreted = interpret_binding(
                raw,
                binding,
                category_map=categorical_maps[binding.column],
                label=label,
            )
            if interpreted is _NULL:
                visible = False
                continue
            channels[channel] = float(interpreted)

        children = [
            _project_generation(child, group_rows, group_indices, categorical_maps, input_parameters)
            for child in generation.children
        ]
        projected_groups.append({
            'key': key,
            'primitive': generation.primitive,
            'visible': visible,
            'channels': channels,
            'parameters': dict(bound_parameters),
            'source_rows': list(group_indices),
            'children': children,
        })
    return {
        'id': generation.id,
        'groups': projected_groups,
    }


def project_visualization(source: Any, template: InputTemplate, preset: VisualizationPreset) -> dict[str, Any]:
    preset.validate_against(template)
    rows, source_indices, input_parameters = _rows_from_template(source, template)
    categorical_maps = _categorical_maps(rows)
    return {
        'format': 's3d.dvs.visual-plan',
        'version': '1.0',
        'source_format': template.source_format,
        'input_template_id': template.id,
        'visualization_preset_id': preset.id,
        'row_count': len(rows),
        'parameters': dict(input_parameters),
        'generations': [
            _project_generation(generation, rows, source_indices, categorical_maps, input_parameters)
            for generation in preset.generations
        ],
    }
