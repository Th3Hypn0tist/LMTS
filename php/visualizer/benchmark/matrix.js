import { cellState, groupBy, metricLabel, targetKey, testGroup } from './aggregate.js';
import { number, pfScore } from './format.js';
import { h } from './ui.js';

function groupSlug(value) {
  return String(value || 'other').toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
}

function setMatrixCategory(section, category) {
  section.dataset.matrixCategory = category;

  for (const button of section.querySelectorAll('.matrix-category-button')) {
    button.classList.toggle('active', button.dataset.group === category);
  }

  for (const cell of section.querySelectorAll('[data-matrix-group]')) {
    const group = cell.dataset.matrixGroup;
    cell.classList.toggle('is-hidden', category !== 'all' && group !== category);
  }
}

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

  const groups = [...new Set(tests.map(test => test.group))];
  const index = new Map();
  for (const cell of visibleCells) {
    index.set(targetKey(cell) + '\u0001' + String(cell.test_version_id), cell);
  }

  const table = h('table', { className: 'matrix' });
  const head = h('tr', {}, [
    h('th', { text: state.mode === 'hardware-model' ? 'Model' : 'Target' }),
    h('th', { text: 'P/F' }),
  ]);

  for (const test of tests) {
    const slug = groupSlug(test.group);
    head.append(h('th', {
      className: 'test-head matrix-group-' + slug,
      text: test.label,
      dataset: { matrixGroup: slug },
    }));
  }
  table.append(h('thead', {}, [head]));

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
      const slug = groupSlug(test.group);
      const cell = index.get(target.key + '\u0001' + test.key);
      const status = cellState(cell);
      row.append(h('td', {
        className: 'matrix-td matrix-group-' + slug,
        dataset: { matrixGroup: slug },
      }, [
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
    ['input_tokens', 'Input tokens'],
    ['output_tokens', 'Output tokens'],
    ['gpu_power_w', 'GPU power'],
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

  const section = h('section', {
    className: 'section matrix-section',
    id: 'matrix',
    dataset: { matrixCategory: state.matrixCategory || 'all' },
  });

  const categoryNav = h('div', { className: 'matrix-category-nav' }, [
    h('div', { className: 'matrix-category-list' }, groups.map(group => {
      const slug = groupSlug(group);
      return h('button', {
        type: 'button',
        className: 'matrix-category-button' + ((state.matrixCategory || 'all') === slug ? ' active' : ''),
        text: group,
        dataset: { group: slug },
        on: { click: () => {
          state.matrixCategory = slug;
          setMatrixCategory(section, slug);
        } },
      });
    })),
    h('button', {
      type: 'button',
      className: 'matrix-category-button matrix-category-all' + ((state.matrixCategory || 'all') === 'all' ? ' active' : ''),
      text: 'All',
      dataset: { group: 'all' },
      on: { click: () => {
        state.matrixCategory = 'all';
        setMatrixCategory(section, 'all');
      } },
    }),
  ]);

  section.append(
    h('div', { className: 'section-head matrix-head' }, [
      h('div', {}, [
        h('h2', { text: 'Test matrix' }),
        h('p', { text: 'Click a category to show only that test group. All shows the complete matrix.' }),
      ]),
      h('div', { className: 'matrix-controls' }, [
        h('label', { className: 'mini-control' }, [h('span', { text: 'Metric' }), metric]),
        state.metric === 'pf' ? null : aggregation,
      ].filter(Boolean)),
    ]),
    categoryNav,
    visibleCells.length
      ? h('div', { className: 'matrix-scroll' }, [table])
      : h('p', { className: 'empty', text: 'No benchmark evidence matches this view.' }),
  );

  queueMicrotask(() => setMatrixCategory(section, state.matrixCategory || 'all'));
  return section;
}

export { renderMatrix };
