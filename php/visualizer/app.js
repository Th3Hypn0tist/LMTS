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
  gui.replace(app, blocks);
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
