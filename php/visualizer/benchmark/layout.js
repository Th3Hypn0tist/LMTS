import { configurationKey, targetKey } from './aggregate.js';
import { renderMatrix } from './matrix.js';
import { topbarRoot } from './nav.js';
import { renderHardwareRanking, renderModelRanking } from './ranking.js';
import { renderRawEvidence } from './raw-evidence.js';
import { h, replaceRoot, selectControl } from './ui.js';

function modeButton(state, rerender, id, title, subtitle) {
  return h('button', {
    className: 'mode-card',
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

function backButton(state, rerender) {
  return h('button', {
    className: 'workflow-back',
    type: 'button',
    text: '← Benchmark',
    on: { click: () => {
      state.mode = null;
      state.rawCell = null;
      rerender();
    } },
  });
}

function landing(state, rerender) {
  return h('main', { className: 'page landing-page' }, [
    h('section', { className: 'landing-hero' }, [
      h('span', { className: 'eyebrow', text: 'LMTS BENCHMARK' }),
      h('h1', { text: 'Find what actually works.' }),
      h('p', { text: 'Start from the hardware you have, or from the model you want to run.' }),
      h('div', { className: 'mode-grid landing-modes' }, [
        modeButton(
          state,
          rerender,
          'hardware-model',
          'Hardware → Model',
          'Choose a tested system and compare models against its benchmark evidence.',
        ),
        modeButton(
          state,
          rerender,
          'model-hardware',
          'Model → Hardware',
          'Choose a model and compare it across tested systems.',
        ),
      ]),
    ]),
  ]);
}

function workflowHero(state, rerender, primaryControl) {
  return h('section', { className: 'workflow-head' }, [
    h('div', { className: 'workflow-title' }, [
      backButton(state, rerender),
      h('span', { className: 'eyebrow', text: 'LMTS BENCHMARK' }),
      h('h1', {
        text: state.mode === 'hardware-model'
          ? 'Hardware → Model'
          : 'Model → Hardware',
      }),
      h('p', {
        text: state.mode === 'hardware-model'
          ? 'Compare models using evidence measured on the selected system.'
          : 'Compare one model across systems that have actually tested it.',
      }),
    ]),
    h('div', { className: 'workflow-control' }, [primaryControl]),
  ]);
}

function renderBenchmark(payload, state, rerender) {
  const configurations = payload.filters?.options?.configurations || [];
  const targets = payload.filters?.options?.targets || [];
  const cells = payload.cells || [];
  const header = topbarRoot('benchmark');

  if (!state.mode) {
    replaceRoot([header, landing(state, rerender)]);
    return;
  }

  const selectedConfiguration = configurations.find(
    item => String(item.value) === String(state.configurationKey)
  );

  const primaryControl = state.mode === 'hardware-model'
    ? selectControl(
        'System / compute profile',
        state.configurationKey,
        configurations.map(item => ({ value: item.value, label: item.label || item.value })),
        value => {
          state.configurationKey = value;
          state.rawCell = null;
          rerender();
        },
      )
    : selectControl(
        'Model',
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

  const mainContent = state.mode === 'hardware-model'
    ? renderModelRanking(payload, configurationCells, selectedConfiguration, state, rerender)
    : renderHardwareRanking(payload, cells, state);

  replaceRoot([
    header,
    h('main', { className: 'page' }, [
      workflowHero(state, rerender, primaryControl),
      mainContent,
      renderMatrix(matrixCells, state, rerender),
    ]),
    renderRawEvidence(payload, state, rerender),
  ].filter(Boolean));
}

export { renderBenchmark };
