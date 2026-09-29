const state = {
  mode: null,
  configurationKey: null,
  hardwarePreset: null,
  hardwareSelections: {
    cpu: null,
    memory: null,
    gpu: null,
    gpu_memory: null,
    npu: null,
  },
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
  const systems = payload?.filters?.options?.systems ?? [];
  const targets = payload?.filters?.options?.targets ?? [];

  if (!state.configurationKey && configurations.length) {
    state.configurationKey = String(configurations[0].value);
  }
  if (!state.targetKey && targets.length) {
    state.targetKey = String(targets[0].value);
  }

  if (!state.hardwarePreset && systems.length) {
    state.hardwarePreset = String(systems[0].system_id);
    for (const kind of Object.keys(state.hardwareSelections)) {
      const matches = hardware.filter(item =>
        String(item.kind) === kind
        && (item.system_ids || []).map(String).includes(state.hardwarePreset)
      );
      state.hardwareSelections[kind] = matches.length === 1 ? String(matches[0].value) : null;
    }
  }
}

export { state, initializeState };
