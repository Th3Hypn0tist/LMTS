import { fetchBenchmark } from './benchmark/api.js';
import { renderBenchmark } from './benchmark/layout.js';
import { initializeState, state } from './benchmark/state.js';
import { h, replaceRoot } from './benchmark/ui.js';

let payload = null;

function rerender() {
  if (!payload) return;
  renderBenchmark(payload, state, rerender);
}

async function start() {
  replaceRoot([
    h('p', { className: 'loading', text: 'Loading benchmark evidence…' }),
  ]);

  payload = await fetchBenchmark();
  initializeState(payload);
  rerender();
}

start().catch(error => {
  replaceRoot([
    h('pre', {
      className: 'fatal',
      text: error?.stack || String(error),
    }),
  ]);
});
