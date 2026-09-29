import { targetKey } from './aggregate.js';
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
      h('p', { text: 'Start from tested hardware, or from the model you want to run.' }),
      h('div', { className: 'mode-grid landing-modes' }, [
        modeButton(
          state,
          rerender,
          'hardware-model',
          'Hardware → Model',
          'Choose tested hardware and compare models against its benchmark evidence.',
        ),
        modeButton(
          state,
          rerender,
          'model-hardware',
          'Model → Hardware',
          'Choose a model and compare it across tested hardware.',
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
          ? 'Compare models using evidence from systems containing the selected tested hardware.'
          : 'Compare one model across hardware that has actually tested it.',
      }),
    ]),
    h('div', { className: 'workflow-control' }, [primaryControl]),
  ]);
}

function hardwareControls(payload, state, rerender) {
  const hardware = payload.filters?.options?.hardware || [];
  const kinds = [...new Set(hardware.map(item => String(item.kind)))];

  if (!kinds.includes(String(state.hardwareKind)) && kinds.length) {
    state.hardwareKind = kinds[0];
  }

  const options = hardware.filter(item => String(item.kind) === String(state.hardwareKind));
  if (!options.some(item => String(item.value) === String(state.hardwareValue)) && options.length) {
    state.hardwareValue = String(options[0].value);
  }

  const labels = {
    cpu: 'CPU',
    memory: 'Memory',
    gpu: 'GPU',
    gpu_memory: 'GPU Memory',
    npu: 'NPU',
  };

  return h('div', { className: 'hardware-picker' }, [
    selectControl(
      'Hardware type',
      state.hardwareKind,
      kinds.map(kind => ({ value: kind, label: labels[kind] || kind })),
      value => {
        state.hardwareKind = value;
        const first = hardware.find(item => String(item.kind) === String(value));
        state.hardwareValue = first ? String(first.value) : null;
        state.rawCell = null;
        rerender();
      },
    ),
    selectControl(
      'Tested hardware',
      state.hardwareValue,
      options.map(item => ({ value: item.value, label: item.label || item.value })),
      value => {
        state.hardwareValue = value;
        state.rawCell = null;
        rerender();
      },
    ),
  ]);
}

function renderBenchmark(payload, state, rerender) {
  const targets = payload.filters?.options?.targets || [];
  const hardware = payload.filters?.options?.hardware || [];
  const cells = payload.cells || [];
  const header = topbarRoot('benchmark');

  if (!state.mode) {
    replaceRoot([header, landing(state, rerender)]);
    return;
  }

  const selectedHardware = hardware.find(
    item => String(item.kind) === String(state.hardwareKind)
      && String(item.value) === String(state.hardwareValue)
  );

  const primaryControl = state.mode === 'hardware-model'
    ? hardwareControls(payload, state, rerender)
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

  const selectedSystemIds = new Set((selectedHardware?.system_ids || []).map(String));
  const hardwareCells = state.mode === 'hardware-model'
    ? cells.filter(cell => selectedSystemIds.has(String(cell.system_id)))
    : cells;

  const matrixCells = state.mode === 'hardware-model'
    ? hardwareCells
    : cells.filter(cell => targetKey(cell) === state.targetKey);

  const selectedHardwareSummary = selectedHardware
    ? {
        label: (state.hardwareKind === 'gpu_memory' ? 'GPU Memory' : String(state.hardwareKind || '').toUpperCase())
          + ' · ' + (selectedHardware.label || selectedHardware.value),
        value: selectedHardware.value,
      }
    : null;

  const mainContent = state.mode === 'hardware-model'
    ? renderModelRanking(payload, hardwareCells, selectedHardwareSummary, state, rerender)
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
