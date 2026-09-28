import { WebGUI } from './WebGUI/webgui.js';

const gui = new WebGUI({ theme: null });
const app = document.querySelector('#app');

function h(tag, props = {}, children = []) {
  return gui.h(tag, props, children);
}

function text(value, fallback = '-') {
  return value == null || value === '' ? fallback : String(value);
}

function number(value, digits = 2) {
  if (value == null || value === '') return '-';
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return String(value);
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(parsed);
}

function median(values) {
  const numeric = (values ?? [])
    .map(value => Number(value))
    .filter(value => Number.isFinite(value))
    .sort((a, b) => a - b);
  if (!numeric.length) return null;
  const middle = Math.floor(numeric.length / 2);
  return numeric.length % 2
    ? numeric[middle]
    : (numeric[middle - 1] + numeric[middle]) / 2;
}

function average(values) {
  const numeric = (values ?? [])
    .map(value => Number(value))
    .filter(value => Number.isFinite(value));
  if (!numeric.length) return null;
  return numeric.reduce((sum, value) => sum + value, 0) / numeric.length;
}

function aggregate(values, mode) {
  return mode === 'avg' ? average(values) : median(values);
}

function level1ViewState(metricOptions) {
  const params = new URLSearchParams(location.search);
  const available = new Set((metricOptions ?? []).map(item => item.value));
  const requested = params.get('l1_metric');
  const metric = requested && available.has(requested) ? requested : 'pf_score';
  const aggregation = ['avg', 'med'].includes(params.get('l1_agg'))
    ? params.get('l1_agg')
    : 'med';
  const direction = ['asc', 'desc'].includes(params.get('l1_dir'))
    ? params.get('l1_dir')
    : (metric === 'pf_score' || metric === 'coverage' ? 'desc' : 'asc');
  return { metric, aggregation, direction };
}

function updateLevel1View(next) {
  const params = new URLSearchParams(location.search);
  params.set('l1_metric', next.metric);
  params.set('l1_agg', next.aggregation);
  params.set('l1_dir', next.direction);
  load(params);
}

function level2ViewState() {
  const params = new URLSearchParams(location.search);
  const metric = ['total_time', 'ttft', 'pf_score'].includes(params.get('l2_metric'))
    ? params.get('l2_metric')
    : 'total_time';
  const aggregation = ['avg', 'med'].includes(params.get('l2_agg'))
    ? params.get('l2_agg')
    : 'med';
  const axes = ['model_test', 'test_model'].includes(params.get('l2_axes'))
    ? params.get('l2_axes')
    : 'model_test';
  return { metric, aggregation, axes };
}

function updateLevel2View(next) {
  const params = new URLSearchParams(location.search);
  params.set('l2_metric', next.metric);
  params.set('l2_agg', next.aggregation);
  params.set('l2_axes', next.axes);
  load(params);
}

function level3ViewState(drilldown) {
  const params = new URLSearchParams(location.search);
  const available = new Set((drilldown?.metric_options ?? []).map(item => item.value));
  const requested = params.get('l3_metric');
  const metric = requested && available.has(requested) ? requested : 'total_time';
  const aggregation = ['avg', 'med'].includes(params.get('l3_agg'))
    ? params.get('l3_agg')
    : 'med';
  return { metric, aggregation };
}

function updateLevel3View(next) {
  const params = new URLSearchParams(location.search);
  params.set('l3_metric', next.metric);
  params.set('l3_agg', next.aggregation);
  load(params);
}

function evidenceValue(sample) {
  if (sample.value_number != null && sample.value_number !== '') return number(sample.value_number);
  if (sample.value_boolean != null && sample.value_boolean !== '') return String(Boolean(Number(sample.value_boolean)));
  if (sample.value_text != null && sample.value_text !== '') return String(sample.value_text);
  if (sample.value_json != null && sample.value_json !== '') return String(sample.value_json);
  return '-';
}

function evidenceTable(headers, rows) {
  const table = h('table', { className: 'results-table evidence-table' });
  table.append(h('thead', {}, [h('tr', {}, headers.map(label => h('th', { text: label }))) ]));
  const body = h('tbody');
  for (const row of rows) body.append(h('tr', {}, row.map(value => h('td', {}, Array.isArray(value) ? value : [value]))));
  table.append(body);
  return h('div', { className: 'scroll' }, [table]);
}

function openEvidenceModal(cell, payload) {
  const sourceIds = cell.source_configuration_ids ?? [cell.configuration_id];
  const records = (payload.records ?? []).filter(record =>
    record.target_ref === cell.target_ref
    && record.test_version_id === cell.test_version_id
    && sourceIds.includes(record.configuration_id)
  );
  const recordKeys = new Set(records.map(record => record.report_id + '\u0000' + record.record_id));
  const telemetry = (payload.telemetry ?? []).filter(sample =>
    recordKeys.has(sample.report_id + '\u0000' + sample.record_id)
  );
  const variance = (payload.variance ?? []).filter(sample =>
    sample.target_ref === cell.target_ref
    && sample.test_version_id === cell.test_version_id
    && sourceIds.includes(sample.configuration_id)
  );

  const overlay = h('div', { className: 'evidence-overlay' });
  const close = () => overlay.remove();
  const runRows = records.map(run => [
    h('a', {
      href: './api/report.php?id=' + encodeURIComponent(run.report_id),
      target: '_blank',
      rel: 'noopener',
      text: run.report_id,
      title: 'Open immutable report evidence',
    }),
    text(run.record_id),
    text(run.configuration_label || run.configuration_id),
    outcomeLabel(run.outcome),
    number(run.total_time_ms),
    number(run.ttft_ms),
    number(run.score_percent),
    text(run.started_at),
  ]);
  const varianceRows = variance.map(sample => [
    text(sample.configuration_id),
    text(sample.status),
    number(sample.pass_count, 0),
    number(sample.fail_count, 0),
    number(sample.sample_count, 0),
    number(sample.pf_score),
    number(sample.variance),
  ]);
  const telemetryRows = telemetry.map(sample => [
    text(sample.report_id),
    text(sample.record_id),
    text(sample.telemetry_name || sample.canonical_key),
    evidenceValue(sample),
    text(sample.unit, ''),
    number(sample.sample_ordinal, 0),
    text(sample.observed_at),
  ]);

  const dialog = h('section', { className: 'evidence-modal', role: 'dialog', 'aria-modal': 'true' }, [
    h('div', { className: 'section-title' }, [
      h('div', {}, [
        h('h2', { text: 'Raw evidence' }),
        h('div', { className: 'subtle', text: text(cell.target_label || cell.target_ref) + ' · ' + text(cell.test_label || cell.test_version_id) }),
      ]),
      gui.button('Close', { className: 'filter-action secondary', on: { click: close } }),
    ]),
    h('div', { className: 'evidence-meta' }, [
      h('span', { text: 'Requested configuration: ' + text(cell.configuration_id) }),
      h('span', { text: 'Evidence scope: ' + text(cell.evidence_scope, 'exact') }),
      h('span', { text: 'Source configurations: ' + sourceIds.join(', ') }),
      h('span', { text: 'Matrix state: ' + (location.search || '(default)') }),
    ]),
    cell.evidence_scope === 'inferred_lighter_pass'
      ? h('p', { className: 'panel-note', text: 'Compatibility is inferred from lighter PASS evidence. No performance value is attributed to the requested configuration.' })
      : null,
    h('h3', { text: 'Runs in current statistics payload' }),
    runRows.length
      ? evidenceTable(['Report', 'Record', 'Configuration', 'Outcome', 'Total ms', 'TTFT ms', 'Score', 'Started'], runRows)
      : h('p', { className: 'empty', text: 'No source run rows are present in the current statistics payload.' }),
    h('h3', { text: 'Canonical PASS / FAIL aggregate' }),
    varianceRows.length
      ? evidenceTable(['Configuration', 'Status', 'Pass', 'Fail', 'N', 'P/F', 'Variance'], varianceRows)
      : h('p', { className: 'empty', text: 'No variance aggregate is present for this source cell.' }),
    h('h3', { text: 'Telemetry samples in current statistics payload' }),
    telemetryRows.length
      ? evidenceTable(['Report', 'Record', 'Metric', 'Value', 'Unit', 'Ordinal', 'Observed'], telemetryRows)
      : h('p', { className: 'empty', text: 'No telemetry samples are present for the visible source runs.' }),
  ].filter(Boolean));
  overlay.append(dialog);
  document.body.append(overlay);
}

function targetLabel(record) {
  if (record.target_label) return record.target_label;
  const id = record.target_id ? ' · ' + record.target_id : '';
  return text(record.target_kind, 'unresolved') + id;
}

function testLabel(record) {
  if (record.test_name && record.test_version) return record.test_name + ' @ ' + record.test_version;
  if (record.test_namespace) return record.test_namespace;
  return text(record.test_version_id, 'unresolved');
}

function outcomeLabel(value, suffix = '') {
  const label = text(value, 'unknown').toLowerCase();
  return h('span', { className: 'result result-' + label, text: label.toUpperCase() + suffix });
}

function matrixOutcome(cell) {
  const states = ['pass', 'fail'].filter(key => Number(cell?.[key] ?? 0) > 0);
  return states.length === 1 ? states[0] : (states.length > 1 ? 'mixed' : 'unknown');
}

function matrixLink(cell) {
  const params = new URLSearchParams(location.search);
  params.set('target_kind', text(cell.target_kind, 'unknown'));
  if (cell.target_ref) params.set('target_id', cell.target_ref);
  else params.delete('target_id');
  if (cell.test_version_id) params.set('test_version_id', cell.test_version_id);
  return '?' + params.toString();
}

function benchmarkMatrix(cells) {
  const targets = new Map();
  const tests = new Map();
  const index = new Map();

  for (const cell of cells ?? []) {
    const targetKey = text(cell.target_kind, 'unknown') + '\u0000' + text(cell.target_ref, '');
    const testKey = text(cell.test_version_id, 'unresolved');
    if (!targets.has(targetKey)) targets.set(targetKey, cell.target_label || cell.target_ref || cell.target_kind || 'Unresolved target');
    if (!tests.has(testKey)) tests.set(testKey, cell.test_label || cell.test_version_id || 'Unresolved test');
    index.set(targetKey + '\u0001' + testKey, cell);
  }

  const targetEntries = [...targets.entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1]), undefined, { numeric: true }));
  const testEntries = [...tests.entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1]), undefined, { numeric: true }));
  const table = h('table', { className: 'matrix' });
  const head = h('tr', {}, [h('th', { text: 'Target / model' })]);
  for (const [, label] of testEntries) head.append(h('th', { text: label }));
  table.append(h('thead', {}, [head]));

  const body = h('tbody');
  for (const [targetKey, targetLabel] of targetEntries) {
    const row = h('tr', {}, [h('th', { className: 'row-label', text: targetLabel })]);
    for (const [testKey] of testEntries) {
      const cell = index.get(targetKey + '\u0001' + testKey);
      if (!cell) {
        row.append(h('td', { className: 'matrix-empty', text: '—' }));
        continue;
      }
      const outcome = matrixOutcome(cell);
      const runs = Number(cell.runs ?? 0);
      row.append(h('td', {}, [
        h('a', {
          className: 'matrix-cell matrix-cell-' + outcome,
          href: matrixLink(cell),
          title: [
            'runs ' + runs,
            'pass ' + number(cell.pass, 0),
            'fail ' + number(cell.fail, 0),
          ].join(' · '),
        }, [
          outcomeLabel(outcome),
          h('span', { className: 'matrix-runs', text: runs === 1 ? '1 run' : runs + ' runs' }),
        ]),
      ]));
    }
    body.append(row);
  }
  table.append(body);
  return h('div', { className: 'scroll' }, [table]);
}

function summaryCard(label, value) {
  return h('div', { className: 'card' }, [
    h('strong', { text: number(value, 0) }),
    h('span', { text: label }),
  ]);
}

function configurationComparison(matrix, view, payload) {
  const cells = matrix?.cells ?? [];
  const targets = new Map();
  const tests = new Map();
  const index = new Map();

  for (const cell of cells) {
    const targetKey = text(cell.target_ref, 'unresolved');
    const testKey = text(cell.test_version_id, 'unresolved');
    if (!targets.has(targetKey)) targets.set(targetKey, cell.target_label || cell.target_ref || 'Unresolved model');
    if (!tests.has(testKey)) tests.set(testKey, cell.test_label || cell.test_version_id || 'Unresolved test');
    index.set(targetKey + '\u0001' + testKey, cell);
  }

  const targetEntries = [...targets.entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1]), undefined, { numeric: true }));
  const testEntries = [...tests.entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1]), undefined, { numeric: true }));
  const rowEntries = view.axes === 'test_model' ? testEntries : targetEntries;
  const columnEntries = view.axes === 'test_model' ? targetEntries : testEntries;
  const table = h('table', { className: 'matrix' });
  const head = h('tr', {}, [h('th', { text: view.axes === 'test_model' ? 'Test / model' : 'Model / test' })]);
  for (const [, label] of columnEntries) head.append(h('th', { text: label }));
  table.append(h('thead', {}, [head]));

  function cellFor(rowKey, columnKey) {
    return view.axes === 'test_model'
      ? index.get(columnKey + '\u0001' + rowKey)
      : index.get(rowKey + '\u0001' + columnKey);
  }

  function metricValue(cell) {
    if (text(cell.evidence_scope, 'unknown') === 'inferred_lighter_pass') return null;
    if (cell.performance_scope !== 'exact' && view.metric !== 'pf_score') return null;
    if (view.metric === 'pf_score') {
      return cell.pf_score == null ? null : Number(cell.pf_score);
    }
    const samples = view.metric === 'ttft'
      ? cell.ttft_samples_ms
      : cell.total_time_samples_ms;
    return aggregate(samples, view.aggregation);
  }

  function metricLabel(cell) {
    const value = metricValue(cell);
    if (value == null || !Number.isFinite(value)) return 'NaN';
    if (view.metric === 'pf_score') return number(value);
    return number(value) + ' ms';
  }

  const body = h('tbody');
  for (const [rowKey, rowLabel] of rowEntries) {
    const row = h('tr', {}, [h('th', { className: 'row-label', text: rowLabel })]);
    for (const [columnKey] of columnEntries) {
      const cell = cellFor(rowKey, columnKey);
      if (!cell) {
        row.append(h('td', { className: 'matrix-empty', text: 'NaN' }));
        continue;
      }

      const scope = text(cell.evidence_scope, 'unknown');
      const compatibility = text(cell.compatibility_status, 'unknown');
      if (scope === 'lower_fail_only' || compatibility === 'unknown') {
        row.append(h('td', {}, [
          h('div', { className: 'matrix-cell matrix-cell-unknown' }, [
            h('strong', { text: 'NaN' }),
            h('span', { className: 'matrix-runs', text: 'lighter FAIL does not propagate' }),
            h('span', { className: 'subtle', text: 'compatibility unknown' }),
          ]),
        ]));
        continue;
      }

      const inferred = scope === 'inferred_lighter_pass';
      const evidence = inferred
        ? 'inferred PASS from lighter configuration'
        : 'exact evidence';

      row.append(h('td', {}, [
        h('button', {
          className: 'matrix-cell matrix-cell-action matrix-cell-' + compatibility,
          on: { click: () => openEvidenceModal(cell, payload) },
          title: 'Open raw evidence',
        }, [
          h('strong', { text: metricLabel(cell) }),
          h('span', { className: 'matrix-runs', text:
            inferred
              ? 'PASS · performance unavailable'
              : 'P/F ' + number(cell.pf_score) + ' · N=' + number(cell.sample_count, 0)
          }),
          h('span', { className: 'subtle', text: evidence }),
        ]),
      ]));
    }
    body.append(row);
  }
  table.append(body);
  return h('div', { className: 'scroll' }, [table]);
}

function modelDrilldownTable(drilldown, view, payload) {
  const cells = drilldown?.cells ?? [];
  const tests = new Map();
  const configurations = new Map();
  const index = new Map();

  for (const cell of cells) {
    const testKey = text(cell.test_version_id, 'unresolved');
    const configKey = text(cell.configuration_id, 'unresolved');
    if (!tests.has(testKey)) tests.set(testKey, cell.test_label || cell.test_version_id || 'Unresolved test');
    if (!configurations.has(configKey)) configurations.set(configKey, cell.configuration_label || cell.configuration_id || 'Unresolved configuration');
    index.set(testKey + '\u0001' + configKey, cell);
  }

  const testEntries = [...tests.entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1]), undefined, { numeric: true }));
  const configEntries = [...configurations.entries()].sort((a, b) => String(a[1]).localeCompare(String(b[1]), undefined, { numeric: true }));
  const table = h('table', { className: 'matrix' });
  const head = h('tr', {}, [h('th', { text: 'Test / hardware' })]);
  for (const [, label] of configEntries) head.append(h('th', { text: label }));
  table.append(h('thead', {}, [head]));

  function metricValue(cell) {
    if (view.metric === 'pf_score') return cell.pf_score == null ? null : Number(cell.pf_score);
    if (view.metric === 'variance') return cell.variance == null ? null : Number(cell.variance);
    if (view.metric === 'total_time') return aggregate(cell.total_time_samples_ms, view.aggregation);
    if (view.metric === 'ttft') return aggregate(cell.ttft_samples_ms, view.aggregation);
    if (view.metric.startsWith('telemetry:')) {
      const typeId = view.metric.slice('telemetry:'.length);
      return aggregate(cell.telemetry?.[typeId]?.samples, view.aggregation);
    }
    return null;
  }

  function metricUnit(cell) {
    if (view.metric === 'total_time' || view.metric === 'ttft') return 'ms';
    if (view.metric === 'pf_score') return '';
    if (view.metric === 'variance') return '';
    if (view.metric.startsWith('telemetry:')) {
      const typeId = view.metric.slice('telemetry:'.length);
      return text(cell.telemetry?.[typeId]?.unit, '');
    }
    return '';
  }

  const body = h('tbody');
  for (const [testKey, testLabelValue] of testEntries) {
    const row = h('tr', {}, [h('th', { className: 'row-label', text: testLabelValue })]);
    for (const [configKey] of configEntries) {
      const cell = index.get(testKey + '\u0001' + configKey);
      if (!cell) {
        row.append(h('td', { className: 'matrix-empty', text: 'NaN' }));
        continue;
      }
      const value = metricValue(cell);
      const unit = metricUnit(cell);
      const label = value == null || !Number.isFinite(value)
        ? 'NaN'
        : number(value) + (unit ? ' ' + unit : '');
      row.append(h('td', {}, [
        h('button', {
          className: 'matrix-cell matrix-cell-action matrix-cell-' + text(cell.compatibility_status, 'unknown'),
          on: { click: () => openEvidenceModal({ ...cell, evidence_scope: 'exact', source_configuration_ids: [cell.configuration_id] }, payload) },
          title: 'Open raw evidence',
        }, [
          h('strong', { text: label }),
          h('span', { className: 'matrix-runs', text: 'P/F ' + number(cell.pf_score) + ' · N=' + number(cell.sample_count, 0) }),
          h('span', { className: 'subtle', text: 'exact configuration evidence' }),
        ]),
      ]));
    }
    body.append(row);
  }
  table.append(body);
  return h('div', { className: 'scroll' }, [table]);
}

function configurationOverviewTable(rows, view, metricOptions) {
  const metricOption = (metricOptions ?? []).find(item => item.value === view.metric) ?? {
    value: 'pf_score',
    label: 'P/F score',
    unit: null,
  };

  function metricValue(model) {
    if (view.metric === 'pf_score') return Number(model.pf_score);
    if (view.metric === 'coverage') return Number(model.coverage);
    if (view.metric.startsWith('telemetry:')) {
      const typeId = view.metric.slice('telemetry:'.length);
      return aggregate(model.telemetry?.[typeId]?.samples, view.aggregation);
    }
    return null;
  }

  function orderedModels(row) {
    const models = [...(row.models ?? [])];
    models.sort((left, right) => {
      const a = metricValue(left);
      const b = metricValue(right);
      const aValid = Number.isFinite(a);
      const bValid = Number.isFinite(b);
      if (aValid !== bValid) return aValid ? -1 : 1;
      if (aValid && bValid && a !== b) {
        return view.direction === 'asc' ? a - b : b - a;
      }
      if (view.metric === 'pf_score') {
        const coverage = Number(right.coverage) - Number(left.coverage);
        if (coverage !== 0) return coverage;
      }
      return String(left.target_ref).localeCompare(String(right.target_ref), undefined, { numeric: true });
    });
    return models;
  }

  function leaders(row) {
    const models = orderedModels(row);
    if (!models.length) return [];
    const first = metricValue(models[0]);
    if (!Number.isFinite(first)) return [];
    const firstCoverage = Number(models[0].coverage);
    return models.filter(model =>
      metricValue(model) === first
      && (view.metric !== 'pf_score' || Number(model.coverage) === firstCoverage)
    );
  }

  function metricText(model) {
    const value = metricValue(model);
    if (!Number.isFinite(value)) return 'NaN';
    const unit = metricOption.unit ? ' ' + metricOption.unit : '';
    return number(value) + unit;
  }

  const table = h('table', { className: 'results-table' });
  table.append(h('thead', {}, [
    h('tr', {}, [
      h('th', { text: 'Hardware configuration' }),
      h('th', { text: 'Models tested' }),
      h('th', { text: 'Rank #1' }),
      h('th', { text: metricOption.label }),
      h('th', { text: 'Coverage' }),
    ]),
  ]));

  const body = h('tbody');
  for (const row of rows ?? []) {
    const params = new URLSearchParams(location.search);
    params.set('configuration_id', text(row.configuration_id, ''));
    const href = '?' + params.toString();
    const top = leaders(row);
    const leaderLabel = top.length
      ? top.map(item => text(item.target_label || item.target_ref)).join(' · ')
      : 'NaN';
    const defaultRanking = view.metric === 'pf_score';
    body.append(h('tr', {}, [
      h('td', {}, [
        h('a', {
          href,
          text: text(row.configuration_name || row.configuration_id),
          title: text(row.configuration_fingerprint),
        }),
        h('div', {
          className: 'subtle',
          text: defaultRanking
            ? 'Exact hardware evidence · P/F ↓ · coverage ↓ · equal values share rank'
            : 'Exact hardware evidence · use-case sort: ' + metricOption.label,
        }),
      ]),
      h('td', { text: number(row.models_tested_count, 0) }),
      h('td', {}, [
        h('strong', { text: leaderLabel }),
        top.length > 1
          ? h('div', { className: 'subtle', text: 'Shared #1 · ' + String(top.length) + ' models' })
          : null,
      ].filter(Boolean)),
      h('td', { text: top.length ? metricText(top[0]) : 'NaN' }),
      h('td', { text: top.length ? number(top[0].coverage) : 'NaN' }),
    ]));
  }
  table.append(body);
  return h('div', { className: 'scroll' }, [table]);
}

function option(value, label, selected) {
  return gui.option(value, label, { selected: String(value) === String(selected ?? '') });
}

function filterSelect(label, name, values, selected, valueOf, labelOf) {
  const select = gui.select({ name }, [
    option('', 'All', selected),
    ...values.map(item => option(valueOf(item), labelOf(item), selected)),
  ]);
  return gui.field(label, select, { className: 'filter-field' });
}

function filterInput(label, name, type, value) {
  return gui.field(label, gui.input({ name, type, value: value ?? '' }), { className: 'filter-field' });
}

function renderFilters(filters) {
  const selected = filters?.selected ?? {};
  const options = filters?.options ?? {};
  const form = h('form', { className: 'filters' }, [
    filterSelect('User', 'user_id', options.users ?? [], selected.user_id, item => item.user_id, item => item.user_id),
    filterSelect('System', 'system_id', options.systems ?? [], selected.system_id, item => item.system_id, item => item.label || item.system_id),
    filterSelect('Target', 'target', options.targets ?? [], selected.target, item => item.value, item => item.label),
    filterSelect('Test', 'test_version_id', options.tests ?? [], selected.test_version_id, item => item.test_version_id, item => item.label),
    filterSelect('Outcome', 'outcome', options.outcomes ?? [], selected.outcome, item => item, item => String(item).toUpperCase()),
    filterSelect('Report', 'report_id', options.reports ?? [], selected.report_id, item => item.report_id, item => item.report_id),
    filterInput('From', 'from', 'datetime-local', selected.from_local),
    filterInput('To', 'to', 'datetime-local', selected.to_local),
    gui.field('Rows', gui.select({ name: 'limit' }, [50, 100, 200, 500].map(value => option(value, String(value), selected.limit))), { className: 'filter-field compact' }),
    gui.button('Apply', { type: 'submit', className: 'filter-action' }),
    gui.button('Reset', { className: 'filter-action secondary', on: { click: () => load(new URLSearchParams()) } }),
  ]);

  form.addEventListener('submit', event => {
    event.preventDefault();
    const data = new FormData(form);
    const params = new URLSearchParams();
    for (const key of ['configuration_id', 'l1_metric', 'l1_agg', 'l1_dir', 'l2_metric', 'l2_agg', 'l2_axes', 'l3_metric', 'l3_agg']) {
      const value = new URLSearchParams(location.search).get(key);
      if (value) params.set(key, value);
    }
    for (const [key, raw] of data.entries()) {
      const value = String(raw).trim();
      if (!value) continue;
      if ((key === 'from' || key === 'to') && value) {
        const instant = new Date(value);
        if (!Number.isNaN(instant.valueOf())) params.set(key, instant.toISOString());
      } else if (key === 'target') {
        const separator = value.indexOf(':');
        if (separator > 0) {
          params.set('target_kind', value.slice(0, separator));
          const targetId = value.slice(separator + 1);
          if (targetId) params.set('target_id', targetId);
        }
      } else {
        params.set(key, value);
      }
    }
    load(params);
  });
  return form;
}

function compareValues(left, right) {
  const a = left == null ? '' : left;
  const b = right == null ? '' : right;
  const an = Number(a);
  const bn = Number(b);
  if (a !== '' && b !== '' && Number.isFinite(an) && Number.isFinite(bn)) return an - bn;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

function resultsTable(records) {
  const container = h('div', { className: 'scroll' });
  let sortKey = 'started_at';
  let direction = -1;

  const columns = [
    ['report_id', 'Report', row => row.report_id],
    ['target_label', 'Target / model', row => targetLabel(row)],
    ['test_name', 'Test', row => testLabel(row)],
    ['outcome', 'Outcome', row => row.outcome],
    ['score_percent', 'Score %', row => row.score_percent],
    ['ttft_ms', 'TTFT ms', row => row.ttft_ms],
    ['total_time_ms', 'Total ms', row => row.total_time_ms],
    ['input_tokens', 'Input tokens', row => row.input_tokens],
    ['output_tokens', 'Output tokens', row => row.output_tokens],
    ['system_label', 'System', row => row.system_label || row.system_id],
  ];

  function draw() {
    const sorted = [...records].sort((a, b) => direction * compareValues(
      columns.find(column => column[0] === sortKey)?.[2](a),
      columns.find(column => column[0] === sortKey)?.[2](b),
    ));
    const table = h('table', { className: 'results-table' });
    const head = h('tr');
    for (const [key, label] of columns) {
      head.append(h('th', {}, [
        gui.button(label + (sortKey === key ? (direction > 0 ? ' ↑' : ' ↓') : ''), {
          className: 'sort-button',
          on: { click: () => {
            if (sortKey === key) direction *= -1;
            else { sortKey = key; direction = 1; }
            draw();
          } },
        }),
      ]));
    }
    table.append(h('thead', {}, [head]));

    const body = h('tbody');
    for (const record of sorted) {
      const reportLink = h('a', {
        href: './api/report.php?id=' + encodeURIComponent(record.report_id),
        target: '_blank',
        rel: 'noopener',
        text: record.report_id,
        title: 'Open immutable report evidence',
      });
      body.append(h('tr', {}, [
        h('td', {}, [reportLink, h('div', { className: 'subtle', text: text(record.record_id) })]),
        h('td', { text: targetLabel(record) }),
        h('td', { text: testLabel(record) }),
        h('td', {}, [outcomeLabel(record.outcome)]),
        h('td', { text: number(record.score_percent) }),
        h('td', { text: number(record.ttft_ms) }),
        h('td', { text: number(record.total_time_ms) }),
        h('td', { text: number(record.input_tokens, 0) }),
        h('td', { text: number(record.output_tokens, 0) }),
        h('td', { text: text(record.system_label || record.system_id) }),
      ]));
    }
    table.append(body);
    gui.replace(container, [table]);
  }

  draw();
  return container;
}

function numericSeries(samples) {
  const groups = new Map();
  for (const sample of samples ?? []) {
    if (sample.value_number == null || sample.value_number === '') continue;
    const value = Number(sample.value_number);
    if (!Number.isFinite(value)) continue;
    const unit = sample.unit ?? '';
    const key = String(sample.canonical_key) + '\u0000' + String(unit);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({ ...sample, numeric_value: value });
  }
  return [...groups.values()];
}

function telemetryChart(samples) {
  const first = samples[0];
  const values = samples.map(sample => sample.numeric_value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const bars = samples.map(sample => {
    const normalized = span === 0 ? 0.5 : (sample.numeric_value - min) / span;
    return h('div', {
      className: 'telemetry-bar',
      style: { height: String(Math.max(4, normalized * 96)) + '%' },
      title: [
        sample.report_id + '/' + sample.record_id,
        number(sample.numeric_value) + (first.unit ? ' ' + first.unit : ''),
        sample.observed_at || ('sample ' + sample.sample_ordinal),
      ].join(' · '),
    });
  });

  return h('article', { className: 'telemetry-chart' }, [
    h('div', { className: 'chart-header' }, [
      h('div', {}, [
        h('strong', { text: first.telemetry_name || first.canonical_key }),
        h('div', { className: 'subtle', text: first.canonical_key + (first.unit ? ' · ' + first.unit : '') }),
      ]),
      h('span', { className: 'sample-count', text: String(samples.length) + ' raw samples' }),
    ]),
    h('div', { className: 'chart-range' }, [
      h('span', { text: number(max) }),
      h('span', { text: number(min) }),
    ]),
    h('div', { className: 'chart-scroll' }, [
      h('div', {
        className: 'bar-track',
        style: { minWidth: String(Math.max(640, samples.length * 7)) + 'px' },
      }, bars),
    ]),
  ]);
}

function render(payload) {
  if (payload?.format !== 'lmts.statistics' || payload?.version !== 1) {
    throw new Error('Unsupported LMTS statistics payload');
  }
  const summary = payload.summary ?? {};
  const configurationOverview = payload.configuration_overview ?? [];
  const level1MetricOptions = payload.level1_metric_options ?? [];
  const level1View = level1ViewState(level1MetricOptions);
  const configurationMatrix = payload.configuration_matrix ?? {};
  const level2View = level2ViewState();
  const modelDrilldown = payload.model_drilldown ?? {};
  const level3View = level3ViewState(modelDrilldown);
  const matrix = payload.matrix ?? [];
  const records = payload.records ?? [];
  const series = numericSeries(payload.telemetry);

  const blocks = [
    h('header', { className: 'header' }, [
      h('div', { className: 'eyebrow', text: 'LMTS BENCHMARK STATISTICS' }),
      h('h1', { text: 'Benchmark overview' }),
      h('div', { className: 'meta', text: 'Queryable SQL projections over immutable LMTS report evidence' }),
    ]),
    renderFilters(payload.filters),
    h('div', { className: 'summary' }, [
      summaryCard('Reports', summary.reports),
      summaryCard('Result records', summary.result_records),
      summaryCard('Tests', summary.tests),
      summaryCard('Targets', summary.targets),
      summaryCard('Systems', summary.systems),
      summaryCard('Pass', summary.pass),
      summaryCard('Fail', summary.fail),
      summaryCard('Telemetry values', summary.telemetry_values),
    ]),
    configurationMatrix.configuration_id ? h('section', { className: 'panel' }, [
      h('div', { className: 'section-title' }, [
        h('div', {}, [
          h('h2', { text: 'Configuration comparison' }),
          h('div', { className: 'subtle', text: 'Exact evidence first. Lighter PASS may infer compatibility upward; performance never propagates.' }),
        ]),
        h('span', { className: 'subtle', text: text(configurationMatrix.configuration_id) }),
      ]),
      h('div', { className: 'filters' }, [
        gui.field('Metric', gui.select({
          on: { change: event => updateLevel2View({ ...level2View, metric: event.target.value }) },
        }, [
          option('total_time', 'Total time', level2View.metric),
          option('ttft', 'TTFT', level2View.metric),
          option('pf_score', 'P/F score', level2View.metric),
        ]), { className: 'filter-field compact' }),
        gui.field('Aggregation', gui.select({
          on: { change: event => updateLevel2View({ ...level2View, aggregation: event.target.value }) },
        }, [
          option('med', 'Med', level2View.aggregation),
          option('avg', 'Avg', level2View.aggregation),
        ]), { className: 'filter-field compact' }),
        gui.field('Axes', gui.select({
          on: { change: event => updateLevel2View({ ...level2View, axes: event.target.value }) },
        }, [
          option('model_test', 'Models × tests', level2View.axes),
          option('test_model', 'Tests × models', level2View.axes),
        ]), { className: 'filter-field compact' }),
      ]),
      h('div', { className: 'subtle', text:
        configurationMatrix.hardware_ceiling_status === 'ready'
          ? 'Hardware ceiling enabled · lighter configurations: ' + String((configurationMatrix.lighter_configuration_ids ?? []).length)
          : 'Hardware ceiling inference disabled: canonical ordering evidence is incomplete.'
      }),
      (configurationMatrix.cells ?? []).length
        ? configurationComparison(configurationMatrix, level2View, payload)
        : h('p', { className: 'empty', text: 'No exact model/test evidence exists for this configuration.' }),
    ]) : null,
    modelDrilldown.target_ref ? h('section', { className: 'panel' }, [
      h('div', { className: 'section-title' }, [
        h('div', {}, [
          h('h2', { text: 'Model drilldown' }),
          h('div', { className: 'subtle', text: 'Level 3. Rows are tests; columns are exact hardware configurations. Axes are fixed.' }),
        ]),
        h('span', { className: 'subtle', text: text(modelDrilldown.target_label || modelDrilldown.target_ref) }),
      ]),
      h('div', { className: 'filters' }, [
        gui.field('Metric', gui.select({
          on: { change: event => updateLevel3View({ ...level3View, metric: event.target.value }) },
        }, (modelDrilldown.metric_options ?? []).map(item => option(item.value, item.label, level3View.metric))), { className: 'filter-field' }),
        gui.field('Aggregation', gui.select({
          on: { change: event => updateLevel3View({ ...level3View, aggregation: event.target.value }) },
        }, [
          option('med', 'Med', level3View.aggregation),
          option('avg', 'Avg', level3View.aggregation),
        ]), { className: 'filter-field compact' }),
      ]),
      (modelDrilldown.cells ?? []).length
        ? modelDrilldownTable(modelDrilldown, level3View, payload)
        : h('p', { className: 'empty', text: 'No exact hardware evidence exists for this model.' }),
    ]) : null,
    h('section', { className: 'panel' }, [
      h('div', { className: 'section-title' }, [
        h('div', {}, [
          h('h2', { text: 'Hardware configurations' }),
          h('div', { className: 'subtle', text: 'Level 1. Exact evidence per canonical hardware configuration. Default ranking is P/F then coverage.' }),
        ]),
        h('span', { className: 'subtle', text: String(configurationOverview.length) + ' configuration(s)' }),
      ]),
      h('div', { className: 'filters' }, [
        ...(level1MetricOptions ?? []).map(item => gui.button(item.label, {
          className: 'filter-action' + (level1View.metric === item.value ? '' : ' secondary'),
          on: { click: () => updateLevel1View({
            ...level1View,
            metric: item.value,
            direction: item.value === 'pf_score' || item.value === 'coverage' ? 'desc' : level1View.direction,
          }) },
        })),
        gui.field('Aggregation', gui.select({
          on: { change: event => updateLevel1View({ ...level1View, aggregation: event.target.value }) },
        }, [
          option('med', 'Med', level1View.aggregation),
          option('avg', 'Avg', level1View.aggregation),
        ]), { className: 'filter-field compact' }),
        gui.field('Order', gui.select({
          on: { change: event => updateLevel1View({ ...level1View, direction: event.target.value }) },
        }, [
          option('desc', 'High first', level1View.direction),
          option('asc', 'Low first', level1View.direction),
        ]), { className: 'filter-field compact' }),
      ]),
      configurationOverview.length
        ? configurationOverviewTable(configurationOverview, level1View, level1MetricOptions)
        : h('p', { className: 'empty', text: 'No hardware configurations have benchmark evidence.' }),
    ]),
    h('section', { className: 'panel' }, [
      h('div', { className: 'section-title' }, [
        h('div', {}, [
          h('h2', { text: 'Results matrix' }),
          h('div', { className: 'subtle', text: 'Targets × test versions. Mixed means the filtered scope contains more than one outcome state.' }),
        ]),
        h('span', { className: 'subtle', text: String(matrix.length) + ' populated cells' }),
      ]),
      matrix.length ? benchmarkMatrix(matrix) : h('p', { className: 'empty', text: 'No matrix cells match this view.' }),
    ]),
    h('section', { className: 'panel' }, [
      h('div', { className: 'section-title' }, [
        h('div', {}, [
          h('h2', { text: 'Result records' }),
          h('div', { className: 'subtle', text: 'Record-level drill-down. Report links open immutable canonical evidence.' }),
        ]),
        h('span', { className: 'subtle', text: String(records.length) + ' rows in this view' }),
      ]),
      records.length ? resultsTable(records) : h('p', { className: 'empty', text: 'No projected result records match this view.' }),
    ]),
    h('section', { className: 'panel' }, [
      h('div', { className: 'section-title' }, [
        h('h2', { text: 'Telemetry' }),
        h('span', { className: 'subtle', text: 'One chart per canonical key and unit. Every bar is one stored sample.' }),
      ]),
      series.length
        ? h('div', { className: 'chart-grid' }, series.map(telemetryChart))
        : h('p', { className: 'empty', text: 'No numeric telemetry samples exist for the visible result records.' }),
    ]),
  ];
  gui.replace(app, blocks.filter(Boolean));
}

async function load(params = new URLSearchParams(location.search)) {
  const query = params.toString();
  history.replaceState(null, '', query ? '?' + query : location.pathname);
  gui.replace(app, [h('p', { className: 'loading', text: 'Loading canonical statistics…' })]);
  const response = await fetch('./api/stats.php' + (query ? '?' + query : ''), { cache: 'no-store' });
  if (!response.ok) {
    let detail = 'HTTP ' + response.status;
    try {
      const payload = await response.json();
      if (payload?.error) detail += ': ' + payload.error;
    } catch {}
    throw new Error('Statistics request failed: ' + detail);
  }
  render(await response.json());
}

load().catch(error => {
  gui.replace(app, [h('pre', { className: 'fatal', text: error.stack ?? String(error) })]);
});
