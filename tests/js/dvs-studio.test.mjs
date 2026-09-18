import test from 'node:test';
import assert from 'node:assert/strict';

import {
  compatiblePresets,
  databaseReportLabel,
  copyTextToClipboard,
  dvsErrors,
  errorReportText,
  reportDvsError,
  definitionDocument,
  encodeDefinitionId,
  newDefinition,
  numericInputColumns,
  scaleForColumn,
  studioApi,
  studioCollection,
  studioDraftApi,
  studioRangeApi,
  updateScaleDefinition,
} from '../../lmts/dvs/static/dvs.js';


test('Studio selects the correct registry collection', () => {
  const templates = [{ id: 'template-a' }];
  const presets = [{ id: 'preset-a' }];
  assert.equal(studioCollection('input-template', templates, presets), templates);
  assert.equal(studioCollection('visualization-preset', templates, presets), presets);
  assert.throws(() => studioCollection('unknown', templates, presets), /Unsupported Studio definition type/);
});


test('Studio canonical skeletons use formal typed DVS contracts', () => {
  const template = newDefinition('input-template');
  assert.equal(template.format, 's3d.dvs.input-template');
  assert.equal(template.version, '1.0');
  assert.equal(template.reader, 'json');
  assert.deepEqual(template.columns, [{ name: 'value', selector: 'value', type: 'number' }]);

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
  assert.equal(studioRangeApi(), '/api/studio/range/input-template');
  assert.throws(
    () => studioDraftApi('input-template', 'persist'),
    /Unsupported Studio draft operation/,
  );
  assert.throws(
    () => studioDraftApi('unknown', 'validate'),
    /Unsupported Studio definition type/,
  );
});


test('Studio scale tools only expose number columns', () => {
  const definition = {
    columns: [
      { name: 'name', type: 'string' },
      { name: 'score', type: 'number' },
      { name: 'passed', type: 'boolean' },
      { name: 'latency', type: 'number', scale: { low: 10, high: 20, power: 2 } },
    ],
  };
  assert.deepEqual(numericInputColumns(definition).map(column => column.name), ['score', 'latency']);
  assert.equal(scaleForColumn(definition, 'score'), null);
  assert.deepEqual(scaleForColumn(definition, 'latency'), { low: 10, high: 20, power: 2 });
  assert.throws(() => scaleForColumn(definition, 'name'), /no number column/);
});


test('Studio scale editor applies and removes one canonical scale object', () => {
  const definition = {
    columns: [
      { name: 'score', selector: 'score', type: 'number' },
      { name: 'label', selector: 'label', type: 'string' },
    ],
  };
  const scaled = updateScaleDefinition(definition, 'score', { low: '0.2', high: '5.9', power: '1' });
  assert.deepEqual(scaled.columns[0].scale, { low: 0.2, high: 5.9, power: 1 });
  assert.equal(definition.columns[0].scale, undefined);

  const removed = updateScaleDefinition(scaled, 'score', null);
  assert.equal(removed.columns[0].scale, undefined);
  assert.throws(
    () => updateScaleDefinition(definition, 'label', { low: 0, high: 1, power: 1 }),
    /requires number column/,
  );
  assert.throws(
    () => updateScaleDefinition(definition, 'score', { low: 1, high: 1, power: 1 }),
    /greater than low/,
  );
  assert.throws(
    () => updateScaleDefinition(definition, 'score', { low: 0, high: 1, power: 0 }),
    /greater than zero/,
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


test('DVS database report labels preserve selected database identity', () => {
  assert.equal(
    databaseReportLabel({
      database_source_id: 'archive',
      database_source_label: 'Archive DB',
      created_at: '2026-09-18T08:00:00.000000',
      report_id: 'r-42',
      source_id: 'model-a',
    }),
    '[Archive DB] 2026-09-18T08:00:00.000000 r-42 · model-a',
  );
});


test('DVS error report includes API diagnostics and deduplicates one Error', () => {
  dvsErrors.splice(0, dvsErrors.length);
  const error = new Error('database query failed');
  const first = reportDvsError(error, {
    type: 'api_error',
    method: 'POST',
    path: '/api/database-reports',
    status: 400,
    response_body: '{"error":"mysql failed"}',
  });
  const second = reportDvsError(error, { type: 'database_ui_error' });

  assert.equal(first, second);
  assert.equal(dvsErrors.length, 1);

  const report = errorReportText(dvsErrors, {
    url: 'http://127.0.0.1:8775/',
    userAgent: 'test-agent',
  });
  assert.match(report, /LMTS DVS ERROR REPORT/);
  assert.match(report, /api_error/);
  assert.match(report, /request: POST \/api\/database-reports/);
  assert.match(report, /http_status: 400/);
  assert.match(report, /response_body: \{"error":"mysql failed"\}/);
  assert.match(report, /database query failed/);
  dvsErrors.splice(0, dvsErrors.length);
});


test('DVS clipboard copy helper fails explicitly when no copy path exists', async () => {
  const originalNavigator = globalThis.navigator;
  const originalDocument = globalThis.document;
  try {
    Object.defineProperty(globalThis, 'navigator', {
      configurable: true,
      value: {},
    });
    Object.defineProperty(globalThis, 'document', {
      configurable: true,
      value: {
        execCommand: undefined,
      },
    });
    await assert.rejects(
      () => copyTextToClipboard('test report'),
      /Clipboard copy unavailable/,
    );
  } finally {
    if (originalNavigator === undefined) delete globalThis.navigator;
    else Object.defineProperty(globalThis, 'navigator', { configurable: true, value: originalNavigator });
    if (originalDocument === undefined) delete globalThis.document;
    else Object.defineProperty(globalThis, 'document', { configurable: true, value: originalDocument });
  }
});
