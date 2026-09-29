function number(value, digits = 2) {
  if (value == null || value === '') return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return null;
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(parsed);
}

function milliseconds(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return '—';
  if (parsed >= 1000) return number(parsed / 1000, 2) + ' s';
  return number(parsed, 0) + ' ms';
}

function pfScore(pass, fail) {
  const passed = Number(pass || 0);
  const failed = Number(fail || 0);
  const total = passed + failed;
  return total ? (passed / total) * 100 : null;
}

export { number, milliseconds, pfScore };
