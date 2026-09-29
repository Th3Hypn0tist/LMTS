import { targetKey } from './aggregate.js';
import { renderMatrix } from './matrix.js';
import { topbarRoot } from './nav.js';
import { renderHardwareRanking, renderModelRanking } from './ranking.js';
import { renderRawEvidence } from './raw-evidence.js';
import { h, replaceRoot, selectControl } from './ui.js';

const HARDWARE_KINDS = [
  ['cpu', 'CPU'],
  ['memory', 'Memory'],
  ['gpu', 'GPU'],
  ['gpu_memory', 'GPU Memory'],
  ['npu', 'NPU'],
];

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
          'Choose tested hardware parts and compare models against matching benchmark evidence.',
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
          ? 'Select hardware parts independently. Presets only fill these selections for you.'
          : 'Compare one model across hardware that has actually tested it.',
      }),
    ]),
    h('div', { className: 'workflow-control' }, [primaryControl]),
  ]);
}

function hardwareForSystem(hardware, systemId, kind) {
  return hardware.filter(item =>
    String(item.kind) === kind
    && (item.system_ids || []).map(String).includes(String(systemId))
  );
}

function applyPreset(payload, state, systemId) {
  const hardware = payload.filters?.options?.hardware || [];
  state.hardwarePreset = systemId || null;

  for (const [kind] of HARDWARE_KINDS) {
    const matches = systemId ? hardwareForSystem(hardware, systemId, kind) : [];
    state.hardwareSelections[kind] = matches.length === 1
      ? String(matches[0].value)
      : null;
  }
}

function hardwareControls(payload, state, rerender) {
  const hardware = payload.filters?.options?.hardware || [];
  const systems = payload.filters?.options?.systems || [];

  const facetControls = HARDWARE_KINDS.map(([kind, label]) => {
    const options = hardware.filter(item => String(item.kind) === kind);
    if (!options.length) return null;

    return selectControl(
      label,
      state.hardwareSelections[kind],
      [
        { value: '', label: 'Any' },
        ...options.map(item => ({
          value: String(item.value),
          label: item.label || String(item.value),
        })),
      ],
      value => {
        state.hardwareSelections[kind] = value || null;
        state.hardwarePreset = null;
        state.rawCell = null;
        rerender();
      },
    );
  }).filter(Boolean);

  const presetControl = selectControl(
    'Preset',
    state.hardwarePreset,
    [
      { value: '', label: 'Custom' },
      ...systems.map(item => ({
        value: String(item.system_id),
        label: item.label || String(item.system_id),
      })),
    ],
    value => {
      if (!value) {
        state.hardwarePreset = null;
        rerender();
        return;
      }
      applyPreset(payload, state, value);
      state.rawCell = null;
      rerender();
    },
  );

  return h('div', { className: 'hardware-facets' }, [
    h('div', { className: 'hardware-facet-list' }, facetControls),
    h('div', { className: 'hardware-preset' }, [presetControl]),
  ]);
}

function matchingSystemIds(payload, state) {
  const systems = payload.filters?.options?.systems || [];
  const hardware = payload.filters?.options?.hardware || [];
  let matches = new Set(systems.map(item => String(item.system_id)));

  for (const [kind] of HARDWARE_KINDS) {
    const selected = state.hardwareSelections[kind];
    if (!selected) continue;

    const option = hardware.find(item =>
      String(item.kind) === kind
      && String(item.value) === String(selected)
    );
    const systemsForOption = new Set((option?.system_ids || []).map(String));
    matches = new Set([...matches].filter(systemId => systemsForOption.has(systemId)));
  }

  return matches;
}

function hardwareSummary(payload, state) {
  const hardware = payload.filters?.options?.hardware || [];
  const parts = [];

  for (const [kind, label] of HARDWARE_KINDS) {
    const selected = state.hardwareSelections[kind];
    if (!selected) continue;

    const option = hardware.find(item =>
      String(item.kind) === kind
      && String(item.value) === String(selected)
    );
    parts.push(label + ': ' + (option?.label || selected));
  }

  return {
    label: parts.length ? parts.join(' · ') : 'All tested hardware',
    value: parts.length ? parts.length + ' hardware filter' + (parts.length === 1 ? '' : 's') : 'No hardware filters',
  };
}

function renderBenchmark(payload, state, rerender) {
  const targets = payload.filters?.options?.targets || [];
  const cells = payload.cells || [];
  const header = topbarRoot('benchmark');

  if (!state.mode) {
    replaceRoot([header, landing(state, rerender)]);
    return;
  }

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

  const selectedSystemIds = matchingSystemIds(payload, state);
  const hardwareCells = state.mode === 'hardware-model'
    ? cells.filter(cell => selectedSystemIds.has(String(cell.system_id)))
    : cells;

  const matrixCells = state.mode === 'hardware-model'
    ? hardwareCells
    : cells.filter(cell => targetKey(cell) === state.targetKey);

  const mainContent = state.mode === 'hardware-model'
    ? renderModelRanking(payload, hardwareCells, hardwareSummary(payload, state), state, rerender)
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
