import { WebGUI } from './WebGUI/webgui.js';

const gui = new WebGUI({ theme: null });
const root = document.querySelector('#app');

const state = {
  mode: 'hardware-model',
  configurationKey: null,
  targetKey: null,
  search: '',
  status: 'all',
  metric: 'total_time',
  aggregation: 'median',
  rawCell: null,
};

function h(tag, props = {}, children = []) {
  return gui.h(tag, props, children);
}

function n(value, digits = 2) {
  if (value == null || value === '') return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(parsed);
}

function ms(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return '—';
  if (parsed >= 1000) return n(parsed / 1000, 2) + ' s';
  return n(parsed, 0) + ' ms';
}

function pf(pass, fail) {
  const p = Number(pass || 0);
  const f = Number(fail || 0);
  const total = p + f;
  return total ? (p / total) * 100 : null;
}

function targetKey(cell) {
  return String(cell.target_kind || 'unknown') + ':' + String(cell.target_ref || '');
}

function configurationKey(cell) {
  return String(cell.system_id || '') + ':' + String(cell.compute_profile_id || '');
}

function cellState(cell) {
  const pass = Number(cell?.pass || 0);
  const fail = Number(cell?.fail || 0);
  if (pass > 0) return 'pass';
  if (fail > 0) return 'fail';
  return 'unknown';
}

function cellMetric(cell) {
  if (!cell) return null;
  if (state.metric === 'pf') return pf(cell.pass, cell.fail);
  if (state.metric === 'ttft') {
    return state.aggregation === 'average' ? cell.avg_ttft_ms : cell.median_ttft_ms;
  }
  return state.aggregation === 'average' ? cell.avg_total_time_ms : cell.median_total_time_ms;
}

function metricLabel(cell) {
  const status = cellState(cell);
  if (status === 'fail') return 'FAIL';
  if (status === 'unknown') return '—';
  if (state.metric === 'pf') {
    const value = pf(cell.pass, cell.fail);
    return value == null ? '—' : n(value, 0);
  }
  return ms(cellMetric(cell));
}

function testGroup(cell) {
  const ns = String(cell.test_namespace || cell.test_name || 'Other');
  const first = ns.split(/[.:/]/)[0];
  return first ? first.replace(/[_-]+/g, ' ') : 'Other';
}

function groupBy(items, keyFn) {
  const map = new Map();
  for (const item of items) {
    const key = keyFn(item);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(item);
  }
  return map;
}

function aggregateTarget(cells, totalTests) {
  const pass = cells.reduce((sum, cell) => sum + Number(cell.pass || 0), 0);
  const fail = cells.reduce((sum, cell) => sum + Number(cell.fail || 0), 0);
  const passedTests = cells.filter(cell => Number(cell.pass || 0) > 0).length;
  const failedTests = cells.filter(cell => Number(cell.pass || 0) === 0 && Number(cell.fail || 0) > 0).length;
  const observedTests = new Set(cells.map(cell => cell.test_version_id)).size;
  const medians = cells
    .map(cell => Number(cell.median_total_time_ms))
    .filter(Number.isFinite)
    .sort((a, b) => a - b);
  const median = medians.length
    ? (medians.length % 2
      ? medians[Math.floor(medians.length / 2)]
      : (medians[medians.length / 2 - 1] + medians[medians.length / 2]) / 2)
    : null;

  return {
    pass,
    fail,
    pf: pf(pass, fail),
    passedTests,
    failedTests,
    observedTests,
    totalTests,
    median,
    status: failedTests > 0 ? 'partial' : (passedTests > 0 ? 'compatible' : 'unknown'),
  };
}

function modeButton(id, title, subtitle) {
  const active = state.mode === id;
  return h('button', {
    className: 'mode-card' + (active ? ' active' : ''),
    type: 'button',
    on: { click: () => {
      state.mode = id;
      state.rawCell = null;
      render(window.__LMTS_PAYLOAD__);
    } },
  }, [
    h('span', { className: 'mode-icon', text: id === 'hardware-model' ? '▣' : '◇' }),
    h('span', { className: 'mode-copy' }, [
      h('strong', { text: title }),
      h('small', { text: subtitle }),
    ]),
  ]);
}

function selectControl(label, value, options, onChange) {
  const select = h('select', {
    value: value || '',
    on: { change: event => onChange(event.target.value) },
  }, options.map(item => h('option', {
    value: item.value,
    text: item.label,
    selected: String(item.value) === String(value || ''),
  })));
  return h('label', { className: 'control' }, [
    h('span', { text: label }),
    select,
  ]);
}

function stat(value, label, tone = '') {
  return h('div', { className: 'stat' + (tone ? ' ' + tone : '') }, [
    h('strong', { text: String(value) }),
    h('span', { text: label }),
  ]);
}

function statusPill(value) {
  const labels = {
    compatible: 'Compatible',
    partial: 'Partial',
    fail: 'Failed',
    unknown: 'Unknown',
  };
  return h('span', { className: 'status status-' + value }, [
    h('i'),
    h('span', { text: labels[value] || value }),
  ]);
}

function rankingView(payload, cells, selectedSystem) {
  const tests = new Set(cells.map(cell => cell.test_version_id));
  const byTarget = groupBy(cells, targetKey);
  const rows = [];

  for (const [key, targetCells] of byTarget) {
    const first = targetCells[0];
    const summary = aggregateTarget(targetCells, tests.size);
    rows.push({
      key,
      label: first.target_label || first.target_ref || first.target_kind || 'Unknown model',
      provider: first.target_kind || 'model',
      summary,
    });
  }

  rows.sort((a, b) => {
    const apf = a.summary.pf ?? -1;
    const bpf = b.summary.pf ?? -1;
    if (bpf !== apf) return bpf - apf;
    if (b.summary.passedTests !== a.summary.passedTests) return b.summary.passedTests - a.summary.passedTests;
    return (a.summary.median ?? Infinity) - (b.summary.median ?? Infinity);
  });

  const filtered = rows.filter(row => {
    if (state.search && !row.label.toLowerCase().includes(state.search.toLowerCase())) return false;
    if (state.status !== 'all' && row.summary.status !== state.status) return false;
    return true;
  });

  const compatible = rows.filter(row => row.summary.status === 'compatible').length;
  const partial = rows.filter(row => row.summary.status === 'partial').length;
  const unknown = rows.filter(row => row.summary.status === 'unknown').length;

  const search = h('input', {
    className: 'search-input',
    type: 'search',
    placeholder: 'Search models…',
    value: state.search,
    on: { input: event => {
      state.search = event.target.value;
      render(window.__LMTS_PAYLOAD__);
    } },
  });

  const status = h('select', {
    on: { change: event => {
      state.status = event.target.value;
      render(window.__LMTS_PAYLOAD__);
    } },
  }, [
    ['all', 'All states'],
    ['compatible', 'Compatible'],
    ['partial', 'Partial'],
    ['unknown', 'Unknown'],
  ].map(([value, label]) => h('option', {
    value,
    text: label,
    selected: state.status === value,
  })));

  const table = h('table', { className: 'ranking-table' });
  table.append(h('thead', {}, [h('tr', {}, [
    h('th', { text: '#' }),
    h('th', { text: 'Model' }),
    h('th', { text: 'P/F' }),
    h('th', { text: 'Tests' }),
    h('th', { text: 'Median test time' }),
    h('th', { text: 'Status' }),
    h('th', { text: '' }),
  ])]));

  const body = h('tbody');
  filtered.forEach((row, index) => {
    body.append(h('tr', {}, [
      h('td', { className: 'rank', text: String(index + 1) }),
      h('td', {}, [
        h('strong', { className: 'model-name', text: row.label }),
        h('span', { className: 'subtle block', text: row.provider }),
      ]),
      h('td', { className: 'mono strong', text: row.summary.pf == null ? '—' : n(row.summary.pf, 0) }),
      h('td', {
        className: 'mono',
        text: row.summary.observedTests + '/' + row.summary.totalTests,
        title: row.summary.passedTests + ' passed · ' + row.summary.failedTests + ' failed',
      }),
      h('td', { className: 'mono', text: row.summary.median == null ? '—' : ms(row.summary.median) }),
      h('td', {}, [statusPill(row.summary.status)]),
      h('td', {}, [
        h('button', {
          className: 'row-open',
          type: 'button',
          text: 'Open',
          on: { click: () => {
            state.targetKey = row.key;
            document.querySelector('#matrix')?.scrollIntoView({ behavior: 'smooth' });
            render(window.__LMTS_PAYLOAD__);
          } },
        }),
      ]),
    ]));
  });
  table.append(body);

  return h('div', {}, [
    h('div', { className: 'stats-strip' }, [
      h('div', { className: 'system-summary' }, [
        h('span', { className: 'system-icon', text: '▣' }),
        h('div', {}, [
          h('strong', { text: selectedSystem?.label || 'Hardware configuration' }),
          h('span', { text: selectedSystem?.value || '' }),
        ]),
      ]),
      stat(rows.length, 'models tested'),
      stat(compatible, 'compatible', 'good'),
      stat(partial, 'partial / fails', 'bad'),
      stat(unknown, 'unknown'),
    ]),
    h('section', { className: 'section' }, [
      h('div', { className: 'section-head' }, [
        h('div', {}, [
          h('h2', { text: 'Model results' }),
          h('p', { text: 'Aggregated benchmark evidence for the selected hardware configuration.' }),
        ]),
      ]),
      h('div', { className: 'toolbar' }, [
        search,
        h('label', { className: 'mini-control' }, [
          h('span', { text: 'Status' }),
          status,
        ]),
      ]),
      h('div', { className: 'table-shell' }, [table]),
    ]),
  ]);
}

function hardwareRankingView(payload, cells) {
  const selectedTarget = state.targetKey;
  const modelCells = cells.filter(cell => targetKey(cell) === selectedTarget);
  const bySystem = groupBy(modelCells, configurationKey);
  const allTests = new Set(modelCells.map(cell => cell.test_version_id));
  const rows = [];

  for (const [configKey, systemCells] of bySystem) {
    const first = systemCells[0];
    rows.push({
      systemId: configKey,
      label: first.configuration_label || first.system_label || configKey,
      summary: aggregateTarget(systemCells, allTests.size),
    });
  }

  rows.sort((a, b) => {
    const apf = a.summary.pf ?? -1;
    const bpf = b.summary.pf ?? -1;
    if (bpf !== apf) return bpf - apf;
    return (a.summary.median ?? Infinity) - (b.summary.median ?? Infinity);
  });

  const table = h('table', { className: 'ranking-table' });
  table.append(h('thead', {}, [h('tr', {}, [
    h('th', { text: '#' }),
    h('th', { text: 'Hardware configuration' }),
    h('th', { text: 'P/F' }),
    h('th', { text: 'Tests' }),
    h('th', { text: 'Median test time' }),
    h('th', { text: 'Status' }),
  ])]));

  const body = h('tbody');
  rows.forEach((row, index) => {
    body.append(h('tr', {}, [
      h('td', { className: 'rank', text: String(index + 1) }),
      h('td', {}, [
        h('strong', { text: row.label }),
        h('span', { className: 'subtle block', text: row.systemId }),
      ]),
      h('td', { className: 'mono strong', text: row.summary.pf == null ? '—' : n(row.summary.pf, 0) }),
      h('td', { className: 'mono', text: row.summary.observedTests + '/' + row.summary.totalTests }),
      h('td', { className: 'mono', text: row.summary.median == null ? '—' : ms(row.summary.median) }),
      h('td', {}, [statusPill(row.summary.status)]),
    ]));
  });
  table.append(body);

  const target = payload.filters.options.targets.find(item => item.value === selectedTarget);

  return h('div', {}, [
    h('div', { className: 'stats-strip' }, [
      h('div', { className: 'system-summary' }, [
        h('span', { className: 'system-icon', text: '◇' }),
        h('div', {}, [
          h('strong', { text: target?.label || 'Selected model' }),
          h('span', { text: selectedTarget || '' }),
        ]),
      ]),
      stat(rows.length, 'configurations tested'),
      stat(rows.filter(row => row.summary.status === 'compatible').length, 'compatible', 'good'),
      stat(rows.filter(row => row.summary.status === 'partial').length, 'partial / fails', 'bad'),
    ]),
    h('section', { className: 'section' }, [
      h('div', { className: 'section-head' }, [
        h('div', {}, [
          h('h2', { text: 'Hardware results' }),
          h('p', { text: 'Compare the selected model across tested hardware configurations.' }),
        ]),
      ]),
      h('div', { className: 'table-shell' }, [table]),
    ]),
  ]);
}

function matrixView(payload, cells) {
  let visibleCells = cells;

  if (state.mode === 'hardware-model' && state.configurationKey) {
    visibleCells = visibleCells.filter(cell => configurationKey(cell) === String(state.configurationKey));
  }
  if (state.targetKey) {
    visibleCells = visibleCells.filter(cell => targetKey(cell) === state.targetKey);
  }

  const targets = [...groupBy(visibleCells, targetKey).entries()]
    .map(([key, items]) => ({ key, label: items[0].target_label || items[0].target_ref || key }))
    .sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }));

  const tests = [...groupBy(visibleCells, cell => String(cell.test_version_id)).entries()]
    .map(([key, items]) => ({
      key,
      label: items[0].test_name || items[0].test_namespace || key,
      group: testGroup(items[0]),
    }))
    .sort((a, b) => a.group.localeCompare(b.group) || a.label.localeCompare(b.label, undefined, { numeric: true }));

  const index = new Map();
  for (const cell of visibleCells) {
    index.set(targetKey(cell) + '\u0001' + String(cell.test_version_id), cell);
  }

  const table = h('table', { className: 'matrix' });
  const groupRow = h('tr', { className: 'matrix-groups' }, [
    h('th', { rowspan: '2', text: state.mode === 'hardware-model' ? 'Model' : 'Target' }),
    h('th', { rowspan: '2', text: 'P/F' }),
  ]);

  let currentGroup = null;
  let groupCell = null;
  let groupCount = 0;
  for (const test of tests) {
    if (test.group !== currentGroup) {
      if (groupCell) groupCell.colSpan = String(groupCount);
      currentGroup = test.group;
      groupCount = 1;
      groupCell = h('th', { text: test.group });
      groupRow.append(groupCell);
    } else {
      groupCount += 1;
    }
  }
  if (groupCell) groupCell.colSpan = String(groupCount);

  const testRow = h('tr');
  tests.forEach(test => testRow.append(h('th', { className: 'test-head', text: test.label })));
  table.append(h('thead', {}, [groupRow, testRow]));

  const body = h('tbody');
  for (const target of targets) {
    const rowCells = visibleCells.filter(cell => targetKey(cell) === target.key);
    const pass = rowCells.reduce((sum, cell) => sum + Number(cell.pass || 0), 0);
    const fail = rowCells.reduce((sum, cell) => sum + Number(cell.fail || 0), 0);
    const row = h('tr', {}, [
      h('th', { className: 'sticky-row', text: target.label }),
      h('td', { className: 'mono strong sticky-pf', text: pf(pass, fail) == null ? '—' : n(pf(pass, fail), 0) }),
    ]);

    for (const test of tests) {
      const cell = index.get(target.key + '\u0001' + test.key);
      const status = cellState(cell);
      row.append(h('td', { className: 'matrix-td' }, [
        h('button', {
          type: 'button',
          className: 'matrix-cell cell-' + status,
          title: cell
            ? [cell.test_label, Number(cell.pass || 0) + ' pass', Number(cell.fail || 0) + ' fail', Number(cell.runs || 0) + ' runs'].join(' · ')
            : 'No data',
          on: cell ? { click: () => {
            state.rawCell = cell;
            render(window.__LMTS_PAYLOAD__);
          } } : {},
        }, [
          h('span', { className: 'cell-value', text: metricLabel(cell) }),
          status === 'pass' ? h('i', { className: 'cell-dot' }) : h('span', { className: 'cell-mark', text: status === 'fail' ? '×' : '' }),
        ]),
      ]));
    }
    body.append(row);
  }
  table.append(body);

  const metric = h('select', {
    on: { change: event => {
      state.metric = event.target.value;
      render(window.__LMTS_PAYLOAD__);
    } },
  }, [
    ['total_time', 'Total time'],
    ['ttft', 'TTFT'],
    ['pf', 'P/F'],
  ].map(([value, label]) => h('option', { value, text: label, selected: state.metric === value })));

  const aggregation = h('div', { className: 'segmented' }, [
    h('button', {
      className: state.aggregation === 'median' ? 'active' : '',
      type: 'button',
      text: 'Median',
      on: { click: () => { state.aggregation = 'median'; render(window.__LMTS_PAYLOAD__); } },
    }),
    h('button', {
      className: state.aggregation === 'average' ? 'active' : '',
      type: 'button',
      text: 'Average',
      on: { click: () => { state.aggregation = 'average'; render(window.__LMTS_PAYLOAD__); } },
    }),
  ]);

  return h('section', { className: 'section matrix-section', id: 'matrix' }, [
    h('div', { className: 'section-head matrix-head' }, [
      h('div', {}, [
        h('h2', { text: 'Test matrix' }),
        h('p', { text: 'Click a cell for its contributing PASS/FAIL runs. Individual reports stay out of the primary UI.' }),
      ]),
      h('div', { className: 'matrix-controls' }, [
        h('label', { className: 'mini-control' }, [h('span', { text: 'Metric' }), metric]),
        state.metric === 'pf' ? null : aggregation,
      ].filter(Boolean)),
    ]),
    visibleCells.length
      ? h('div', { className: 'matrix-scroll' }, [table])
      : h('p', { className: 'empty', text: 'No benchmark evidence matches this view.' }),
  ]);
}

function rawPopup(payload) {
  const cell = state.rawCell;
  if (!cell) return null;

  const matching = (payload.records || []).filter(record =>
    String(record.system_id || '') === String(cell.system_id || '')
    && String(record.compute_profile_id || '') === String(cell.compute_profile_id || '')
    && String(record.target_kind || '') === String(cell.target_kind || '')
    && String(record.target_ref || '') === String(cell.target_ref || '')
    && String(record.test_version_id || '') === String(cell.test_version_id || '')
  );

  const pass = Number(cell.pass || 0);
  const fail = Number(cell.fail || 0);

  const table = h('table', { className: 'raw-table' });
  table.append(h('thead', {}, [h('tr', {}, [
    h('th', { text: 'Time' }),
    h('th', { text: 'Outcome' }),
    h('th', { text: 'Score' }),
    h('th', { text: 'TTFT' }),
    h('th', { text: 'Total' }),
    h('th', { text: 'Input' }),
    h('th', { text: 'Output' }),
  ])]));

  const body = h('tbody');
  matching.forEach(record => body.append(h('tr', {}, [
    h('td', { className: 'mono', text: record.started_at ? new Date(record.started_at).toLocaleString() : '—' }),
    h('td', {}, [statusPill(record.outcome === 'pass' ? 'compatible' : 'fail')]),
    h('td', { className: 'mono', text: record.score_percent == null ? '—' : n(record.score_percent, 1) }),
    h('td', { className: 'mono', text: record.ttft_ms == null ? '—' : ms(record.ttft_ms) }),
    h('td', { className: 'mono', text: record.total_time_ms == null ? '—' : ms(record.total_time_ms) }),
    h('td', { className: 'mono', text: record.input_tokens == null ? '—' : n(record.input_tokens, 0) }),
    h('td', { className: 'mono', text: record.output_tokens == null ? '—' : n(record.output_tokens, 0) }),
  ])));
  table.append(body);

  return h('div', {
    className: 'modal-backdrop',
    on: { click: event => {
      if (event.target === event.currentTarget) {
        state.rawCell = null;
        render(window.__LMTS_PAYLOAD__);
      }
    } },
  }, [
    h('section', { className: 'modal' }, [
      h('div', { className: 'modal-head' }, [
        h('div', {}, [
          h('span', { className: 'eyebrow', text: 'RAW RUN EVIDENCE' }),
          h('h2', { text: cell.test_label || 'Test result' }),
          h('p', { text: (cell.target_label || cell.target_ref || 'Target') + ' · ' + (cell.system_label || cell.system_id || 'System') }),
        ]),
        h('button', {
          className: 'modal-close',
          type: 'button',
          text: '×',
          on: { click: () => { state.rawCell = null; render(window.__LMTS_PAYLOAD__); } },
        }),
      ]),
      h('div', { className: 'modal-summary' }, [
        stat(pass, 'pass', 'good'),
        stat(fail, 'fail', 'bad'),
        stat(pf(pass, fail) == null ? '—' : n(pf(pass, fail), 0), 'P/F'),
        stat(cell.median_total_time_ms == null ? '—' : ms(cell.median_total_time_ms), 'median'),
        stat(cell.runs || 0, 'runs'),
      ]),
      matching.length
        ? h('div', { className: 'table-shell' }, [table])
        : h('p', { className: 'empty', text: 'Raw rows are outside the current record window. Increase the API row limit if deeper evidence is needed.' }),
    ]),
  ]);
}

function render(payload) {
  if (!payload || payload.format !== 'lmts.statistics' || payload.version !== 2) {
    throw new Error('Unsupported LMTS statistics payload');
  }

  window.__LMTS_PAYLOAD__ = payload;

  const systems = payload.filters?.options?.systems || [];
  const targets = payload.filters?.options?.targets || [];
  const cells = payload.cells || [];

  if (!state.configurationKey && configurations.length) state.configurationKey = String(configurations[0].value);
  if (!state.targetKey && targets.length) state.targetKey = String(targets[0].value);

  const selectedSystem = configurations.find(item => String(item.value) === String(state.configurationKey));
  const selectedTarget = targets.find(item => String(item.value) === String(state.targetKey));

  const primaryControl = state.mode === 'hardware-model'
    ? selectControl(
        'Select hardware configuration',
        state.configurationKey,
        configurations.map(item => ({ value: item.value, label: item.label || item.value })),
        value => { state.configurationKey = value; state.rawCell = null; render(payload); },
      )
    : selectControl(
        'Select model',
        state.targetKey,
        targets.map(item => ({ value: item.value, label: item.label })),
        value => { state.targetKey = value; state.rawCell = null; render(payload); },
      );

  const activeCells = state.mode === 'hardware-model'
    ? cells.filter(cell => configurationKey(cell) === String(state.configurationKey))
    : cells;

  const header = h('header', { className: 'topbar' }, [
    h('a', { className: 'brand', href: '/', title: 'AIGM' }, [
      h('img', { src: '/images/AIGM-LOGO.png', alt: 'AIGM' }),
      h('span', { className: 'brand-divider' }),
      h('span', { text: 'LMTS' }),
      h('span', { className: 'breadcrumb', text: '/ Benchmark' }),
    ]),
    h('nav', { className: 'nav' }, [
      h('a', { className: 'active', href: '#', text: 'Benchmark' }),
      h('a', { href: '#matrix', text: 'Tests' }),
    ]),
  ]);

  const hero = h('section', { className: 'hero' }, [
    h('div', { className: 'hero-copy' }, [
      h('span', { className: 'eyebrow', text: 'LMTS BENCHMARK' }),
      h('h1', { text: state.mode === 'hardware-model' ? 'Find the best model for your hardware.' : 'Find the best hardware for your model.' }),
      h('p', { text: 'Compare measured benchmark evidence without exposing report plumbing in the primary interface.' }),
    ]),
    h('div', { className: 'hero-controls' }, [
      h('div', { className: 'mode-grid' }, [
        modeButton('hardware-model', 'Hardware → Model', 'Find the strongest tested model for a hardware configuration.'),
        modeButton('model-hardware', 'Model → Hardware', 'Compare one model across tested hardware configurations.'),
      ]),
      primaryControl,
      h('p', { className: 'helper', text: 'PASS/FAIL evidence only. ERROR and CANCELLED material is rejected before visualization.' }),
    ]),
  ]);

  const main = state.mode === 'hardware-model'
    ? rankingView(payload, activeCells, selectedSystem)
    : hardwareRankingView(payload, cells);

  const matrixCells = state.mode === 'hardware-model'
    ? activeCells
    : cells.filter(cell => targetKey(cell) === state.targetKey);

  gui.replace(root, [
    header,
    h('main', { className: 'page' }, [
      hero,
      main,
      matrixView(payload, matrixCells),
    ]),
    rawPopup(payload),
  ].filter(Boolean));
}

async function load() {
  gui.replace(root, [h('p', { className: 'loading', text: 'Loading benchmark evidence…' })]);

  const response = await fetch('./api/stats.php?limit=500', { cache: 'no-store' });
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
  gui.replace(root, [h('pre', { className: 'fatal', text: error.stack || String(error) })]);
});
