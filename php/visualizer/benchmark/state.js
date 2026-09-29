const state = {
  mode: null,
  configurationKey: null,
  hardwareKind: null,
  hardwareValue: null,
  targetKey: null,
  search: '',
  status: 'all',
  metric: 'total_time',
  aggregation: 'median',
  matrixCategory: 'all',
  rawCell: null,
};

function initializeState(payload) {
  const configurations = payload?.filters?.options?.configurations ?? [];
  const hardware = payload?.filters?.options?.hardware ?? [];
  const targets = payload?.filters?.options?.targets ?? [];

  if (!state.configurationKey && configurations.length) {
    state.configurationKey = String(configurations[0].value);
  }
  if (!state.hardwareKind && hardware.length) {
    state.hardwareKind = String(hardware[0].kind);
  }
  const hardwareForKind = hardware.filter(item => String(item.kind) === String(state.hardwareKind));
  if ((!state.hardwareValue || !hardwareForKind.some(item => String(item.value) === String(state.hardwareValue))) && hardwareForKind.length) {
    state.hardwareValue = String(hardwareForKind[0].value);
  }
  if (!state.targetKey && targets.length) {
    state.targetKey = String(targets[0].value);
  }
}

export { state, initializeState };
