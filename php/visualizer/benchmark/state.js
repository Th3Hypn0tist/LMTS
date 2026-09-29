const state = {
  mode: null,
  configurationKey: null,
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
  const targets = payload?.filters?.options?.targets ?? [];

  if (!state.configurationKey && configurations.length) {
    state.configurationKey = String(configurations[0].value);
  }
  if (!state.targetKey && targets.length) {
    state.targetKey = String(targets[0].value);
  }
}

export { state, initializeState };
