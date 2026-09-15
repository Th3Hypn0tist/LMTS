from __future__ import annotations

import unittest

from lmts.dvs.model import InputTemplate, VisualizationPreset


class DVSTest(unittest.TestCase):
    def test_input_template_owns_string_number_boolean_typing(self) -> None:
        template = InputTemplate.from_dict({
            'format': 's3d.dvs.input-template',
            'version': '1.0',
            'id': 'typed',
            'source_format': 'example/1.0',
            'reader': 'json',
            'rows': 'records[*]',
            'columns': [
                {'name': 'id', 'selector': 'id', 'type': 'string'},
                {'name': 'number', 'selector': 'value', 'type': 'number'},
                {'name': 'flag', 'selector': 'flag', 'type': 'boolean'},
                {'name': 'nullable_number', 'selector': 'missing', 'type': 'number', 'nullable': True},
            ],
        })
        table = template.extract({
            'records': [{'id': 'a', 'value': '42.5', 'flag': 'true', 'missing': None}],
        })
        self.assertEqual(table.columns, ('id', 'number', 'flag', 'nullable_number'))
        self.assertEqual(table.column_types, ('string', 'number', 'boolean', 'number'))
        self.assertEqual(table.rows, (('a', 42.5, True, None),))

    def test_input_template_rejects_integer_type(self) -> None:
        with self.assertRaisesRegex(ValueError, 'InputColumn.type'):
            InputTemplate.from_dict({
                'format': 's3d.dvs.input-template',
                'version': '1.0',
                'id': 'integer-is-not-a-type',
                'source_format': 'example/1.0',
                'reader': 'json',
                'rows': 'records[*]',
                'columns': [{'name': 'value', 'selector': 'value', 'type': 'integer'}],
            })

    def test_input_template_rejects_unknown_column_semantics(self) -> None:
        with self.assertRaises(ValueError):
            InputTemplate.from_dict({
                'format': 's3d.dvs.input-template',
                'version': '1.0',
                'id': 'legacy-fallback',
                'source_format': 'example/1.0',
                'reader': 'json',
                'rows': 'records[*]',
                'columns': [
                    {'name': 'missing', 'selector': 'missing', 'type': 'string', 'on_missing': 'null'},
                ],
            })

    def test_missing_field_is_error(self) -> None:
        template = InputTemplate.from_dict({
            'format': 's3d.dvs.input-template',
            'version': '1.0',
            'id': 'strict',
            'source_format': 'example/1.0',
            'reader': 'json',
            'rows': 'records[*]',
            'columns': [{'name': 'required', 'selector': 'required', 'type': 'string'}],
        })
        with self.assertRaises(ValueError):
            template.extract({'records': [{}]})

    def test_scale_is_number_only_and_exposed_as_parameter(self) -> None:
        template = InputTemplate.from_dict({
            'format': 's3d.dvs.input-template',
            'version': '1.0',
            'id': 'scaled',
            'source_format': 'example/1.0',
            'reader': 'json',
            'rows': 'records[*]',
            'columns': [{
                'name': 'value',
                'selector': 'value',
                'type': 'number',
                'scale': {'low': 0.2, 'high': 5.9, 'power': 1.0},
            }],
        })
        table = template.extract({'records': [{'value': 1.4}]})
        self.assertAlmostEqual(table.rows[0][0], (1.4 - 0.2) / (5.9 - 0.2))
        self.assertEqual(
            table.parameters,
            {'scale.value': {'low': 0.2, 'high': 5.9, 'power': 1.0}},
        )

        with self.assertRaisesRegex(ValueError, 'requires type number'):
            InputTemplate.from_dict({
                'format': 's3d.dvs.input-template',
                'version': '1.0',
                'id': 'bad-scale',
                'source_format': 'example/1.0',
                'reader': 'json',
                'rows': 'records[*]',
                'columns': [{
                    'name': 'value',
                    'selector': 'value',
                    'type': 'string',
                    'scale': {'low': 0, 'high': 1, 'power': 1},
                }],
            })

    def test_find_typed_range_scans_before_scale_and_skips_nullable_null(self) -> None:
        template = InputTemplate.from_dict({
            'format': 's3d.dvs.input-template',
            'version': '1.0',
            'id': 'range',
            'source_format': 'example/1.0',
            'reader': 'json',
            'rows': 'records[*]',
            'columns': [{
                'name': 'value',
                'selector': 'value',
                'type': 'number',
                'nullable': True,
                'scale': {'low': 0, 'high': 100, 'power': 2},
            }],
        })
        self.assertEqual(
            template.find_typed_range({'records': [{'value': '3.5'}, {'value': None}, {'value': 9}]}, 'value'),
            (3.5, 9.0),
        )

    def test_visualization_preset_is_recursive_and_column_bound(self) -> None:
        template = InputTemplate.from_dict({
            'format': 's3d.dvs.input-template',
            'version': '1.0',
            'id': 'table',
            'source_format': 'example/1.0',
            'reader': 'json',
            'rows': 'records[*]',
            'columns': [
                {'name': 'a', 'selector': 'a', 'type': 'number'},
                {'name': 'b', 'selector': 'b', 'type': 'string'},
            ],
        })
        preset = VisualizationPreset.from_dict({
            'format': 's3d.dvs.visualization-preset',
            'version': '1.0',
            'id': 'recursive',
            'source_format': 'example/1.0',
            'input_template_ref': 'table',
            'generations': [{
                'id': 'g0',
                'primitive': 'box',
                'bindings': {
                    'position.x': {'column': 'a', 'interpretation': 'number'},
                },
                'children': [{
                    'id': 'g1',
                    'primitive': 'point',
                    'bindings': {
                        'position.x': {'column': 'b', 'interpretation': 'categorical-index'},
                    },
                }],
            }],
        })
        preset.validate_against(template)
        self.assertEqual(preset.generations[0].children[0].primitive, 'point')

    def test_visualization_preset_rejects_unknown_column(self) -> None:
        template = InputTemplate.from_dict({
            'format': 's3d.dvs.input-template',
            'version': '1.0',
            'id': 'table',
            'source_format': 'example/1.0',
            'reader': 'json',
            'rows': 'records[*]',
            'columns': [{'name': 'a', 'selector': 'a', 'type': 'number'}],
        })
        preset = VisualizationPreset.from_dict({
            'format': 's3d.dvs.visualization-preset',
            'version': '1.0',
            'id': 'bad',
            'source_format': 'example/1.0',
            'input_template_ref': 'table',
            'generations': [{
                'id': 'g0',
                'primitive': 'sphere',
                'bindings': {
                    'scale.x': {'column': 'missing', 'interpretation': 'number'},
                },
            }],
        })
        with self.assertRaises(ValueError):
            preset.validate_against(template)


if __name__ == '__main__':
    unittest.main()
