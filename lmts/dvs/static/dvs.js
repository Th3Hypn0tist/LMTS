import { S3DVisualPlanRenderer } from './visualizer.js';

async function requestJson(method, path, body = undefined) {
  const response = await fetch(path, {
    method,
    cache: 'no-store',
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `${response.status}`);
  return payload;
}

async function getJson(path) {
  return requestJson('GET', path);
}

async function postJson(path, body) {
  return requestJson('POST', path, body);
}

async function putJson(path, body) {
  return requestJson('PUT', path, body);
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

function definitionDocument(raw) {
  const text = String(raw ?? '').trim();
  if (!text) throw new Error('Definition JSON is required');
  const value = JSON.parse(text);
  if (value == null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Definition JSON root must be an object');
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

function setStudioMessage(text, mode = '') {
  const node = document.querySelector('#studio-message');
  node.textContent = text;
  node.className = `hint ${mode}`.trim();
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

function studioCollection(kind, templates, presets) {
  if (kind === 'input-template') return templates;
  if (kind === 'visualization-preset') return presets;
  throw new Error(`Unsupported Studio definition type: ${kind}`);
}

function newDefinition(kind) {
  if (kind === 'input-template') {
    return {
      format: 's3d.dvs.input-template',
      version: '1.0',
      id: 'example.template',
      source_format: 'example/1.0',
      reader: 'json',
      rows: 'records[*]',
      columns: [
        { name: 'value', selector: 'value' },
      ],
    };
  }
  if (kind === 'visualization-preset') {
    return {
      format: 's3d.dvs.visualization-preset',
      version: '1.0',
      id: 'example.preset',
      source_format: 'example/1.0',
      input_template_ref: 'example.template',
      generations: [
        {
          id: 'root',
          primitive: 'box',
          bindings: {
            'scale.y': { column: 'value', interpretation: 'number' },
          },
        },
      ],
    };
  }
  throw new Error(`Unsupported Studio definition type: ${kind}`);
}

function studioApi(kind) {
  if (kind === 'input-template') return '/api/studio/input-templates';
  if (kind === 'visualization-preset') return '/api/studio/visualization-presets';
  throw new Error(`Unsupported Studio definition type: ${kind}`);
}

function studioDraftApi(kind, operation) {
  if (!['validate', 'preview'].includes(operation)) {
    throw new Error(`Unsupported Studio draft operation: ${operation}`);
  }
  if (kind === 'input-template') return `/api/studio/${operation}/input-template`;
  if (kind === 'visualization-preset') return `/api/studio/${operation}/visualization-preset`;
  throw new Error(`Unsupported Studio definition type: ${kind}`);
}

function encodeDefinitionId(itemId) {
  const value = String(itemId ?? '').trim();
  if (!value) throw new Error('Definition id is required');
  return encodeURIComponent(value);
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
  const health = await getJson('/api/health');
  const state = {
    templates: [],
    presets: [],
  };

  const templateSelect = document.querySelector('#template');
  const studioKind = document.querySelector('#studio-kind');
  const studioDefinition = document.querySelector('#studio-definition');
  const studioEditor = document.querySelector('#studio-editor');
  let renderer = null;

  async function refreshRegistry() {
    const [templatePayload, presetPayload] = await Promise.all([
      getJson('/api/input-templates'),
      getJson('/api/visualization-presets'),
    ]);
    state.templates = templatePayload.input_templates;
    state.presets = presetPayload.visualization_presets;

    document.querySelector('#templates').textContent = JSON.stringify(templatePayload, null, 2);
    document.querySelector('#presets').textContent = JSON.stringify(presetPayload, null, 2);

    const previousTemplate = templateSelect.value;
    templateSelect.replaceChildren();
    for (const template of state.templates) {
      option(templateSelect, template.id, `${template.id} · ${template.source_format}`);
    }
    if (!state.templates.length) throw new Error('No DVS Input Templates are registered');
    if (state.templates.some(item => item.id === previousTemplate)) templateSelect.value = previousTemplate;
    populatePresets(templateSelect.value, state.templates, state.presets);

    const previousStudio = studioDefinition.value;
    studioDefinition.replaceChildren();
    const definitions = studioCollection(studioKind.value, state.templates, state.presets);
    for (const definition of definitions) option(studioDefinition, definition.id, definition.id);
    if (definitions.some(item => item.id === previousStudio)) studioDefinition.value = previousStudio;
  }

  function loadStudioSelection() {
    const definitions = studioCollection(studioKind.value, state.templates, state.presets);
    const selected = definitions.find(item => item.id === studioDefinition.value);
    if (!selected) throw new Error('No registered Studio definition is selected');
    studioEditor.value = JSON.stringify(selected, null, 2);
    setStudioMessage(`Loaded ${selected.id}. Update is validated by the server before persistence.`, 'ready');
  }

  await refreshRegistry();
  document.querySelector('#studio-root').textContent = `Studio root: ${health.studio?.root ?? 'unavailable'}`;

  templateSelect.addEventListener('change', () => populatePresets(templateSelect.value, state.templates, state.presets));
  studioKind.addEventListener('change', () => {
    studioDefinition.replaceChildren();
    const definitions = studioCollection(studioKind.value, state.templates, state.presets);
    for (const definition of definitions) option(studioDefinition, definition.id, definition.id);
    studioEditor.value = '';
    setStudioMessage('Select Load to inspect an existing definition, or New to start from a canonical skeleton.');
  });

  document.querySelector('#studio-load').addEventListener('click', () => {
    try {
      loadStudioSelection();
    } catch (error) {
      setStudioMessage(error.message, 'error');
    }
  });

  document.querySelector('#studio-new').addEventListener('click', () => {
    try {
      const definition = newDefinition(studioKind.value);
      studioEditor.value = JSON.stringify(definition, null, 2);
      setStudioMessage('New definition skeleton loaded. Change the id before Create.', 'ready');
    } catch (error) {
      setStudioMessage(error.message, 'error');
    }
  });

  document.querySelector('#studio-validate').addEventListener('click', async () => {
    try {
      const definition = definitionDocument(studioEditor.value);
      const payload = await postJson(studioDraftApi(studioKind.value, 'validate'), definition);
      document.querySelector('#output').textContent = JSON.stringify(payload, null, 2);
      setStudioMessage(`Draft ${definition.id ?? '(unnamed)'} is valid. Nothing was persisted.`, 'ready');
      setStatus('Studio draft validated', 'ready');
    } catch (error) {
      setStudioMessage(error.message, 'error');
      setStatus(error.message, 'error');
    }
  });

  document.querySelector('#studio-preview').addEventListener('click', async () => {
    try {
      const definition = definitionDocument(studioEditor.value);
      const payload = await postJson(studioDraftApi(studioKind.value, 'preview'), {
        definition,
        source: sourceDocument(),
      });
      if (studioKind.value === 'visualization-preset') {
        if (!renderer) throw new Error('S3D is not configured for Visualization Preset preview');
        renderer.load(payload.visual_plan);
        document.querySelector('#output').textContent = JSON.stringify(payload.visual_plan, null, 2);
        setViewerMessage(`${payload.visual_plan.row_count} source row(s) · draft ${definition.id}`);
      } else {
        document.querySelector('#output').textContent = JSON.stringify({
          columns: payload.columns,
          rows: payload.rows,
        }, null, 2);
      }
      setStudioMessage(`Previewed ${definition.id ?? '(unnamed)'} without persistence.`, 'ready');
      setStatus('Studio draft preview complete', 'ready');
    } catch (error) {
      setStudioMessage(error.message, 'error');
      setStatus(error.message, 'error');
      setViewerMessage(error.message);
    }
  });

  document.querySelector('#studio-create').addEventListener('click', async () => {
    try {
      const documentValue = definitionDocument(studioEditor.value);
      const payload = await postJson(studioApi(studioKind.value), documentValue);
      await refreshRegistry();
      studioDefinition.value = documentValue.id;
      studioEditor.value = JSON.stringify(
        studioKind.value === 'input-template' ? payload.input_template : payload.visualization_preset,
        null,
        2,
      );
      setStudioMessage(`Created ${documentValue.id}.`, 'ready');
      setStatus(`Studio created ${documentValue.id}`, 'ready');
    } catch (error) {
      setStudioMessage(error.message, 'error');
      setStatus(error.message, 'error');
    }
  });

  document.querySelector('#studio-update').addEventListener('click', async () => {
    try {
      const documentValue = definitionDocument(studioEditor.value);
      const selectedId = studioDefinition.value;
      if (!selectedId) throw new Error('Select the registered definition to update');
      if (documentValue.id !== selectedId) {
        throw new Error('Update cannot rename a definition; editor id must match the selected registry id');
      }
      const path = `${studioApi(studioKind.value)}/${encodeDefinitionId(selectedId)}`;
      const payload = await putJson(path, documentValue);
      await refreshRegistry();
      studioDefinition.value = selectedId;
      studioEditor.value = JSON.stringify(
        studioKind.value === 'input-template' ? payload.input_template : payload.visualization_preset,
        null,
        2,
      );
      setStudioMessage(`Updated ${selectedId}.`, 'ready');
      setStatus(`Studio updated ${selectedId}`, 'ready');
    } catch (error) {
      setStudioMessage(error.message, 'error');
      setStatus(error.message, 'error');
    }
  });

  document.querySelector('#studio-refresh').addEventListener('click', async () => {
    try {
      await refreshRegistry();
      setStudioMessage('Registry reloaded from server.', 'ready');
    } catch (error) {
      setStudioMessage(error.message, 'error');
    }
  });

  renderer = await buildRenderer(health);
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

if (typeof document !== 'undefined') {
  main().catch(error => {
    document.body.dataset.error = 'true';
    setStatus(error.message, 'error');
    setViewerMessage(error.message);
    console.error(error);
  });
}

export {
  compatiblePresets,
  definitionDocument,
  encodeDefinitionId,
  newDefinition,
  studioApi,
  studioCollection,
  studioDraftApi,
};
