async function fetchBenchmark() {
  const response = await fetch('./api/stats.php?limit=500', { cache: 'no-store' });
  if (!response.ok) {
    let detail = 'HTTP ' + response.status;
    try {
      const payload = await response.json();
      if (payload?.error) detail += ': ' + payload.error;
    } catch {}
    throw new Error('Statistics request failed: ' + detail);
  }

  const payload = await response.json();
  if (!payload || payload.format !== 'lmts.statistics' || payload.version !== 2) {
    throw new Error('Unsupported LMTS statistics payload');
  }
  return payload;
}

export { fetchBenchmark };
