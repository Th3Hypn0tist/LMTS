import { milliseconds, number, pfScore } from './format.js';
import { h, stat, statusPill } from './ui.js';

function renderRawEvidence(payload, state, rerender) {
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
  const score = pfScore(pass, fail);

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
    h('td', { className: 'mono', text: record.score_percent == null ? '—' : number(record.score_percent, 1) }),
    h('td', { className: 'mono', text: record.ttft_ms == null ? '—' : milliseconds(record.ttft_ms) }),
    h('td', { className: 'mono', text: record.total_time_ms == null ? '—' : milliseconds(record.total_time_ms) }),
    h('td', { className: 'mono', text: record.input_tokens == null ? '—' : number(record.input_tokens, 0) }),
    h('td', { className: 'mono', text: record.output_tokens == null ? '—' : number(record.output_tokens, 0) }),
  ])));
  table.append(body);

  function close() {
    state.rawCell = null;
    rerender();
  }

  return h('div', {
    className: 'modal-backdrop',
    on: { click: event => {
      if (event.target === event.currentTarget) close();
    } },
  }, [
    h('section', { className: 'modal' }, [
      h('div', { className: 'modal-head' }, [
        h('div', {}, [
          h('span', { className: 'eyebrow', text: 'RAW RUN EVIDENCE' }),
          h('h2', { text: cell.test_label || 'Test result' }),
          h('p', { text: (cell.target_label || cell.target_ref || 'Target') + ' · ' + (cell.configuration_label || cell.system_label || cell.system_id || 'System') }),
        ]),
        h('button', { className: 'modal-close', type: 'button', text: '×', on: { click: close } }),
      ]),
      h('div', { className: 'modal-summary' }, [
        stat(pass, 'pass', 'good'),
        stat(fail, 'fail', 'bad'),
        stat(score == null ? '—' : number(score, 0), 'P/F'),
        stat(cell.median_total_time_ms == null ? '—' : milliseconds(cell.median_total_time_ms), 'median'),
        stat(cell.runs || 0, 'runs'),
      ]),
      matching.length
        ? h('div', { className: 'table-shell' }, [table])
        : h('p', { className: 'empty', text: 'Raw rows are outside the current record window.' }),
    ]),
  ]);
}

export { renderRawEvidence };
