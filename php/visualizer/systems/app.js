import { aggregateTarget, groupBy, targetKey } from '../benchmark/aggregate.js';
import { milliseconds, number } from '../benchmark/format.js';
import { topbar } from '../benchmark/nav.js';
import { h, replaceRoot, statusPill } from '../benchmark/ui.js';

const state = { selectedSystem: new URLSearchParams(location.search).get('system_id') || null };

function resourceSummary(resources) {
  const grouped = new Map();
  for (const resource of resources || []) {
    const key = String(resource.resource_kind || resource.category || 'other').toUpperCase();
    if (!grouped.has(key)) grouped.set(key, []);
    grouped.get(key).push(resource.label || resource.local_key || 'Unknown');
  }
  return [...grouped.entries()].map(([kind, labels]) => kind + ': ' + labels.join(', ')).join(' · ');
}

function systemTable(systems) {
  const table = h('table', { className: 'ranking-table systems-table' });
  table.append(h('thead', {}, [h('tr', {}, [
    h('th', { text: 'System' }),
    h('th', { text: 'User' }),
    h('th', { text: 'Hardware' }),
    h('th', { text: 'Runs' }),
    h('th', { text: 'Tests' }),
    h('th', { text: 'Models' }),
    h('th', { text: 'Contributors' }),
  ])]));

  const body = h('tbody');
  for (const system of systems) {
    const href = '?system_id=' + encodeURIComponent(system.system_id);
    body.append(h('tr', {}, [
      h('td', {}, [
        h('a', { className: 'entity-link', href, text: system.label || system.system_id }),
        h('span', { className: 'subtle block', text: system.system_id }),
      ]),
      h('td', {}, [
        h('a', {
          className: 'entity-link',
          href: '/iam/' + encodeURIComponent(system.username || system.user_id),
          text: system.username || system.user_id,
        }),
        system.display_name ? h('span', { className: 'subtle block', text: system.display_name }) : null,
      ].filter(Boolean)),
      h('td', { className: 'system-hardware', text: resourceSummary(system.resources) || '—' }),
      h('td', { className: 'mono', text: number(system.test_executions, 0) }),
      h('td', { className: 'mono', text: number(system.unique_tests, 0) }),
      h('td', { className: 'mono', text: number(system.unique_targets, 0) }),
      h('td', { className: 'mono', text: number(system.contributors, 0) }),
    ]));
  }
  table.append(body);
  return table;
}

function modelTable(cells) {
  const modelCells = (cells || []).filter(cell => String(cell.target_kind || '') === 'model');
  const totalTests = new Set(modelCells.map(cell => cell.test_version_id)).size;
  const grouped = groupBy(modelCells, targetKey);
  const rows = [];

  for (const [key, targetCells] of grouped) {
    const first = targetCells[0];
    rows.push({
      key,
      label: first.target_label || first.target_ref || 'Unknown model',
      provider: first.target_kind || 'model',
      summary: aggregateTarget(targetCells, totalTests),
    });
  }

  rows.sort((a, b) => {
    const apf = a.summary.pf ?? -1;
    const bpf = b.summary.pf ?? -1;
    if (bpf !== apf) return bpf - apf;
    if (b.summary.passedTests !== a.summary.passedTests) {
      return b.summary.passedTests - a.summary.passedTests;
    }
    return (a.summary.median ?? Infinity) - (b.summary.median ?? Infinity);
  });

  const table = h('table', { className: 'ranking-table system-detail-table' });
  table.append(h('thead', {}, [h('tr', {}, [
    h('th', { text: '#' }),
    h('th', { text: 'Model' }),
    h('th', { text: 'P/F' }),
    h('th', { text: 'Tests' }),
    h('th', { text: 'Median test time' }),
    h('th', { text: 'State' }),
  ])]));

  const body = h('tbody');
  rows.forEach((row, index) => {
    body.append(h('tr', {}, [
      h('td', { className: 'rank', text: String(index + 1) }),
      h('td', {}, [
        h('strong', { className: 'model-name', text: row.label }),
        h('span', { className: 'subtle block', text: row.provider }),
      ]),
      h('td', {
        className: 'mono strong',
        text: row.summary.pf == null ? '—' : number(row.summary.pf, 0),
      }),
      h('td', {
        className: 'mono',
        text: row.summary.observedTests + '/' + row.summary.totalTests,
        title: row.summary.passedTests + ' passed · ' + row.summary.failedTests + ' failed',
      }),
      h('td', {
        className: 'mono',
        text: row.summary.median == null ? '—' : milliseconds(row.summary.median),
      }),
      h('td', {}, [statusPill(row.summary.status)]),
    ]));
  });
  table.append(body);

  return {
    table,
    count: rows.length,
  };
}

function render(payload, evidence) {
  const selected = payload.systems?.[0] && state.selectedSystem ? payload.systems[0] : null;

  replaceRoot([
    topbar('systems', 'Systems'),
    h('main', { className: 'page explorer-page' }, [
      h('section', { className: 'explorer-head compact-explorer-head' }, [
        selected ? h('h1', { text: selected.label }) : null,
        h('p', {
          text: selected
            ? 'Hardware identity, contributor and benchmark evidence for this system.'
            : 'Browse systems that have contributed valid PASS/FAIL benchmark evidence.',
        }),
        selected ? h('a', { className: 'workflow-back link-button', href: '/lmts/systems/', text: '← All systems' }) : null,
      ].filter(Boolean)),
      selected
        ? h('div', {}, [
            h('section', { className: 'system-detail-summary' }, [
              h('div', {}, [h('span', { text: 'Owner' }), h('strong', { text: selected.username || selected.user_id })]),
              h('div', {}, [h('span', { text: 'Hardware' }), h('strong', { text: resourceSummary(selected.resources) || '—' })]),
              h('div', {}, [h('span', { text: 'Test executions' }), h('strong', { text: number(selected.test_executions, 0) })]),
              h('div', {}, [h('span', { text: 'Unique tests' }), h('strong', { text: number(selected.unique_tests, 0) })]),
            ]),
            (() => {
              const models = modelTable(evidence?.cells || []);
              return h('section', { className: 'section' }, [
                h('div', { className: 'section-head' }, [
                  h('div', {}, [
                    h('h2', { text: 'Model results' }),
                    h('p', {
                      text: models.count
                        ? models.count + ' tested model variant' + (models.count === 1 ? '' : 's') + ' on this system.'
                        : 'No model benchmark evidence on this system.',
                    }),
                  ]),
                ]),
                h('div', { className: 'table-shell' }, [
                  models.count ? models.table : h('p', { className: 'empty', text: 'No model benchmark evidence.' }),
                ]),
              ]);
            })(),
          ])
        : h('section', { className: 'section' }, [
            h('div', { className: 'table-shell' }, [
              payload.systems?.length ? systemTable(payload.systems) : h('p', { className: 'empty', text: 'No systems found.' }),
            ]),
          ]),
    ]),
  ]);
}

async function load() {
  const query = state.selectedSystem ? '?system_id=' + encodeURIComponent(state.selectedSystem) : '';
  const separator = query ? '&' : '?';
  const requests = [
    fetch(
      '../api/systems.php' + query + separator + '_=' + Date.now(),
      { cache: 'no-store' },
    ),
  ];

  if (state.selectedSystem) {
    requests.push(fetch(
      '../api/stats.php?system_id=' + encodeURIComponent(state.selectedSystem) + '&limit=500&_=' + Date.now(),
      { cache: 'no-store' },
    ));
  }

  const [systemsResponse, statsResponse] = await Promise.all(requests);
  if (!systemsResponse.ok) throw new Error('Systems request failed: HTTP ' + systemsResponse.status);

  const payload = await systemsResponse.json();
  if (payload?.format !== 'lmts.systems' || payload?.version !== 1) {
    throw new Error('Unsupported systems payload');
  }

  let evidence = null;
  if (statsResponse) {
    if (!statsResponse.ok) throw new Error('Statistics request failed: HTTP ' + statsResponse.status);
    evidence = await statsResponse.json();
    if (evidence?.format !== 'lmts.statistics' || evidence?.version !== 2) {
      throw new Error('Unsupported statistics payload');
    }
  }

  render(payload, evidence);
}

window.addEventListener('lmts:refresh', () => {
  load().catch(error => console.error('LMTS systems refresh failed', error));
});

load().catch(error => replaceRoot([
  topbar('systems', 'Systems'),
  h('pre', { className: 'fatal', text: error?.stack || String(error) }),
]));
