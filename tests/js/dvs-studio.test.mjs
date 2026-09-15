import test from 'node:test';
import assert from 'node:assert/strict';

import {
  compatiblePresets,
  definitionDocument,
  encodeDefinitionId,
  newDefinition,
  studioApi,
  studioCollection,
  studioDraftApi,
} from '../../lmts/dvs/static/dvs.js';


test('Studio selects the correct registry collection', () => {
  const templates = [{ id: 'template-a' }];
  const presets = [{ id: 'preset-a' }];
  assert.equal(studioCollection('input-template', templates, presets), templates);
  assert.equal(studioCollection('visualization-preset', templates, presets), presets);
  assert.throws(() => studioCollection('unknown', templates, presets), /Unsupported Studio definition type/);
});


test('Studio canonical skeletons use formal DVS contracts', () => {
  const template = newDefinition('input-template');
  assert.equal(template.format, 's3d.dvs.input-template');
  assert.equal(template.version, '1.0');
  assert.equal(template.reader, 'json');
  assert.deepEqual(template.columns, [{ name: 'value', selector: 'value' }]);

  const preset = newDefinition('visualization-preset');
  assert.equal(preset.format, 's3d.dvs.visualization-preset');
  assert.equal(preset.version, '1.0');
  assert.equal(preset.input_template_ref, 'example.template');
  assert.equal(preset.generations[0].primitive, 'box');
  assert.deepEqual(
    preset.generations[0].bindings['scale.y'],
    { column: 'value', interpretation: 'number' },
  );
});


test('Studio API paths keep create and update namespaces explicit', () => {
  assert.equal(studioApi('input-template'), '/api/studio/input-templates');
  assert.equal(studioApi('visualization-preset'), '/api/studio/visualization-presets');
  assert.throws(() => studioApi('unknown'), /Unsupported Studio definition type/);
});


test('Studio draft API paths keep validation and preview non-persistent', () => {
  assert.equal(
    studioDraftApi('input-template', 'validate'),
    '/api/studio/validate/input-template',
  );
  assert.equal(
    studioDraftApi('input-template', 'preview'),
    '/api/studio/preview/input-template',
  );
  assert.equal(
    studioDraftApi('visualization-preset', 'validate'),
    '/api/studio/validate/visualization-preset',
  );
  assert.equal(
    studioDraftApi('visualization-preset', 'preview'),
    '/api/studio/preview/visualization-preset',
  );
  assert.throws(
    () => studioDraftApi('input-template', 'persist'),
    /Unsupported Studio draft operation/,
  );
  assert.throws(
    () => studioDraftApi('unknown', 'validate'),
    /Unsupported Studio definition type/,
  );
});


test('Studio definition ids are encoded as one URL path component', () => {
  assert.equal(encodeDefinitionId('user/template'), 'user%2Ftemplate');
  assert.equal(encodeDefinitionId('a b'), 'a%20b');
  assert.throws(() => encodeDefinitionId('   '), /Definition id is required/);
});


test('Studio editor only accepts JSON objects as definition roots', () => {
  assert.deepEqual(definitionDocument('{"id":"a"}'), { id: 'a' });
  assert.throws(() => definitionDocument(''), /Definition JSON is required/);
  assert.throws(() => definitionDocument('[]'), /Definition JSON root must be an object/);
  assert.throws(() => definitionDocument('null'), /Definition JSON root must be an object/);
});


test('Viewer preset compatibility still follows template id and source format', () => {
  const templates = [{ id: 'table', source_format: 'example/1.0' }];
  const presets = [
    { id: 'ok', input_template_ref: 'table', source_format: 'example/1.0' },
    { id: 'wrong-template', input_template_ref: 'other', source_format: 'example/1.0' },
    { id: 'wrong-format', input_template_ref: 'table', source_format: 'example/2.0' },
  ];
  assert.deepEqual(compatiblePresets('table', templates, presets).map(item => item.id), ['ok']);
});
