import { configurationKey, targetKey } from './aggregate.js';
import { renderMatrix } from './matrix.js';
import { renderHardwareRanking, renderModelRanking } from './ranking.js';
import { renderRawEvidence } from './raw-evidence.js';
import { h, replaceRoot, selectControl } from './ui.js';

function modeButton(state, rerender, id, title, subtitle) {
  const active = state.mode === id;
  return h('button', {
    className: 'mode-card' + (active ? ' active' : ''),
    type: 'button',
    on: { click: () => {
      state.mode = id;
      state.rawCell = null;
      rerender();
    } },
  }, [
    h('span', { className: 'mode-icon', text: id === 'hardware-model' ? '▣' : '◇' }),
    h('span', { className: 'mode-copy' }, [
      h('strong', { text: title }),
      h('small', { text: subtitle }),
    ]),
  ]);
}

function renderBenchmark(payload, state, rerender) {
  const configurations = payload.filters?.options?.configurations || [];
  const targets = payload.filters?.options?.targets || [];
  const cells = payload.cells || [];

  const selectedConfiguration = configurations.find(
    item => String(item.value) === String(state.configurationKey)
  );

  const primaryControl = state.mode === 'hardware-model'
    ? selectControl(
        'Select hardware configuration',
        state.configurationKey,
        configurations.map(item => ({ value: item.value, label: item.label || item.value })),
        value => {
          state.configurationKey = value;
          state.rawCell = null;
          rerender();
        },
      )
    : selectControl(
        'Select model',
        state.targetKey,
        targets.map(item => ({ value: item.value, label: item.label })),
        value => {
          state.targetKey = value;
          state.rawCell = null;
          rerender();
        },
      );

  const configurationCells = state.mode === 'hardware-model'
    ? cells.filter(cell => configurationKey(cell) === String(state.configurationKey))
    : cells;

  const matrixCells = state.mode === 'hardware-model'
    ? configurationCells
    : cells.filter(cell => targetKey(cell) === state.targetKey);

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
      h('h1', {
        text: state.mode === 'hardware-model'
          ? 'Find the best model for your hardware.'
          : 'Find the best hardware for your model.',
      }),
      h('p', { text: 'Compare measured benchmark evidence without exposing report plumbing in the primary interface.' }),
    ]),
    h('div', { className: 'hero-controls' }, [
      h('div', { className: 'mode-grid' }, [
        modeButton(state, rerender, 'hardware-model', 'Hardware → Model', 'Find the strongest tested model for a hardware configuration.'),
        modeButton(state, rerender, 'model-hardware', 'Model → Hardware', 'Compare one model across tested hardware configurations.'),
      ]),
      primaryControl,
      h('p', { className: 'helper', text: 'PASS/FAIL evidence only. ERROR and CANCELLED material is rejected before visualization.' }),
    ]),
  ]);

  const mainContent = state.mode === 'hardware-model'
    ? renderModelRanking(payload, configurationCells, selectedConfiguration, state, rerender)
    : renderHardwareRanking(payload, cells, state);

  replaceRoot([
    header,
    h('main', { className: 'page' }, [
      hero,
      mainContent,
      renderMatrix(matrixCells, state, rerender),
    ]),
    renderRawEvidence(payload, state, rerender),
  ].filter(Boolean));
}

export { renderBenchmark };
