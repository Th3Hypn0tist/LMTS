import { aggregateTarget, configurationKey, groupBy, targetKey } from './aggregate.js';
import { milliseconds, number } from './format.js';
import { h, stat, statusPill } from './ui.js';

function renderModelRanking(payload, cells, selectedConfiguration, state, rerender) {
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
    h('div', { className: 'stats-strip' }, [
      h('div', { className: 'system-summary' }, [
        h('span', { className: 'system-icon', text: '▣' }),
        h('div', {}, [
          h('strong', { text: selectedConfiguration?.label || 'Hardware configuration' }),
          h('span', { text: selectedConfiguration?.value || '' }),
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

function renderHardwareRanking(payload, cells, state) {
  const selectedTarget = state.targetKey;
  const modelCells = cells.filter(cell => targetKey(cell) === selectedTarget);
  const byConfiguration = groupBy(modelCells, configurationKey);
  const allTests = new Set(modelCells.map(cell => cell.test_version_id));
  const rows = [];

  for (const [configKey, configurationCells] of byConfiguration) {
    const first = configurationCells[0];
    rows.push({
      key: configKey,
      label: first.configuration_label || first.system_label || configKey,
      summary: aggregateTarget(configurationCells, allTests.size),
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
        h('span', { className: 'subtle block', text: row.key }),
      ]),
      h('td', { className: 'mono strong', text: row.summary.pf == null ? '—' : number(row.summary.pf, 0) }),
      h('td', { className: 'mono', text: row.summary.observedTests + '/' + row.summary.totalTests }),
      h('td', { className: 'mono', text: row.summary.median == null ? '—' : milliseconds(row.summary.median) }),
      h('td', {}, [statusPill(row.summary.status)]),
    ]));
  });
  table.append(body);

  const target = payload.filters?.options?.targets?.find(item => item.value === selectedTarget);

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

export { renderHardwareRanking, renderModelRanking };
