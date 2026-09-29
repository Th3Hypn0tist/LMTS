import { cellState, groupBy, metricLabel, targetKey, testGroup } from './aggregate.js';
import { number, pfScore } from './format.js';
import { h } from './ui.js';

function renderMatrix(cells, state, rerender) {
  const visibleCells = cells;

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
    h('th', { rowSpan: 2, text: state.mode === 'hardware-model' ? 'Model' : 'Target' }),
    h('th', { rowSpan: 2, text: 'P/F' }),
  ]);

  let currentGroup = null;
  let groupCell = null;
  let groupCount = 0;

  for (const test of tests) {
    if (test.group !== currentGroup) {
      if (groupCell) groupCell.colSpan = groupCount;
      currentGroup = test.group;
      groupCount = 1;
      groupCell = h('th', { text: test.group });
      groupRow.append(groupCell);
    } else {
      groupCount += 1;
    }
  }
  if (groupCell) groupCell.colSpan = groupCount;

  const testRow = h('tr');
  tests.forEach(test => testRow.append(h('th', { className: 'test-head', text: test.label })));
  table.append(h('thead', {}, [groupRow, testRow]));

  const body = h('tbody');
  for (const target of targets) {
    const rowCells = visibleCells.filter(cell => targetKey(cell) === target.key);
    const pass = rowCells.reduce((sum, cell) => sum + Number(cell.pass || 0), 0);
    const fail = rowCells.reduce((sum, cell) => sum + Number(cell.fail || 0), 0);
    const score = pfScore(pass, fail);

    const row = h('tr', {}, [
      h('th', { className: 'sticky-row', text: target.label }),
      h('td', { className: 'mono strong sticky-pf', text: score == null ? '—' : number(score, 0) }),
    ]);

    for (const test of tests) {
      const cell = index.get(target.key + '\u0001' + test.key);
      const status = cellState(cell);
      row.append(h('td', { className: 'matrix-td' }, [
        h('button', {
          type: 'button',
          className: 'matrix-cell cell-' + status,
          disabled: !cell,
          title: cell
            ? [cell.test_label, Number(cell.pass || 0) + ' pass', Number(cell.fail || 0) + ' fail', Number(cell.runs || 0) + ' runs'].join(' · ')
            : 'No data',
          on: cell ? { click: () => {
            state.rawCell = cell;
            rerender();
          } } : {},
        }, [
          h('span', { className: 'cell-value', text: metricLabel(cell, state.metric, state.aggregation) }),
          status === 'pass'
            ? h('i', { className: 'cell-dot' })
            : h('span', { className: 'cell-mark', text: status === 'fail' ? '×' : '' }),
        ]),
      ]));
    }
    body.append(row);
  }

  table.append(body);

  const metric = h('select', {
    on: { change: event => {
      state.metric = event.target.value;
      rerender();
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
      on: { click: () => { state.aggregation = 'median'; rerender(); } },
    }),
    h('button', {
      className: state.aggregation === 'average' ? 'active' : '',
      type: 'button',
      text: 'Average',
      on: { click: () => { state.aggregation = 'average'; rerender(); } },
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

export { renderMatrix };
