import { number, pfScore } from '../benchmark/format.js';
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

function detailTable(rows) {
  const table = h('table', { className: 'ranking-table system-detail-table' });
  table.append(h('thead', {}, [h('tr', {}, [
    h('th', { text: 'Test' }),
    h('th', { text: 'Model / target' }),
    h('th', { text: 'Uploader' }),
    h('th', { text: 'Runs' }),
    h('th', { text: 'P/F' }),
    h('th', { text: 'State' }),
  ])]));

  const body = h('tbody');
  for (const row of rows) {
    const score = pfScore(row.pass, row.fail);
    body.append(h('tr', {}, [
      h('td', {}, [
        h('strong', { text: row.test_name || row.test_namespace || row.test_version_id || 'Unknown test' }),
        h('span', { className: 'subtle block', text: row.test_version ? '@ ' + row.test_version : '' }),
      ]),
      h('td', { text: row.target_label || row.target_ref || row.target_kind || '—' }),
      h('td', {}, [
        h('a', {
          className: 'entity-link',
          href: '/iam/' + encodeURIComponent(row.username || row.tester_user_id),
          text: row.username || row.tester_user_id || '—',
        }),
      ]),
      h('td', { className: 'mono', text: number(row.runs, 0) }),
      h('td', { className: 'mono strong', text: score == null ? '—' : number(score, 0) }),
      h('td', {}, [statusPill(Number(row.pass || 0) > 0 ? 'compatible' : 'fail')]),
    ]));
  }
  table.append(body);
  return table;
}

function render(payload) {
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
            h('section', { className: 'section' }, [
              h('div', { className: 'section-head' }, [
                h('div', {}, [
                  h('h2', { text: 'Benchmark evidence' }),
                  h('p', { text: 'Tests and targets measured on this system, grouped by uploader.' }),
                ]),
              ]),
              h('div', { className: 'table-shell' }, [
                payload.details?.length ? detailTable(payload.details) : h('p', { className: 'empty', text: 'No benchmark evidence.' }),
              ]),
            ]),
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
  const response = await fetch(
    '../api/systems.php' + query + separator + '_=' + Date.now(),
    { cache: 'no-store' },
  );
  if (!response.ok) throw new Error('Systems request failed: HTTP ' + response.status);
  const payload = await response.json();
  if (payload?.format !== 'lmts.systems' || payload?.version !== 1) throw new Error('Unsupported systems payload');
  render(payload);
}

window.addEventListener('lmts:refresh', () => {
  load().catch(error => console.error('LMTS systems refresh failed', error));
});

load().catch(error => replaceRoot([
  topbar('systems', 'Systems'),
  h('pre', { className: 'fatal', text: error?.stack || String(error) }),
]));
