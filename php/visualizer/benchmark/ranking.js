import { aggregateTarget, configurationKey, groupBy, targetKey } from './aggregate.js';
import { milliseconds, number } from './format.js';
import { h, stat, statusPill } from './ui.js';

function renderModelRanking(payload, cells, hardwareControls, state, rerender) {
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
      rerender();
    } },
  });

  const status = h('select', {
    on: { change: event => {
      state.status = event.target.value;
      rerender();
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
      h('td', { className: 'mono strong', text: row.summary.pf == null ? '—' : number(row.summary.pf, 0) }),
      h('td', {
        className: 'mono',
        text: row.summary.observedTests + '/' + row.summary.totalTests,
        title: row.summary.passedTests + ' passed · ' + row.summary.failedTests + ' failed',
      }),
      h('td', { className: 'mono', text: row.summary.median == null ? '—' : milliseconds(row.summary.median) }),
      h('td', {}, [statusPill(row.summary.status)]),
      h('td', {}, [
        h('button', {
          className: 'row-open',
          type: 'button',
          text: 'Open',
          on: { click: () => {
            state.targetKey = row.key;
            rerender();
            document.querySelector('#matrix')?.scrollIntoView({ behavior: 'smooth' });
          } },
        }),
      ]),
    ]));
  });
  table.append(body);

  return h('div', {}, [
    h('div', { className: 'stats-strip hardware-stats-strip' }, [
      h('div', { className: 'hardware-strip-controls' }, [hardwareControls]),
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

function renderHardwareRanking(payload, cells, state) {
  const allTests = new Set(cells.map(cell => cell.test_version_id));
  const grouped = groupBy(
    cells,
    cell => targetKey(cell) + '\u0001' + configurationKey(cell),
  );
  const rows = [];

  for (const [key, rowCells] of grouped) {
    const first = rowCells[0];
    rows.push({
      key,
      variantKey: targetKey(first),
      variantLabel: first.target_label || first.target_ref || 'Unknown model',
      configurationKey: configurationKey(first),
      configurationLabel: first.configuration_label || first.system_label || configurationKey(first),
      summary: aggregateTarget(rowCells, allTests.size),
    });
  }

  rows.sort((a, b) => {
    const variantOrder = a.variantLabel.localeCompare(
      b.variantLabel,
      undefined,
      { numeric: true },
    );
    if (variantOrder !== 0) return variantOrder;
    const apf = a.summary.pf ?? -1;
    const bpf = b.summary.pf ?? -1;
    if (bpf !== apf) return bpf - apf;
    return (a.summary.median ?? Infinity) - (b.summary.median ?? Infinity);
  });

  const table = h('table', { className: 'ranking-table' });
  table.append(h('thead', {}, [h('tr', {}, [
    h('th', { text: '#' }),
    h('th', { text: 'Model variant' }),
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
        h('strong', { text: row.variantLabel }),
        h('span', { className: 'subtle block', text: row.variantKey }),
      ]),
      h('td', {}, [
        h('strong', { text: row.configurationLabel }),
        h('span', { className: 'subtle block', text: row.configurationKey }),
      ]),
      h('td', { className: 'mono strong', text: row.summary.pf == null ? '—' : number(row.summary.pf, 0) }),
      h('td', { className: 'mono', text: row.summary.observedTests + '/' + row.summary.totalTests }),
      h('td', { className: 'mono', text: row.summary.median == null ? '—' : milliseconds(row.summary.median) }),
      h('td', {}, [statusPill(row.summary.status)]),
    ]));
  });
  table.append(body);

  const variants = new Set(cells.map(targetKey));
  const configurations = new Set(cells.map(configurationKey));

  return h('div', {}, [
    h('div', { className: 'stats-strip' }, [
      h('div', { className: 'system-summary' }, [
        h('span', { className: 'system-icon', text: '◇' }),
        h('div', {}, [
          h('strong', { text: state.modelFamilyKey ? state.modelFamilyKey.split(':').slice(1).join(':') : 'Selected model family' }),
          h('span', { text: variants.size + ' tested variant' + (variants.size === 1 ? '' : 's') }),
        ]),
      ]),
      stat(configurations.size, 'configurations tested'),
      stat(rows.filter(row => row.summary.status === 'compatible').length, 'compatible', 'good'),
      stat(rows.filter(row => row.summary.status === 'partial').length, 'partial / fails', 'bad'),
    ]),
    h('section', { className: 'section' }, [
      h('div', { className: 'section-head' }, [
        h('div', {}, [
          h('h2', { text: 'Hardware results' }),
          h('p', { text: 'Compare tested variants of the selected model family across hardware configurations.' }),
        ]),
      ]),
      h('div', { className: 'table-shell' }, [table]),
    ]),
  ]);
}

export { renderHardwareRanking, renderModelRanking };
