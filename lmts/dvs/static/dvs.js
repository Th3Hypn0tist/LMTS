import { S3DVisualPlanRenderer } from './visualizer.js';

const dvsErrors = [];

function normalizeError(value) {
  if (value instanceof Error) return { message: value.message, stack: value.stack || '' };
  if (typeof value === 'string') return { message: value, stack: '' };
  try {
    return { message: JSON.stringify(value), stack: '' };
  } catch {
    return { message: String(value), stack: '' };
  }
}

function refreshErrorButton() {
  if (typeof document === 'undefined') return;
  const button = document.querySelector('#errorReportButton');
  if (!button) return;
  button.textContent = `ERRORS ${dvsErrors.length}`;
  button.classList.toggle('has-errors', dvsErrors.length > 0);
}

function reportDvsError(error, context = {}) {
  if (error instanceof Error && error.__dvsReported) return error.__dvsReported;
  const entry = {
    timestamp: new Date().toISOString(),
    type: context.type || 'caught_error',
    ...normalizeError(error),
    ...context,
  };
  dvsErrors.push(entry);
  if (error instanceof Error) error.__dvsReported = entry;
  refreshErrorButton();
  return entry;
}

function errorReportText(errors = dvsErrors, environment = {}) {
  const url = environment.url ?? (typeof location !== 'undefined' ? location.href : '');
  const userAgent = environment.userAgent ?? (typeof navigator !== 'undefined' ? navigator.userAgent : '');
  return [
    'LMTS DVS ERROR REPORT',
    `generated: ${new Date().toISOString()}`,
    `url: ${url}`,
    `user_agent: ${userAgent}`,
    `error_count: ${errors.length}`,
    '',
    ...errors.flatMap((error, index) => [
      `[${index + 1}] ${error.timestamp} ${error.type}`,
      `message: ${error.message}`,
      error.method ? `request: ${error.method} ${error.path || ''}` : '',
      error.status != null ? `http_status: ${error.status}` : '',
      error.response_body ? `response_body: ${error.response_body}` : '',
      error.source ? `source: ${error.source}:${error.line ?? 0}:${error.column ?? 0}` : '',
      error.stack ? `stack:\n${error.stack}` : '',
      '',
    ]),
  ].join('\n');
}

function openErrorReportDialog(text) {
  if (typeof document === 'undefined') return false;
  const dialog = document.querySelector('#errorReportDialog');
  const textarea = document.querySelector('#errorReportText');
  if (!dialog || !textarea) return false;
  textarea.value = text;
  if (typeof dialog.showModal === 'function') dialog.showModal();
  else dialog.setAttribute('open', '');
  textarea.focus();
  textarea.select();
  return true;
}

async function copyTextToClipboard(text) {
  let nativeError = null;

  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return 'clipboard';
    } catch (error) {
      nativeError = error;
    }
  }

  if (typeof document !== 'undefined' && typeof document.execCommand === 'function') {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.setAttribute('readonly', '');
    textarea.setAttribute('aria-hidden', 'true');
    textarea.style.position = 'fixed';
    textarea.style.left = '-10000px';
    textarea.style.top = '0';
    document.body.append(textarea);
    try {
      textarea.focus();
      textarea.select();
      textarea.setSelectionRange(0, textarea.value.length);
      if (document.execCommand('copy')) return 'legacy';
    } finally {
      textarea.remove();
    }
  }

  const detail = nativeError instanceof Error ? `: ${nativeError.message}` : '';
  throw new Error(`Clipboard copy unavailable${detail}`);
}


async function requestJson(method, path, body = undefined) {
  let response;
  try {
    response = await fetch(path, {
      method,
      cache: 'no-store',
      headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (error) {
    reportDvsError(error, { type: 'api_network_error', method, path });
    throw error;
  }

  const raw = await response.text();
  let payload;
  try {
    payload = raw ? JSON.parse(raw) : {};
  } catch (error) {
    reportDvsError(error, {
      type: 'api_decode_error',
      method,
      path,
      status: response.status,
      response_body: raw.slice(0, 4000),
    });
    throw new Error(`${method} ${path} returned invalid JSON (HTTP ${response.status})`);
  }

  if (!response.ok) {
    const backendMismatch = (
      response.status === 404
      && payload?.error === 'not_found'
      && (path.startsWith('/api/database-') || path.startsWith('/api/report-source'))
    );
    const message = backendMismatch
      ? `DVS backend does not expose ${path}. Restart DVS after updating LMTS.`
      : (payload?.error || `${response.status}`);
    const error = new Error(message);
    reportDvsError(error, {
      type: backendMismatch ? 'backend_api_mismatch' : 'api_error',
      method,
      path,
      status: response.status,
      response_body: raw.slice(0, 4000),
    });
    throw error;
  }
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

function databaseReportLabel(report) {
  const source = String(report.report_source_label || report.report_source_id || report.database_source_label || report.database_source_id || '').trim();
  const created = String(report.created_at || '').trim();
  const reportId = String(report.report_id || '').trim();
  const entity = String(report.source_id || '').trim();
  return [source && `[${source}]`, created, reportId, entity && `· ${entity}`].filter(Boolean).join(' ');
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
        { name: 'value', selector: 'value', type: 'number' },
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

function studioRangeApi() {
  return '/api/studio/range/input-template';
}

function numericInputColumns(definition) {
  if (!definition || !Array.isArray(definition.columns)) return [];
  return definition.columns.filter(column => column?.type === 'number');
}

function scaleForColumn(definition, columnName) {
  const column = numericInputColumns(definition).find(item => item.name === columnName);
  if (!column) throw new Error(`Input Template has no number column ${columnName}`);
  return column.scale ? { ...column.scale } : null;
}

function updateScaleDefinition(definition, columnName, scale) {
  const result = JSON.parse(JSON.stringify(definition));
  if (!Array.isArray(result.columns)) throw new Error('Input Template columns must be an array');
  const column = result.columns.find(item => item?.name === columnName);
  if (!column) throw new Error(`Input Template has no column ${columnName}`);
  if (column.type !== 'number') throw new Error(`Input scale requires number column ${columnName}`);

  if (scale == null) {
    delete column.scale;
    return result;
  }

  const low = Number(scale.low);
  const high = Number(scale.high);
  const power = Number(scale.power);
  if (!Number.isFinite(low)) throw new Error('Scale low must be a finite number');
  if (!Number.isFinite(high)) throw new Error('Scale high must be a finite number');
  if (!(high > low)) throw new Error('Scale high must be greater than low');
  if (!Number.isFinite(power) || !(power > 0)) throw new Error('Scale power must be greater than zero');
  column.scale = { low, high, power };
  return result;
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
    databaseSources: [],
    databaseReports: [],
  };

  const templateSelect = document.querySelector('#template');
  const databaseSources = document.querySelector('#database-sources');
  const databaseReport = document.querySelector('#database-report');
  const databaseMessage = document.querySelector('#database-message');
  const databaseRefresh = document.querySelector('#database-refresh');
  const studioKind = document.querySelector('#studio-kind');
  const studioDefinition = document.querySelector('#studio-definition');
  const studioEditor = document.querySelector('#studio-editor');
  const scaleTools = document.querySelector('#studio-scale-tools');
  const scaleColumn = document.querySelector('#studio-scale-column');
  const scaleLow = document.querySelector('#studio-scale-low');
  const scaleHigh = document.querySelector('#studio-scale-high');
  const scalePower = document.querySelector('#studio-scale-power');
  let renderer = null;

  function selectedDatabaseSourceIds() {
    return [...databaseSources.querySelectorAll('input[type="checkbox"]:checked')].map(item => item.value);
  }

  async function refreshDatabaseSources() {
    const previouslySelected = new Set(selectedDatabaseSourceIds());
    const payload = await getJson('/api/report-source-statuses');
    state.databaseSources = payload.report_sources || [];
    databaseSources.replaceChildren();
    for (const source of state.databaseSources) {
      const label = document.createElement('label');
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.value = source.id;
      checkbox.checked = previouslySelected.has(source.id)
        || (previouslySelected.size === 0 && Number(source.report_count || 0) > 0);
      const statusText = source.ok
        ? `${source.report_count} report(s)${source.latest_report_id ? ` · latest ${source.latest_report_id}` : ''}`
        : `ERROR: ${source.error || 'unknown source error'}`;
      label.append(
        checkbox,
        ` ${source.label} · ${source.address || ''} · ${statusText}`,
      );
      databaseSources.append(label);
    }
    databaseReport.replaceChildren();
    state.databaseReports = [];
    const selectedCount = selectedDatabaseSourceIds().length;
    databaseRefresh.disabled = selectedCount === 0;
    const totalReports = state.databaseSources.reduce((sum, source) => sum + Number(source.report_count || 0), 0);
    databaseMessage.textContent = state.databaseSources.length
      ? `${selectedCount} report source(s) selected · ${totalReports} report(s) visible across configured sources.`
      : 'No DVS report sources configured.';
  }

  async function refreshDatabaseReports() {
    const sourceIds = selectedDatabaseSourceIds();
    if (!sourceIds.length) throw new Error('Select at least one report source');
    const payload = await postJson('/api/report-source-reports', {
      source_ids: sourceIds,
      limit_per_source: 100,
    });
    state.databaseReports = payload.reports || [];
    databaseReport.replaceChildren();
    for (let index = 0; index < state.databaseReports.length; index += 1) {
      option(databaseReport, String(index), databaseReportLabel(state.databaseReports[index]));
    }
    if (state.databaseReports.length) {
      for (const item of [...databaseReport.options].slice(0, Math.min(10, databaseReport.options.length))) {
        item.selected = true;
      }
      databaseMessage.textContent = `${state.databaseReports.length} report(s) from ${sourceIds.length} report source(s). First ${Math.min(10, state.databaseReports.length)} selected.`;
    } else {
      databaseMessage.textContent = `0 reports from ${sourceIds.length} selected database source(s).`;
    }
  }

  function selectedDatabaseReports() {
    return [...databaseReport.selectedOptions].map(item => {
      const selected = state.databaseReports[Number(item.value)];
      if (!selected) throw new Error('Report selection is out of sync with the report list');
      return selected;
    });
  }

  async function loadSelectedDatabaseReport() {
    const selected = selectedDatabaseReports();
    if (!selected.length) throw new Error('Select at least one report');
    const payload = await postJson('/api/report-source-dataset', {
      reports: selected.map(item => ({
        source_id: item.report_source_id,
        report_id: item.report_id,
      })),
    });
    document.querySelector('#source').value = JSON.stringify(payload.source, null, 2);

    const telemetryTemplate = 'lmts.report-telemetry-percent.v1.0';
    if (state.templates.some(item => item.id === telemetryTemplate)) {
      templateSelect.value = telemetryTemplate;
      populatePresets(templateSelect.value, state.templates, state.presets);
      const telemetryPreset = 'lmts.report-telemetry-percent.landscape.v1';
      const presetSelect = document.querySelector('#preset');
      if ([...presetSelect.options].some(item => item.value === telemetryPreset)) {
        presetSelect.value = telemetryPreset;
      }
    }

    databaseMessage.textContent =
      `Loaded ${payload.source.report_count} report(s), ${payload.source.record_count} result record(s), ${payload.source.row_count} percent telemetry row(s).`;
    setStatus('Multi-report telemetry dataset loaded into Source JSON', 'ready');
  }

  function refreshScaleFields() {
    scaleTools.hidden = studioKind.value !== 'input-template';
    if (scaleTools.hidden) return;

    let definition;
    try {
      definition = definitionDocument(studioEditor.value);
    } catch {
      scaleColumn.replaceChildren();
      scaleLow.value = '';
      scaleHigh.value = '';
      scalePower.value = '1';
      return;
    }

    const columns = numericInputColumns(definition);
    const previous = scaleColumn.value;
    scaleColumn.replaceChildren();
    for (const column of columns) option(scaleColumn, column.name, column.name);
    if (columns.some(column => column.name === previous)) scaleColumn.value = previous;
    const selected = scaleColumn.value;
    if (!selected) {
      scaleLow.value = '';
      scaleHigh.value = '';
      scalePower.value = '1';
      return;
    }
    const scale = scaleForColumn(definition, selected);
    scaleLow.value = scale?.low ?? '';
    scaleHigh.value = scale?.high ?? '';
    scalePower.value = scale?.power ?? 1;
  }

  function writeScaleToEditor(scale) {
    const definition = definitionDocument(studioEditor.value);
    const columnName = scaleColumn.value;
    if (!columnName) throw new Error('Select a number column');
    const updated = updateScaleDefinition(definition, columnName, scale);
    studioEditor.value = JSON.stringify(updated, null, 2);
    refreshScaleFields();
    return updated;
  }

  async function findScaleBound(which) {
    if (studioKind.value !== 'input-template') throw new Error('Range scan applies only to Input Templates');
    const definition = definitionDocument(studioEditor.value);
    const column = scaleColumn.value;
    if (!column) throw new Error('Select a number column');
    const payload = await postJson(studioRangeApi(), {
      definition,
      source: sourceDocument(),
      column,
    });
    if (which === 'low') scaleLow.value = payload.low;
    else if (which === 'high') scaleHigh.value = payload.high;
    else throw new Error(`Unknown range bound ${which}`);
    document.querySelector('#output').textContent = JSON.stringify(payload, null, 2);
    setStudioMessage(`Found ${which} for ${column}: ${payload[which]}.`, 'ready');
    setStatus(`Studio range scan ${column}`, 'ready');
  }

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
    refreshScaleFields();
  }

  function loadStudioSelection() {
    const definitions = studioCollection(studioKind.value, state.templates, state.presets);
    const selected = definitions.find(item => item.id === studioDefinition.value);
    if (!selected) throw new Error('No registered Studio definition is selected');
    studioEditor.value = JSON.stringify(selected, null, 2);
    refreshScaleFields();
    setStudioMessage(`Loaded ${selected.id}. Update is validated by the server before persistence.`, 'ready');
  }

  await refreshRegistry();
  await refreshDatabaseSources();
  document.querySelector('#studio-root').textContent = `Studio root: ${health.studio?.root ?? 'unavailable'}`;

  templateSelect.addEventListener('change', () => populatePresets(templateSelect.value, state.templates, state.presets));
  studioKind.addEventListener('change', () => {
    studioDefinition.replaceChildren();
    const definitions = studioCollection(studioKind.value, state.templates, state.presets);
    for (const definition of definitions) option(studioDefinition, definition.id, definition.id);
    studioEditor.value = '';
    refreshScaleFields();
    setStudioMessage('Select Load to inspect an existing definition, or New to start from a canonical skeleton.');
  });
  studioEditor.addEventListener('input', refreshScaleFields);
  scaleColumn.addEventListener('change', refreshScaleFields);

  document.querySelector('#studio-load').addEventListener('click', () => {
    try {
      loadStudioSelection();
    } catch (error) {
      reportDvsError(error, { type: 'ui_action_error' });
      setStudioMessage(error.message, 'error');
    }
  });

  document.querySelector('#studio-new').addEventListener('click', () => {
    try {
      const definition = newDefinition(studioKind.value);
      studioEditor.value = JSON.stringify(definition, null, 2);
      refreshScaleFields();
      setStudioMessage('New definition skeleton loaded. Change the id before Create.', 'ready');
    } catch (error) {
      reportDvsError(error, { type: 'ui_action_error' });
      setStudioMessage(error.message, 'error');
    }
  });

  document.querySelector('#studio-find-low').addEventListener('click', async () => {
    try {
      await findScaleBound('low');
    } catch (error) {
      reportDvsError(error, { type: 'ui_action_error' });
      setStudioMessage(error.message, 'error');
      setStatus(error.message, 'error');
    }
  });

  document.querySelector('#studio-find-high').addEventListener('click', async () => {
    try {
      await findScaleBound('high');
    } catch (error) {
      reportDvsError(error, { type: 'ui_action_error' });
      setStudioMessage(error.message, 'error');
      setStatus(error.message, 'error');
    }
  });

  document.querySelector('#studio-apply-scale').addEventListener('click', () => {
    try {
      const updated = writeScaleToEditor({
        low: scaleLow.value,
        high: scaleHigh.value,
        power: scalePower.value,
      });
      const column = scaleColumn.value;
      setStudioMessage(`Applied scale.${column} to draft ${updated.id}.`, 'ready');
    } catch (error) {
      reportDvsError(error, { type: 'ui_action_error' });
      setStudioMessage(error.message, 'error');
    }
  });

  document.querySelector('#studio-remove-scale').addEventListener('click', () => {
    try {
      const column = scaleColumn.value;
      const updated = writeScaleToEditor(null);
      setStudioMessage(`Removed scale.${column} from draft ${updated.id}.`, 'ready');
    } catch (error) {
      reportDvsError(error, { type: 'ui_action_error' });
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
      reportDvsError(error, { type: 'ui_action_error' });
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
          column_types: payload.column_types,
          rows: payload.rows,
          parameters: payload.parameters,
        }, null, 2);
      }
      setStudioMessage(`Previewed ${definition.id ?? '(unnamed)'} without persistence.`, 'ready');
      setStatus('Studio draft preview complete', 'ready');
    } catch (error) {
      reportDvsError(error, { type: 'ui_action_error' });
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
      refreshScaleFields();
      setStudioMessage(`Created ${documentValue.id}.`, 'ready');
      setStatus(`Studio created ${documentValue.id}`, 'ready');
    } catch (error) {
      reportDvsError(error, { type: 'ui_action_error' });
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
      refreshScaleFields();
      setStudioMessage(`Updated ${selectedId}.`, 'ready');
      setStatus(`Studio updated ${selectedId}`, 'ready');
    } catch (error) {
      reportDvsError(error, { type: 'ui_action_error' });
      setStudioMessage(error.message, 'error');
      setStatus(error.message, 'error');
    }
  });

  document.querySelector('#studio-refresh').addEventListener('click', async () => {
    try {
      await refreshRegistry();
      setStudioMessage('Registry reloaded from server.', 'ready');
    } catch (error) {
      reportDvsError(error, { type: 'ui_action_error' });
      setStudioMessage(error.message, 'error');
    }
  });

  databaseSources.addEventListener('change', () => {
    const selectedCount = selectedDatabaseSourceIds().length;
    databaseRefresh.disabled = selectedCount === 0;
    databaseMessage.textContent = `${selectedCount} database source(s) selected.`;
  });

  databaseRefresh.addEventListener('click', async () => {
    try {
      await refreshDatabaseReports();
    } catch (error) {
      reportDvsError(error, { type: 'database_ui_error' });
      databaseMessage.textContent = error.message;
      setStatus(error.message, 'error');
    }
  });

  document.querySelector('#database-load').addEventListener('click', async () => {
    try {
      await loadSelectedDatabaseReport();
    } catch (error) {
      reportDvsError(error, { type: 'database_ui_error' });
      databaseMessage.textContent = error.message;
      setStatus(error.message, 'error');
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
      reportDvsError(error, { type: 'viewer_action_error' });
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
      reportDvsError(error, { type: 'viewer_action_error' });
      setStatus(error.message, 'error');
      setViewerMessage(error.message);
      console.error(error);
    }
  });
}

if (typeof window !== 'undefined') {
  window.addEventListener('error', event => {
    if (event instanceof ErrorEvent) {
      reportDvsError(event.error || event.message, {
        type: 'runtime_error',
        source: event.filename,
        line: event.lineno,
        column: event.colno,
      });
    } else if (event.target?.src || event.target?.href) {
      reportDvsError(`Failed to load resource: ${event.target.src || event.target.href}`, {
        type: 'resource_error',
        source: event.target.src || event.target.href,
      });
    }
  }, true);
  window.addEventListener('unhandledrejection', event => {
    reportDvsError(event.reason, { type: 'unhandled_rejection' });
  });
}

if (typeof document !== 'undefined') {
  const errorButton = document.querySelector('#errorReportButton');
  const errorDialog = document.querySelector('#errorReportDialog');
  const errorTextarea = document.querySelector('#errorReportText');
  const errorSelect = document.querySelector('#errorReportSelect');
  const errorClose = document.querySelector('#errorReportClose');

  if (errorButton) {
    errorButton.addEventListener('click', async () => {
      const report = errorReportText();
      try {
        await copyTextToClipboard(report);
        errorButton.textContent = `COPIED ${dvsErrors.length}`;
        setTimeout(refreshErrorButton, 900);
      } catch (error) {
        reportDvsError(error, { type: 'clipboard_error' });
        openErrorReportDialog(errorReportText());
        errorButton.textContent = `OPEN ${dvsErrors.length}`;
        setTimeout(refreshErrorButton, 900);
      }
    });
  }

  if (errorSelect && errorTextarea) {
    errorSelect.addEventListener('click', () => {
      errorTextarea.focus();
      errorTextarea.select();
    });
  }

  if (errorClose && errorDialog) {
    errorClose.addEventListener('click', () => {
      if (typeof errorDialog.close === 'function') errorDialog.close();
      else errorDialog.removeAttribute('open');
    });
  }

  refreshErrorButton();

  main().catch(error => {
    reportDvsError(error, { type: 'startup_error' });
    document.body.dataset.error = 'true';
    setStatus(error.message, 'error');
    setViewerMessage(error.message);
    console.error(error);
  });
}

export {
  compatiblePresets,
  dvsErrors,
  errorReportText,
  copyTextToClipboard,
  openErrorReportDialog,
  reportDvsError,
  databaseReportLabel,
  definitionDocument,
  encodeDefinitionId,
  newDefinition,
  numericInputColumns,
  scaleForColumn,
  studioApi,
  studioCollection,
  studioDraftApi,
  studioRangeApi,
  updateScaleDefinition,
};
