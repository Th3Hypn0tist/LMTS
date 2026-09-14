import { S3DVisualPlanRenderer } from '/static/visualizer.js';

async function getJson(path) {
  const response = await fetch(path, { cache: 'no-store' });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `${response.status}`);
  return payload;
}

async function postJson(path, body) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `${response.status}`);
  return payload;
}

function option(select, value, label) {
  const item = document.createElement('option');
  item.value = value;
  item.textContent = label;
  select.append(item);
}

function sourceDocument() {
  const raw = document.querySelector('#source').value.trim();
  if (!raw) throw new Error('Source JSON is required');
  const value = JSON.parse(raw);
  if (value == null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Source JSON root must be an object');
  }
  return value;
}

function setStatus(text, mode = '') {
  const node = document.querySelector('#status');
  node.textContent = text;
  node.className = `status ${mode}`.trim();
}

function setViewerMessage(text) {
  document.querySelector('#viewer-message').textContent = text;
}

function compatiblePresets(templateId, templates, presets) {
  const template = templates.find(item => item.id === templateId);
  if (!template) return [];
  return presets.filter(item => (
    item.input_template_ref === template.id && item.source_format === template.source_format
  ));
}

function populatePresets(templateId, templates, presets) {
  const select = document.querySelector('#preset');
  const previous = select.value;
  select.replaceChildren();
  const compatible = compatiblePresets(templateId, templates, presets);
  for (const preset of compatible) option(select, preset.id, preset.id);
  if (compatible.some(item => item.id === previous)) select.value = previous;
  document.querySelector('#visualize').disabled = compatible.length === 0;
}

async function buildRenderer(health) {
  if (!health.s3d?.configured) {
    setViewerMessage('S3D is not configured. Set LMTS_S3D_ROOT and restart the DVS host.');
    return null;
  }
  if (!health.s3d?.ready) {
    throw new Error('Configured S3D root is not ready');
  }
  const s3d = await import(health.s3d.entrypoint);
  return new S3DVisualPlanRenderer(document.querySelector('#viewer'), s3d);
}

async function main() {
  const [health, templatePayload, presetPayload] = await Promise.all([
    getJson('/api/health'),
    getJson('/api/input-templates'),
    getJson('/api/visualization-presets'),
  ]);
  const templates = templatePayload.input_templates;
  const presets = presetPayload.visualization_presets;

  document.querySelector('#templates').textContent = JSON.stringify(templatePayload, null, 2);
  document.querySelector('#presets').textContent = JSON.stringify(presetPayload, null, 2);

  const templateSelect = document.querySelector('#template');
  for (const template of templates) option(templateSelect, template.id, `${template.id} · ${template.source_format}`);
  if (!templates.length) throw new Error('No DVS Input Templates are registered');
  populatePresets(templateSelect.value, templates, presets);
  templateSelect.addEventListener('change', () => populatePresets(templateSelect.value, templates, presets));

  const renderer = await buildRenderer(health);
  setStatus(
    renderer ? `DVS ready · S3D ${health.s3d.entrypoint}` : 'DVS ready · S3D not configured',
    renderer ? 'ready' : '',
  );

  document.querySelector('#source-file').addEventListener('change', async event => {
    const file = event.target.files?.[0];
    if (!file) return;
    document.querySelector('#source').value = await file.text();
  });

  document.querySelector('#extract').addEventListener('click', async () => {
    try {
      const payload = await postJson('/api/extract', {
        input_template_id: templateSelect.value,
        source: sourceDocument(),
      });
      document.querySelector('#output').textContent = JSON.stringify(payload, null, 2);
      setStatus(`Extracted ${payload.rows.length} row(s)`, 'ready');
    } catch (error) {
      setStatus(error.message, 'error');
      console.error(error);
    }
  });

  document.querySelector('#visualize').addEventListener('click', async () => {
    try {
      if (!renderer) throw new Error('S3D is not configured for this DVS host');
      const presetId = document.querySelector('#preset').value;
      if (!presetId) throw new Error('No compatible Visualization Preset is selected');
      const payload = await postJson('/api/visualize', {
        input_template_id: templateSelect.value,
        visualization_preset_id: presetId,
        source: sourceDocument(),
      });
      renderer.load(payload.visual_plan);
      document.querySelector('#output').textContent = JSON.stringify(payload.visual_plan, null, 2);
      setViewerMessage(
        `${payload.visual_plan.row_count} source row(s) · ${payload.visual_plan.visualization_preset_id}`,
      );
      setStatus('Visual plan rendered through S3D', 'ready');
    } catch (error) {
      setStatus(error.message, 'error');
      setViewerMessage(error.message);
      console.error(error);
    }
  });
}

main().catch(error => {
  document.body.dataset.error = 'true';
  setStatus(error.message, 'error');
  setViewerMessage(error.message);
  console.error(error);
});
