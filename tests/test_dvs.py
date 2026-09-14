from __future__ import annotations

import unittest

from lmts.dvs.model import InputTemplate, VisualizationPreset


class DVSTest(unittest.TestCase):
    def test_input_template_projects_every_cell_to_string(self) -> None:
        template = InputTemplate.from_dict({
            'format': 's3d.dvs.input-template',
            'version': '1.0',
            'id': 'example',
            'source_format': 'example/1.0',
            'reader': 'json',
            'rows': 'records[*]',
            'columns': [
                {'name': 'id', 'selector': 'id'},
                {'name': 'number', 'selector': 'value'},
                {'name': 'flag', 'selector': 'flag'},
                {'name': 'explicit_null', 'selector': 'missing'},
            ],
        })
        table = template.extract({'records': [{'id': 'a', 'value': 42, 'flag': True, 'missing': None}]})
        self.assertEqual(table.columns, ('id', 'number', 'flag', 'explicit_null'))
        self.assertEqual(table.rows, (('a', '42', 'true', 'null'),))
        self.assertTrue(all(isinstance(cell, str) for row in table.rows for cell in row))

    def test_input_template_rejects_on_missing_semantics(self) -> None:
        with self.assertRaises(ValueError):
            InputTemplate.from_dict({
                'format': 's3d.dvs.input-template',
                'version': '1.0',
                'id': 'legacy-fallback',
                'source_format': 'example/1.0',
                'reader': 'json',
                'rows': 'records[*]',
                'columns': [
                    {'name': 'missing', 'selector': 'missing', 'on_missing': 'null'},
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
            'columns': [{'name': 'required', 'selector': 'required'}],
        })
        with self.assertRaises(ValueError):
            template.extract({'records': [{}]})

    def test_visualization_preset_is_recursive_and_column_bound(self) -> None:
        template = InputTemplate.from_dict({
            'format': 's3d.dvs.input-template',
            'version': '1.0',
            'id': 'table',
            'source_format': 'example/1.0',
            'reader': 'json',
            'rows': 'records[*]',
            'columns': [
                {'name': 'a', 'selector': 'a'},
                {'name': 'b', 'selector': 'b'},
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
                        'color': {'column': 'b', 'interpretation': 'category'},
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
            'columns': [{'name': 'a', 'selector': 'a'}],
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
