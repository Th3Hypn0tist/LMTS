import { milliseconds, number, pfScore } from './format.js';

function targetKey(cell) {
  return String(cell?.target_kind || 'unknown') + ':' + String(cell?.target_ref || '');
}

function modelFamilyRef(value) {
  const text = String(value || '').trim();
  const split = text.lastIndexOf(':');
  return split > 0 ? text.slice(0, split) : text;
}

function modelFamilyKey(cell) {
  const kind = String(cell?.target_kind || 'model');
  return kind + ':' + modelFamilyRef(cell?.target_ref || cell?.target_label || '');
}

function modelFamilyLabel(cell) {
  return modelFamilyRef(cell?.target_label || cell?.target_ref || 'Unknown model');
}

function configurationKey(cell) {
  return String(cell?.system_id || '') + ':' + String(cell?.compute_profile_id || '');
}

function groupBy(items, keyFn) {
  const map = new Map();
  for (const item of items ?? []) {
    const key = keyFn(item);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(item);
  }
  return map;
}

function cellState(cell) {
  const pass = Number(cell?.pass || 0);
  const fail = Number(cell?.fail || 0);
  if (pass > 0) return 'pass';
  if (fail > 0) return 'fail';
  return 'unknown';
}

function cellMetric(cell, metric, aggregation) {
  if (!cell) return null;
  if (metric === 'pf') return pfScore(cell.pass, cell.fail);
  if (metric === 'ttft') {
    return aggregation === 'average' ? cell.avg_ttft_ms : cell.median_ttft_ms;
  }
  return aggregation === 'average' ? cell.avg_total_time_ms : cell.median_total_time_ms;
}

function metricLabel(cell, metric, aggregation) {
  const status = cellState(cell);
  if (status === 'fail') return 'FAIL';
  if (status === 'unknown') return '—';
  if (metric === 'pf') {
    const value = pfScore(cell.pass, cell.fail);
    return value == null ? '—' : number(value, 0);
  }
  return milliseconds(cellMetric(cell, metric, aggregation));
}

function testGroup(cell) {
  const namespace = String(cell?.test_namespace || cell?.test_name || 'Other');
  const first = namespace.split(/[.:/]/)[0];
  return first ? first.replace(/[_-]+/g, ' ') : 'Other';
}

function aggregateTarget(cells, totalTests) {
  const pass = cells.reduce((sum, cell) => sum + Number(cell.pass || 0), 0);
  const fail = cells.reduce((sum, cell) => sum + Number(cell.fail || 0), 0);
  const passedTests = cells.filter(cell => Number(cell.pass || 0) > 0).length;
  const failedTests = cells.filter(cell => Number(cell.pass || 0) === 0 && Number(cell.fail || 0) > 0).length;
  const observedTests = new Set(cells.map(cell => cell.test_version_id)).size;

  const medians = cells
    .map(cell => cell.median_total_time_ms)
    .filter(value => value !== null && value !== undefined && value !== '')
    .map(Number)
    .filter(Number.isFinite)
    .sort((a, b) => a - b);

  const median = medians.length
    ? (medians.length % 2
      ? medians[Math.floor(medians.length / 2)]
      : (medians[medians.length / 2 - 1] + medians[medians.length / 2]) / 2)
    : null;

  return {
    pass,
    fail,
    pf: pfScore(pass, fail),
    passedTests,
    failedTests,
    observedTests,
    totalTests,
    median,
    status: failedTests > 0 ? 'partial' : (passedTests > 0 ? 'compatible' : 'unknown'),
  };
}

export {
  aggregateTarget,
  cellMetric,
  cellState,
  configurationKey,
  groupBy,
  metricLabel,
  modelFamilyKey,
  modelFamilyLabel,
  targetKey,
  testGroup,
};
