import { number, pfScore } from '../benchmark/format.js';
import { topbar } from '../benchmark/nav.js';
import { h, replaceRoot } from '../benchmark/ui.js';

function rankingsTable(rows) {
  const table = h('table', { className: 'ranking-table contributor-table' });
  table.append(h('thead', {}, [h('tr', {}, [
    h('th', { text: '#' }),
    h('th', { text: 'Contributor' }),
    h('th', { text: 'Test executions' }),
    h('th', { text: 'Unique tests' }),
    h('th', { text: 'Models' }),
    h('th', { text: 'Systems' }),
    h('th', { text: 'P/F' }),
  ])]));

  const body = h('tbody');
  rows.forEach((row, index) => {
    const score = pfScore(row.pass, row.fail);
    body.append(h('tr', {}, [
      h('td', { className: 'rank contributor-rank', text: String(index + 1) }),
      h('td', {}, [
        h('a', {
          className: 'entity-link contributor-name',
          href: '/iam/' + encodeURIComponent(row.username || row.user_id),
          text: row.username || row.user_id,
        }),
        row.display_name ? h('span', { className: 'subtle block', text: row.display_name }) : null,
      ].filter(Boolean)),
      h('td', { className: 'mono strong', text: number(row.test_executions, 0) }),
      h('td', { className: 'mono', text: number(row.unique_tests, 0) }),
      h('td', { className: 'mono', text: number(row.unique_targets, 0) }),
      h('td', { className: 'mono', text: number(row.systems, 0) }),
      h('td', { className: 'mono', text: score == null ? '—' : number(score, 0) }),
    ]));
  });
  table.append(body);
  return table;
}

function render(payload) {
  const total = (payload.rows || []).reduce((sum, row) => sum + Number(row.test_executions || 0), 0);
  replaceRoot([
    topbar('rankings', 'Rankings'),
    h('main', { className: 'page explorer-page' }, [
      h('section', { className: 'explorer-head ranking-head compact-explorer-head' }, [
        h('p', { text: 'Who has contributed the most valid benchmark evidence?' }),
      ]),
      h('div', { className: 'ranking-summary' }, [
        h('strong', { text: number(total, 0) }),
        h('span', { text: 'valid PASS/FAIL test executions published' }),
      ]),
      h('section', { className: 'section' }, [
        h('div', { className: 'table-shell' }, [
          payload.rows?.length ? rankingsTable(payload.rows) : h('p', { className: 'empty', text: 'No contributor data yet.' }),
        ]),
      ]),
    ]),
  ]);
}

async function load() {
  const response = await fetch(
    '../api/rankings.php?_=' + Date.now(),
    { cache: 'no-store' },
  );
  if (!response.ok) throw new Error('Rankings request failed: HTTP ' + response.status);
  const payload = await response.json();
  if (payload?.format !== 'lmts.rankings' || payload?.version !== 1) throw new Error('Unsupported rankings payload');
  render(payload);
}

window.addEventListener('lmts:refresh', () => {
  load().catch(error => console.error('LMTS rankings refresh failed', error));
});

load().catch(error => replaceRoot([
  topbar('rankings', 'Rankings'),
  h('pre', { className: 'fatal', text: error?.stack || String(error) }),
]));
