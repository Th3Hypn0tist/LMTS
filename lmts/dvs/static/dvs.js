async function getJson(path) {
  const response = await fetch(path, { cache: 'no-store' });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `${response.status}`);
  return payload;
}

async function main() {
  const templates = await getJson('/api/input-templates');
  const presets = await getJson('/api/visualization-presets');
  document.querySelector('#templates').textContent = JSON.stringify(templates, null, 2);
  document.querySelector('#presets').textContent = JSON.stringify(presets, null, 2);
}

main().catch(error => {
  document.body.dataset.error = 'true';
  console.error(error);
});
