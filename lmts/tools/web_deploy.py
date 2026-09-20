from __future__ import annotations

from pathlib import Path

from .output import OutputTarget, write_files
from .report_contract_php import REPORT_CONTRACT_VALIDATOR_PHP


REPORT_CONTRACT_NAME = 'LMTS_Benchmark_Report_Template_v1.1.schema.json'


INDEX_HTML = '''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>LMTS Results</title>
  <link rel="stylesheet" href="./assets/lmts.css">
</head>
<body>
  <main id="app"></main>
  <script type="module" src="./app.js"></script>
</body>
</html>
'''

APP_JS = r'''import { WebGUI } from './WebGUI/webgui.js';

const gui = new WebGUI({ theme: null });
const app = document.querySelector('#app');

function h(tag, props = {}, children = []) {
  return gui.h(tag, props, children);
}

function entity(report, dimensionId, entityId) {
  const dimension = report.dimensions[dimensionId];
  return report.entities[dimension.entity_type][entityId];
}

function getPath(object, path) {
  return path.split('.').reduce((value, key) => value?.[key], object);
}

function systemProfileLabel(profile, index) {
  return String(profile?.profile_id ?? profile?.id ?? `System profile ${index + 1}`);
}

function renderSystemProfiles(report) {
  const profiles = Array.isArray(report.summary?.system_profiles) ? report.summary.system_profiles : [];
  if (!profiles.length) return null;

  const items = profiles.map((profile, index) => {
    const meta = [];
    if (profile?.profiled_at) meta.push(String(profile.profiled_at));
    return h('details', { className: 'system-profile' }, [
      h('summary', {}, [
        h('strong', { text: systemProfileLabel(profile, index) }),
        ...(meta.length ? [h('span', { className: 'profile-meta', text: meta.join(' · ') })] : []),
      ]),
      h('pre', { className: 'profile-json', text: JSON.stringify(profile, null, 2) }),
    ]);
  });

  return h('section', { className: 'panel' }, [
    h('h2', { text: 'System Profiles' }),
    h('p', { className: 'panel-note', text: 'Canonical system contexts recorded for runs in this report.' }),
    h('div', { className: 'profile-list' }, items),
  ]);
}

function render(report) {
  if (report?.format !== 'lmts.report' || report?.version !== '1.1') {
    throw new Error('Unsupported LMTS benchmark report format');
  }

  const summary = report.summary?.outcomes ?? {};
  const systemProfiles = Array.isArray(report.summary?.system_profiles) ? report.summary.system_profiles : [];
  const blocks = [
    h('header', { className: 'header' }, [
      h('div', { className: 'eyebrow', text: 'LMTS BENCHMARK REPORT' }),
      h('h1', { text: report.report.title }),
      h('div', { className: 'meta', text: `${report.report.id} · ${report.report.created_at} · lmts.report/${report.version}` }),
    ]),
    h('div', { className: 'summary' }, [
      ['Records', report.summary.records],
      ['Targets', report.summary.targets ?? Object.keys(report.entities?.target ?? {}).length],
      ['Tests', report.summary.tests ?? Object.keys(report.entities?.test ?? {}).length],
      ['Systems', systemProfiles.length],
      ['Pass', summary.pass ?? 0],
      ['Fail', summary.fail ?? 0],
      ['Error', summary.error ?? 0],
      ['Cancelled', summary.cancelled ?? 0],
    ].map(([label, value]) => h('div', { className: 'card' }, [
      h('strong', { text: String(value) }),
      h('span', { text: label }),
    ]))),
  ];

  const profiles = renderSystemProfiles(report);
  if (profiles) blocks.push(profiles);

  for (const view of report.views ?? []) {
    if (view.type !== 'matrix') continue;
    const rows = Object.keys(report.entities[report.dimensions[view.row_dimension].entity_type] ?? {});
    const columns = Object.keys(report.entities[report.dimensions[view.column_dimension].entity_type] ?? {});
    const cells = new Map();
    for (const record of report.records) {
      const row = record.coordinates[view.row_dimension];
      const column = record.coordinates[view.column_dimension];
      if (row != null && column != null) cells.set(`${row}\u0000${column}`, record);
    }

    const table = h('table', { className: 'matrix' });
    const head = h('tr');
    head.append(h('th', { text: report.dimensions[view.row_dimension].label }));
    for (const columnId of columns) {
      head.append(h('th', { text: entity(report, view.column_dimension, columnId).label }));
    }
    table.append(h('thead', {}, [head]));

    const body = h('tbody');
    for (const rowId of rows) {
      const tr = h('tr');
      tr.append(h('th', { className: 'row-label', text: entity(report, view.row_dimension, rowId).label }));
      for (const columnId of columns) {
        const record = cells.get(`${rowId}\u0000${columnId}`);
        const value = record ? String(getPath(record, view.value) ?? 'unknown') : '-';
        tr.append(h('td', {}, [h('span', { className: `result result-${value}`, text: value.toUpperCase() })]));
      }
      body.append(tr);
    }
    table.append(body);
    blocks.push(h('section', { className: 'panel' }, [h('h2', { text: view.title ?? view.id }), h('div', { className: 'scroll' }, [table])]));
  }

  gui.replace(app, blocks);
}

async function main() {
  const response = await fetch('./api/report.php', { cache: 'no-store' });
  if (!response.ok) throw new Error(`Report request failed: HTTP ${response.status}`);
  render(await response.json());
}

main().catch(error => {
  gui.replace(app, [h('pre', { className: 'fatal', text: error.stack ?? String(error) })]);
});
'''

CSS = '''
:root { color-scheme: dark; font-family: system-ui, sans-serif; background:#0b0d10; color:#edf1f5; }
* { box-sizing:border-box; }
body { margin:0; background:#0b0d10; }
#app { width:min(1500px, calc(100% - 32px)); margin:0 auto; padding:32px 0 64px; }
.header { margin-bottom:20px; }
.eyebrow,.meta { color:#8e9aa7; font-size:12px; }
h1,h2 { margin:.25rem 0 .5rem; }
.summary { display:grid; grid-template-columns:repeat(auto-fit,minmax(110px,1fr)); gap:10px; margin:20px 0; }
.card,.panel { border:1px solid #2a3139; background:#12161b; border-radius:10px; padding:14px; }
.card { display:flex; flex-direction:column; gap:4px; }
.card strong { font-size:24px; }
.card span { color:#8e9aa7; font-size:12px; text-transform:uppercase; }
.panel { margin-top:16px; }
.panel-note { color:#8e9aa7; margin:.25rem 0 1rem; }
.profile-list { display:grid; gap:8px; }
.system-profile { border:1px solid #2a3139; border-radius:8px; background:#0e1217; }
.system-profile summary { display:flex; justify-content:space-between; gap:16px; cursor:pointer; padding:10px 12px; }
.profile-meta { color:#8e9aa7; font-size:12px; font-weight:400; }
.profile-json { margin:0; padding:12px; border-top:1px solid #2a3139; overflow:auto; max-height:420px; white-space:pre; }
.scroll { overflow:auto; }
.matrix { width:100%; min-width:720px; border-collapse:collapse; }
.matrix th,.matrix td { padding:10px 12px; border:1px solid #2a3139; text-align:center; }
.matrix thead th,.row-label { background:#181d23; }
.row-label { text-align:left!important; font-family:ui-monospace,monospace; }
.result { font-weight:800; }
.result-pass { color:#6fd08c; }
.result-fail { color:#f3b75f; }
.result-error { color:#ef7373; }
.result-cancelled { color:#9a8ee8; }
.result-unknown { color:#88939d; }
.fatal { color:#ef7373; white-space:pre-wrap; }
@media (max-width:700px) { .summary { grid-template-columns:repeat(2,1fr); } .system-profile summary { flex-direction:column; gap:4px; } }
'''

REPORT_PHP = r'''<?php

declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
$config = require dirname(__DIR__) . '/config/db.php';
require_once dirname(__DIR__) . '/lib/report_contract.php';

function fail_response(int $status, string $message): never {
    http_response_code($status);
    echo json_encode(['ok' => false, 'error' => $message], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

function canonicalize_json_value(mixed $value): mixed {
    if (!is_array($value)) return $value;
    if (array_is_list($value)) {
        return array_map('canonicalize_json_value', $value);
    }
    ksort($value, SORT_STRING);
    foreach ($value as $key => $item) {
        $value[$key] = canonicalize_json_value($item);
    }
    return $value;
}

try {
    $pdo = new PDO($config['dsn'], $config['user'], $config['password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);

    if ($_SERVER['REQUEST_METHOD'] === 'GET') {
        $id = trim((string)($_GET['id'] ?? ''));
        if ($id !== '') {
            $stmt = $pdo->prepare('SELECT report_json FROM reports WHERE report_id = ? LIMIT 1');
            $stmt->execute([$id]);
        } else {
            $stmt = $pdo->query('SELECT report_json FROM reports ORDER BY created_at DESC, imported_at DESC LIMIT 1');
        }
        $json = $stmt->fetchColumn();
        if ($json === false) fail_response(404, 'report not found');
        echo $json;
        exit;
    }

    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        header('Allow: GET, POST');
        fail_response(405, 'method not allowed');
    }
    if (!hash_equals((string)$config['publish_key'], (string)($_SERVER['HTTP_X_LMTS_KEY'] ?? ''))) {
        fail_response(403, 'invalid publish key');
    }

    $raw = file_get_contents('php://input');
    if ($raw === false || trim($raw) === '') fail_response(400, 'empty request body');

    $document = json_decode($raw, false, 512, JSON_THROW_ON_ERROR);
    if (!($document instanceof stdClass)) fail_response(400, 'benchmark report root must be an object');
    lmts_validate_report_document(
        $document,
        dirname(__DIR__) . '/contracts/' . LMTS_REPORT_CONTRACT_FILE,
    );

    $report = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
    $meta = $report['report'];
    $source = $report['source'];
    $reportId = trim((string)$meta['id']);
    $reportType = trim((string)$meta['type']);
    $createdAtRaw = trim((string)$meta['created_at']);
    $sourceType = trim((string)$source['type']);
    $sourceId = trim((string)$source['id']);

    $createdAt = new DateTimeImmutable($createdAtRaw);
    $createdAtSql = $createdAt->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s.u');
    $canonicalReport = canonicalize_json_value($report);
    $reportJson = json_encode($canonicalReport, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);

    $pdo->beginTransaction();
    $existingStmt = $pdo->prepare('SELECT report_json FROM reports WHERE report_id = ? FOR UPDATE');
    $existingStmt->execute([$reportId]);
    $existingJson = $existingStmt->fetchColumn();

    if ($existingJson !== false) {
        $existingReport = json_decode((string)$existingJson, true, 512, JSON_THROW_ON_ERROR);
        $existingCanonical = json_encode(canonicalize_json_value($existingReport), JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
        $same = hash_equals(hash('sha256', $existingCanonical), hash('sha256', $reportJson));
        $pdo->commit();
        if (!$same) fail_response(409, 'report id already exists with different content');
        echo json_encode(['ok' => true, 'id' => $reportId, 'version' => $report['version'], 'created' => false], JSON_UNESCAPED_SLASHES);
        exit;
    }

    $insert = $pdo->prepare(
        'INSERT INTO reports (report_id, report_type, created_at, source_type, source_id, report_json)
         VALUES (?, ?, ?, ?, ?, ?)'
    );
    $insert->execute([$reportId, $reportType, $createdAtSql, $sourceType, $sourceId, $reportJson]);
    $pdo->commit();
    http_response_code(201);
    echo json_encode(['ok' => true, 'id' => $reportId, 'version' => $report['version'], 'created' => true], JSON_UNESCAPED_SLASHES);
} catch (InvalidArgumentException | JsonException | DateException $e) {
    if (isset($pdo) && $pdo instanceof PDO && $pdo->inTransaction()) $pdo->rollBack();
    fail_response(400, $e->getMessage());
} catch (Throwable $e) {
    if (isset($pdo) && $pdo instanceof PDO && $pdo->inTransaction()) $pdo->rollBack();
    fail_response(500, 'server error');
}
'''

REPORTS_PHP = r'''<?php

declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
$config = require dirname(__DIR__) . '/config/db.php';

try {
    $pdo = new PDO($config['dsn'], $config['user'], $config['password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
    $rows = $pdo->query(
        "SELECT report_id, report_type, created_at, source_type, source_id,
                JSON_UNQUOTE(JSON_EXTRACT(report_json, '$.version')) AS report_version,
                imported_at
         FROM reports ORDER BY created_at DESC, imported_at DESC LIMIT 100"
    )->fetchAll();
    echo json_encode(['reports' => $rows], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
} catch (Throwable $e) {
    http_response_code(500);
    echo json_encode(['error' => 'server error']);
}
'''


WEBGUI_SOURCE_COMMIT = '0dea8e711e0de84bf9da26826f0f40af4d4d8396'


STATISTICS_APP_JS = r'''import { WebGUI } from './WebGUI/webgui.js';

const gui = new WebGUI({ theme: null });
const app = document.querySelector('#app');

function h(tag, props = {}, children = []) {
  return gui.h(tag, props, children);
}

function text(value, fallback = '-') {
  return value == null || value === '' ? fallback : String(value);
}

function number(value, digits = 2) {
  if (value == null || value === '') return '-';
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return String(value);
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: digits }).format(parsed);
}

function targetLabel(record) {
  if (record.target_label) return record.target_label;
  const id = record.target_id ? ' · ' + record.target_id : '';
  return text(record.target_kind, 'unresolved') + id;
}

function testLabel(record) {
  if (record.test_name && record.test_version) return record.test_name + ' @ ' + record.test_version;
  if (record.test_namespace) return record.test_namespace;
  return text(record.test_version_id, 'unresolved');
}

function outcomeLabel(value) {
  const label = text(value, 'unknown').toLowerCase();
  return h('span', { className: 'result result-' + label, text: label.toUpperCase() });
}

function summaryCard(label, value) {
  return h('div', { className: 'card' }, [
    h('strong', { text: number(value, 0) }),
    h('span', { text: label }),
  ]);
}

function option(value, label, selected) {
  return gui.option(value, label, { selected: String(value) === String(selected ?? '') });
}

function filterSelect(label, name, values, selected, valueOf, labelOf) {
  const select = gui.select({ name }, [
    option('', 'All', selected),
    ...values.map(item => option(valueOf(item), labelOf(item), selected)),
  ]);
  return gui.field(label, select, { className: 'filter-field' });
}

function filterInput(label, name, type, value) {
  return gui.field(label, gui.input({ name, type, value: value ?? '' }), { className: 'filter-field' });
}

function renderFilters(filters) {
  const selected = filters?.selected ?? {};
  const options = filters?.options ?? {};
  const form = h('form', { className: 'filters' }, [
    filterSelect('User', 'user_id', options.users ?? [], selected.user_id, item => item.user_id, item => item.user_id),
    filterSelect('System', 'system_id', options.systems ?? [], selected.system_id, item => item.system_id, item => item.label || item.system_id),
    filterSelect('Target', 'target', options.targets ?? [], selected.target, item => item.value, item => item.label),
    filterSelect('Test', 'test_version_id', options.tests ?? [], selected.test_version_id, item => item.test_version_id, item => item.label),
    filterSelect('Outcome', 'outcome', options.outcomes ?? [], selected.outcome, item => item, item => String(item).toUpperCase()),
    filterSelect('Report', 'report_id', options.reports ?? [], selected.report_id, item => item.report_id, item => item.report_id),
    filterInput('From', 'from', 'datetime-local', selected.from_local),
    filterInput('To', 'to', 'datetime-local', selected.to_local),
    gui.field('Rows', gui.select({ name: 'limit' }, [50, 100, 200, 500].map(value => option(value, String(value), selected.limit))), { className: 'filter-field compact' }),
    gui.button('Apply', { type: 'submit', className: 'filter-action' }),
    gui.button('Reset', { className: 'filter-action secondary', on: { click: () => load(new URLSearchParams()) } }),
  ]);

  form.addEventListener('submit', event => {
    event.preventDefault();
    const data = new FormData(form);
    const params = new URLSearchParams();
    for (const [key, raw] of data.entries()) {
      const value = String(raw).trim();
      if (!value) continue;
      if ((key === 'from' || key === 'to') && value) {
        const instant = new Date(value);
        if (!Number.isNaN(instant.valueOf())) params.set(key, instant.toISOString());
      } else if (key === 'target') {
        const separator = value.indexOf(':');
        if (separator > 0) {
          params.set('target_kind', value.slice(0, separator));
          const targetId = value.slice(separator + 1);
          if (targetId) params.set('target_id', targetId);
        }
      } else {
        params.set(key, value);
      }
    }
    load(params);
  });
  return form;
}

function compareValues(left, right) {
  const a = left == null ? '' : left;
  const b = right == null ? '' : right;
  const an = Number(a);
  const bn = Number(b);
  if (a !== '' && b !== '' && Number.isFinite(an) && Number.isFinite(bn)) return an - bn;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

function resultsTable(records) {
  const container = h('div', { className: 'scroll' });
  let sortKey = 'started_at';
  let direction = -1;

  const columns = [
    ['report_id', 'Report', row => row.report_id],
    ['target_label', 'Target / model', row => targetLabel(row)],
    ['test_name', 'Test', row => testLabel(row)],
    ['outcome', 'Outcome', row => row.outcome],
    ['score_percent', 'Score %', row => row.score_percent],
    ['ttft_ms', 'TTFT ms', row => row.ttft_ms],
    ['total_time_ms', 'Total ms', row => row.total_time_ms],
    ['input_tokens', 'Input tokens', row => row.input_tokens],
    ['output_tokens', 'Output tokens', row => row.output_tokens],
    ['system_label', 'System', row => row.system_label || row.system_id],
  ];

  function draw() {
    const sorted = [...records].sort((a, b) => direction * compareValues(
      columns.find(column => column[0] === sortKey)?.[2](a),
      columns.find(column => column[0] === sortKey)?.[2](b),
    ));
    const table = h('table', { className: 'results-table' });
    const head = h('tr');
    for (const [key, label] of columns) {
      head.append(h('th', {}, [
        gui.button(label + (sortKey === key ? (direction > 0 ? ' ↑' : ' ↓') : ''), {
          className: 'sort-button',
          on: { click: () => {
            if (sortKey === key) direction *= -1;
            else { sortKey = key; direction = 1; }
            draw();
          } },
        }),
      ]));
    }
    table.append(h('thead', {}, [head]));

    const body = h('tbody');
    for (const record of sorted) {
      const reportLink = h('a', {
        href: './api/report.php?id=' + encodeURIComponent(record.report_id),
        target: '_blank',
        rel: 'noopener',
        text: record.report_id,
        title: 'Open immutable report evidence',
      });
      body.append(h('tr', {}, [
        h('td', {}, [reportLink, h('div', { className: 'subtle', text: text(record.record_id) })]),
        h('td', { text: targetLabel(record) }),
        h('td', { text: testLabel(record) }),
        h('td', {}, [outcomeLabel(record.outcome)]),
        h('td', { text: number(record.score_percent) }),
        h('td', { text: number(record.ttft_ms) }),
        h('td', { text: number(record.total_time_ms) }),
        h('td', { text: number(record.input_tokens, 0) }),
        h('td', { text: number(record.output_tokens, 0) }),
        h('td', { text: text(record.system_label || record.system_id) }),
      ]));
    }
    table.append(body);
    gui.replace(container, [table]);
  }

  draw();
  return container;
}

function numericSeries(samples) {
  const groups = new Map();
  for (const sample of samples ?? []) {
    if (sample.value_number == null || sample.value_number === '') continue;
    const value = Number(sample.value_number);
    if (!Number.isFinite(value)) continue;
    const unit = sample.unit ?? '';
    const key = String(sample.canonical_key) + '\u0000' + String(unit);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push({ ...sample, numeric_value: value });
  }
  return [...groups.values()];
}

function telemetryChart(samples) {
  const first = samples[0];
  const values = samples.map(sample => sample.numeric_value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min;
  const bars = samples.map(sample => {
    const normalized = span === 0 ? 0.5 : (sample.numeric_value - min) / span;
    return h('div', {
      className: 'telemetry-bar',
      style: { height: String(Math.max(4, normalized * 96)) + '%' },
      title: [
        sample.report_id + '/' + sample.record_id,
        number(sample.numeric_value) + (first.unit ? ' ' + first.unit : ''),
        sample.observed_at || ('sample ' + sample.sample_ordinal),
      ].join(' · '),
    });
  });

  return h('article', { className: 'telemetry-chart' }, [
    h('div', { className: 'chart-header' }, [
      h('div', {}, [
        h('strong', { text: first.telemetry_name || first.canonical_key }),
        h('div', { className: 'subtle', text: first.canonical_key + (first.unit ? ' · ' + first.unit : '') }),
      ]),
      h('span', { className: 'sample-count', text: String(samples.length) + ' raw samples' }),
    ]),
    h('div', { className: 'chart-range' }, [
      h('span', { text: number(max) }),
      h('span', { text: number(min) }),
    ]),
    h('div', { className: 'chart-scroll' }, [
      h('div', {
        className: 'bar-track',
        style: { minWidth: String(Math.max(640, samples.length * 7)) + 'px' },
      }, bars),
    ]),
  ]);
}

function render(payload) {
  if (payload?.format !== 'lmts.statistics' || payload?.version !== 1) {
    throw new Error('Unsupported LMTS statistics payload');
  }
  const summary = payload.summary ?? {};
  const records = payload.records ?? [];
  const series = numericSeries(payload.telemetry);

  const blocks = [
    h('header', { className: 'header' }, [
      h('div', { className: 'eyebrow', text: 'LMTS CANONICAL STATISTICS' }),
      h('h1', { text: 'Results & Telemetry' }),
      h('div', { className: 'meta', text: 'Canonical SQL projections · raw telemetry · no implicit aggregation' }),
    ]),
    renderFilters(payload.filters),
    h('div', { className: 'summary' }, [
      summaryCard('Reports', summary.reports),
      summaryCard('Result records', summary.result_records),
      summaryCard('Pass', summary.pass),
      summaryCard('Fail', summary.fail),
      summaryCard('Error', summary.error),
      summaryCard('Cancelled', summary.cancelled),
      summaryCard('Unknown', summary.unknown),
      summaryCard('Telemetry values', summary.telemetry_values),
    ]),
    h('section', { className: 'panel' }, [
      h('div', { className: 'section-title' }, [
        h('h2', { text: 'Results' }),
        h('span', { className: 'subtle', text: String(records.length) + ' rows in this view' }),
      ]),
      records.length ? resultsTable(records) : h('p', { className: 'empty', text: 'No projected result records match this view.' }),
    ]),
    h('section', { className: 'panel' }, [
      h('div', { className: 'section-title' }, [
        h('h2', { text: 'Telemetry' }),
        h('span', { className: 'subtle', text: 'One chart per canonical key and unit. Every bar is one stored sample.' }),
      ]),
      series.length
        ? h('div', { className: 'chart-grid' }, series.map(telemetryChart))
        : h('p', { className: 'empty', text: 'No numeric telemetry samples exist for the visible result records.' }),
    ]),
  ];
  gui.replace(app, blocks);
}

async function load(params = new URLSearchParams(location.search)) {
  const query = params.toString();
  history.replaceState(null, '', query ? '?' + query : location.pathname);
  gui.replace(app, [h('p', { className: 'loading', text: 'Loading canonical statistics…' })]);
  const response = await fetch('./api/stats.php' + (query ? '?' + query : ''), { cache: 'no-store' });
  if (!response.ok) {
    let detail = 'HTTP ' + response.status;
    try {
      const payload = await response.json();
      if (payload?.error) detail += ': ' + payload.error;
    } catch {}
    throw new Error('Statistics request failed: ' + detail);
  }
  render(await response.json());
}

load().catch(error => {
  gui.replace(app, [h('pre', { className: 'fatal', text: error.stack ?? String(error) })]);
});
'''


STATISTICS_CSS = '''
.filters { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; align-items:end; margin:20px 0; }
.filter-field { display:flex; flex-direction:column; gap:5px; color:#8e9aa7; font-size:12px; }
.filter-field select,.filter-field input,.filter-action { min-height:38px; border:1px solid #2a3139; border-radius:7px; background:#0e1217; color:#edf1f5; padding:7px 9px; }
.filter-field.compact { max-width:110px; }
.filter-action { cursor:pointer; align-self:end; }
.filter-action.secondary { color:#8e9aa7; }
.section-title,.chart-header { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; }
.subtle,.empty,.loading { color:#8e9aa7; font-size:12px; }
.results-table { width:100%; min-width:1180px; border-collapse:collapse; margin-top:10px; }
.results-table th,.results-table td { padding:9px 10px; border:1px solid #2a3139; vertical-align:top; text-align:left; }
.results-table thead th { position:sticky; top:0; background:#181d23; z-index:1; }
.sort-button { appearance:none; border:0; background:transparent; color:#edf1f5; font:inherit; font-weight:700; cursor:pointer; padding:0; white-space:nowrap; }
.results-table a { color:inherit; }
.chart-grid { display:grid; gap:12px; margin-top:12px; }
.telemetry-chart { border:1px solid #2a3139; border-radius:8px; background:#0e1217; padding:12px; }
.sample-count { color:#8e9aa7; font-size:12px; white-space:nowrap; }
.chart-range { display:flex; justify-content:space-between; color:#8e9aa7; font-size:11px; margin-top:10px; }
.chart-scroll { overflow-x:auto; border-bottom:1px solid #2a3139; }
.bar-track { height:150px; display:flex; align-items:flex-end; gap:2px; padding-top:4px; }
.telemetry-bar { flex:1 0 5px; min-width:5px; background:currentColor; opacity:.72; border-radius:2px 2px 0 0; }
@media (max-width:700px) { .filters { grid-template-columns:1fr 1fr; } .section-title,.chart-header { flex-direction:column; gap:4px; } }
'''


STATS_PHP = r'''<?php

declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
$config = require dirname(__DIR__) . '/config/db.php';

function stats_fail(int $status, string $message): never {
    http_response_code($status);
    echo json_encode(['ok' => false, 'error' => $message], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

function stats_param(string $name): ?string {
    $value = trim((string)($_GET[$name] ?? ''));
    return $value === '' ? null : $value;
}

function stats_time(?string $value): ?string {
    if ($value === null) return null;
    try {
        return (new DateTimeImmutable($value))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d H:i:s.u');
    } catch (Throwable $e) {
        stats_fail(400, 'invalid time filter');
    }
}

function stats_scope(): array {
    $conditions = [];
    $params = [];

    $simple = [
        'user_id' => 'rri.tester_user_id',
        'system_id' => 'rri.system_id',
        'test_version_id' => 'rri.test_version_id',
        'report_id' => 'rri.report_id',
        'target_kind' => 'rri.target_kind',
    ];
    foreach ($simple as $param => $column) {
        $value = stats_param($param);
        if ($value !== null) {
            $conditions[] = $column . ' = ?';
            $params[] = $value;
        }
    }

    $outcome = stats_param('outcome');
    if ($outcome === 'unknown') {
        $conditions[] = "(rri.outcome IS NULL OR rri.outcome NOT IN ('pass','fail','error','cancelled'))";
    } elseif ($outcome !== null) {
        $conditions[] = 'rri.outcome = ?';
        $params[] = $outcome;
    }

    $targetId = stats_param('target_id');
    $targetKind = stats_param('target_kind');
    if ($targetId !== null) {
        if ($targetKind === 'model') {
            $conditions[] = 'rri.model_node_id = ?';
        } elseif ($targetKind === 'composition') {
            $conditions[] = 'rri.composition_id = ?';
        } else {
            stats_fail(400, 'target_id requires target_kind model or composition');
        }
        $params[] = $targetId;
    }

    $from = stats_time(stats_param('from'));
    $to = stats_time(stats_param('to'));
    if ($from !== null) {
        $conditions[] = 'COALESCE(rri.started_at, r.created_at) >= ?';
        $params[] = $from;
    }
    if ($to !== null) {
        $conditions[] = 'COALESCE(rri.started_at, r.created_at) <= ?';
        $params[] = $to;
    }

    return [
        $conditions ? 'WHERE ' . implode(' AND ', $conditions) : '',
        $params,
    ];
}

function stats_query(PDO $pdo, string $sql, array $params = []): PDOStatement {
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    return $stmt;
}

function stats_iso(?string $value): ?string {
    if ($value === null || $value === '') return null;
    return (new DateTimeImmutable($value, new DateTimeZone('UTC')))->format('Y-m-d\TH:i:s.u\Z');
}

try {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
        header('Allow: GET');
        stats_fail(405, 'method not allowed');
    }

    $limitRaw = stats_param('limit');
    $limit = $limitRaw === null ? 100 : filter_var($limitRaw, FILTER_VALIDATE_INT);
    if ($limit === false || $limit < 1 || $limit > 500) {
        stats_fail(400, 'limit must be an integer between 1 and 500');
    }

    $pdo = new PDO($config['dsn'], $config['user'], $config['password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);

    [$where, $params] = stats_scope();

    $summary = stats_query(
        $pdo,
        "SELECT
            COUNT(DISTINCT rri.report_id) AS reports,
            COUNT(*) AS result_records,
            COALESCE(SUM(CASE WHEN rri.outcome = 'pass' THEN 1 ELSE 0 END), 0) AS pass,
            COALESCE(SUM(CASE WHEN rri.outcome = 'fail' THEN 1 ELSE 0 END), 0) AS fail,
            COALESCE(SUM(CASE WHEN rri.outcome = 'error' THEN 1 ELSE 0 END), 0) AS error,
            COALESCE(SUM(CASE WHEN rri.outcome = 'cancelled' THEN 1 ELSE 0 END), 0) AS cancelled,
            COALESCE(SUM(CASE
                WHEN rri.outcome IS NULL OR rri.outcome NOT IN ('pass','fail','error','cancelled')
                THEN 1 ELSE 0 END), 0) AS unknown
         FROM report_record_index rri
         JOIN reports r ON r.report_id = rri.report_id
         $where",
        $params,
    )->fetch() ?: [];

    $telemetryCount = stats_query(
        $pdo,
        "SELECT COUNT(*)
         FROM telemetry_values tv
         JOIN report_record_index rri
           ON rri.report_id = tv.report_id AND rri.record_id = tv.record_id
         JOIN reports r ON r.report_id = rri.report_id
         $where",
        $params,
    )->fetchColumn();

    $recordSql = "SELECT
        rri.report_id,
        rri.record_id,
        DATE_FORMAT(r.created_at, '%Y-%m-%dT%H:%i:%s.%fZ') AS report_created_at,
        rri.tester_user_id,
        rri.target_kind,
        rri.model_node_id,
        rri.composition_id,
        CASE
            WHEN rri.model_node_id IS NOT NULL THEN rri.model_node_id
            WHEN rri.composition_id IS NOT NULL THEN rri.composition_id
            ELSE NULL
        END AS target_id,
        COALESCE(mn.label, c.name) AS target_label,
        rri.test_version_id,
        td.test_definition_id,
        td.namespace AS test_namespace,
        td.name AS test_name,
        tv.version AS test_version,
        rri.system_id,
        s.label AS system_label,
        rri.compute_profile_id,
        DATE_FORMAT(rri.started_at, '%Y-%m-%dT%H:%i:%s.%fZ') AS started_at,
        DATE_FORMAT(rri.completed_at, '%Y-%m-%dT%H:%i:%s.%fZ') AS completed_at,
        rri.duration_ms AS total_time_ms,
        rri.ttft_ms,
        rri.outcome,
        rri.score_percent,
        (
            SELECT input_tv.value_number
            FROM telemetry_values input_tv
            WHERE input_tv.report_id = rri.report_id
              AND input_tv.record_id = rri.record_id
              AND input_tv.telemetry_type_id = 'input_tokens'
            ORDER BY input_tv.sample_ordinal, input_tv.telemetry_value_id
            LIMIT 1
        ) AS input_tokens,
        (
            SELECT output_tv.value_number
            FROM telemetry_values output_tv
            WHERE output_tv.report_id = rri.report_id
              AND output_tv.record_id = rri.record_id
              AND output_tv.telemetry_type_id = 'output_tokens'
            ORDER BY output_tv.sample_ordinal, output_tv.telemetry_value_id
            LIMIT 1
        ) AS output_tokens
     FROM report_record_index rri
     JOIN reports r ON r.report_id = rri.report_id
     LEFT JOIN model_nodes mn ON mn.model_node_id = rri.model_node_id
     LEFT JOIN compositions c ON c.composition_id = rri.composition_id
     LEFT JOIN test_versions tv ON tv.test_version_id = rri.test_version_id
     LEFT JOIN test_definitions td ON td.test_definition_id = tv.test_definition_id
     LEFT JOIN systems s ON s.system_id = rri.system_id
     $where
     ORDER BY COALESCE(rri.started_at, r.created_at) DESC, rri.report_id, rri.record_id
     LIMIT $limit";

    $records = stats_query($pdo, $recordSql, $params)->fetchAll();

    $selectedSql = "SELECT rri.report_id, rri.record_id
        FROM report_record_index rri
        JOIN reports r ON r.report_id = rri.report_id
        $where
        ORDER BY COALESCE(rri.started_at, r.created_at) DESC, rri.report_id, rri.record_id
        LIMIT $limit";

    $telemetrySql = "SELECT
        tv.telemetry_value_id,
        tv.report_id,
        tv.record_id,
        tv.user_id,
        tv.system_id,
        tv.compute_profile_id,
        tv.system_resource_id,
        tv.test_definition_id,
        tv.test_version_id,
        tv.telemetry_type_id,
        tt.canonical_key,
        tt.name AS telemetry_name,
        tt.value_kind,
        COALESCE(tv.unit_snapshot, tt.unit) AS unit,
        tv.sample_ordinal,
        DATE_FORMAT(tv.observed_at, '%Y-%m-%dT%H:%i:%s.%fZ') AS observed_at,
        tv.value_number,
        tv.value_text,
        tv.value_boolean,
        tv.value_json
     FROM telemetry_values tv
     JOIN telemetry_types tt ON tt.telemetry_type_id = tv.telemetry_type_id
     JOIN ($selectedSql) selected
       ON selected.report_id = tv.report_id AND selected.record_id = tv.record_id
     ORDER BY tt.canonical_key, COALESCE(tv.unit_snapshot, tt.unit), tv.report_id, tv.record_id,
              tv.sample_ordinal, tv.telemetry_value_id";

    $telemetry = stats_query($pdo, $telemetrySql, $params)->fetchAll();

    $users = $pdo->query(
        "SELECT DISTINCT tester_user_id AS user_id
         FROM report_record_index
         WHERE tester_user_id IS NOT NULL
         ORDER BY tester_user_id"
    )->fetchAll();

    $systems = $pdo->query(
        "SELECT DISTINCT rri.system_id, COALESCE(s.label, rri.system_id) AS label
         FROM report_record_index rri
         LEFT JOIN systems s ON s.system_id = rri.system_id
         WHERE rri.system_id IS NOT NULL
         ORDER BY label, rri.system_id"
    )->fetchAll();

    $tests = $pdo->query(
        "SELECT DISTINCT rri.test_version_id,
                CONCAT(COALESCE(td.name, td.namespace, rri.test_version_id),
                       CASE WHEN tv.version IS NULL THEN '' ELSE CONCAT(' @ ', tv.version) END) AS label
         FROM report_record_index rri
         LEFT JOIN test_versions tv ON tv.test_version_id = rri.test_version_id
         LEFT JOIN test_definitions td ON td.test_definition_id = tv.test_definition_id
         WHERE rri.test_version_id IS NOT NULL
         ORDER BY label, rri.test_version_id"
    )->fetchAll();

    $reports = $pdo->query(
        "SELECT report_id, DATE_FORMAT(created_at, '%Y-%m-%dT%H:%i:%s.%fZ') AS created_at
         FROM reports
         ORDER BY created_at DESC, imported_at DESC
         LIMIT 500"
    )->fetchAll();

    $outcomes = array_map(
        static fn(array $row): string => (string)$row['outcome'],
        $pdo->query(
            "SELECT DISTINCT COALESCE(outcome, 'unknown') AS outcome
             FROM report_record_index
             ORDER BY outcome"
        )->fetchAll(),
    );

    $targets = $pdo->query(
        "SELECT DISTINCT
            rri.target_kind,
            CASE
                WHEN rri.model_node_id IS NOT NULL THEN rri.model_node_id
                WHEN rri.composition_id IS NOT NULL THEN rri.composition_id
                ELSE NULL
            END AS target_id,
            COALESCE(mn.label, c.name, CONCAT(rri.target_kind, ' (unresolved)')) AS label
         FROM report_record_index rri
         LEFT JOIN model_nodes mn ON mn.model_node_id = rri.model_node_id
         LEFT JOIN compositions c ON c.composition_id = rri.composition_id
         ORDER BY label, rri.target_kind"
    )->fetchAll();
    foreach ($targets as &$target) {
        $target['value'] = (string)$target['target_kind'] . ':' . (string)($target['target_id'] ?? '');
    }
    unset($target);

    $selected = [
        'user_id' => stats_param('user_id'),
        'system_id' => stats_param('system_id'),
        'test_version_id' => stats_param('test_version_id'),
        'outcome' => stats_param('outcome'),
        'report_id' => stats_param('report_id'),
        'target' => stats_param('target_kind') === null
            ? null
            : stats_param('target_kind') . ':' . (stats_param('target_id') ?? ''),
        'from_local' => null,
        'to_local' => null,
        'limit' => $limit,
    ];

    $payload = [
        'format' => 'lmts.statistics',
        'version' => 1,
        'summary' => [
            'reports' => (int)($summary['reports'] ?? 0),
            'result_records' => (int)($summary['result_records'] ?? 0),
            'pass' => (int)($summary['pass'] ?? 0),
            'fail' => (int)($summary['fail'] ?? 0),
            'error' => (int)($summary['error'] ?? 0),
            'cancelled' => (int)($summary['cancelled'] ?? 0),
            'unknown' => (int)($summary['unknown'] ?? 0),
            'telemetry_values' => (int)$telemetryCount,
        ],
        'records' => $records,
        'telemetry' => $telemetry,
        'filters' => [
            'selected' => $selected,
            'options' => [
                'users' => $users,
                'systems' => $systems,
                'targets' => $targets,
                'tests' => $tests,
                'outcomes' => $outcomes,
                'reports' => $reports,
            ],
        ],
    ];

    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
} catch (JsonException $e) {
    stats_fail(500, 'statistics serialization failed');
} catch (Throwable $e) {
    stats_fail(500, 'server error');
}
'''


def web_root_files() -> dict[str, str]:
    package_root = Path(__file__).resolve().parent.parent
    db_config = (package_root / 'config' / 'db.php').read_text(encoding='utf-8')
    report_contract = (package_root / 'reporting' / REPORT_CONTRACT_NAME).read_text(encoding='utf-8')
    webgui_root = package_root / 'web' / 'WebGUI'
    return {
        'index.html': INDEX_HTML,
        'app.js': STATISTICS_APP_JS,
        'assets/lmts.css': CSS + STATISTICS_CSS,
        'api/stats.php': STATS_PHP,
        'api/report.php': REPORT_PHP,
        'api/reports.php': REPORTS_PHP,
        'lib/report_contract.php': REPORT_CONTRACT_VALIDATOR_PHP,
        f'contracts/{REPORT_CONTRACT_NAME}': report_contract,
        'config/db.php': db_config,
        'WebGUI/webgui.js': (webgui_root / 'webgui.js').read_text(encoding='utf-8'),
        'WebGUI/core/dom-structure.js': (webgui_root / 'core' / 'dom-structure.js').read_text(encoding='utf-8'),
        'WebGUI/core/theme.js': (webgui_root / 'core' / 'theme.js').read_text(encoding='utf-8'),
    }

def deploy_web_root(target: OutputTarget) -> list[str]:
    return write_files(target, web_root_files())
