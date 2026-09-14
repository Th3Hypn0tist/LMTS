from __future__ import annotations

from pathlib import Path

from .output import OutputTarget, write_files


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

function render(report) {
  if (report?.format !== 'lmts.report' || report?.version !== '1.1') {
    throw new Error('Unsupported LMTS benchmark report format');
  }

  const summary = report.summary?.outcomes ?? {};
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
      ['Pass', summary.pass ?? 0],
      ['Fail', summary.fail ?? 0],
      ['Error', summary.error ?? 0],
      ['Cancelled', summary.cancelled ?? 0],
    ].map(([label, value]) => h('div', { className: 'card' }, [
      h('strong', { text: String(value) }),
      h('span', { text: label }),
    ]))),
  ];

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
@media (max-width:700px) { .summary { grid-template-columns:repeat(2,1fr); } }
'''

REPORT_PHP = r'''<?php

declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
$config = require dirname(__DIR__, 2) . '/config/db.php';

const LMTS_REPORT_FORMAT = 'lmts.report';
const LMTS_REPORT_VERSION = '1.1';

function fail_response(int $status, string $message): never {
    http_response_code($status);
    echo json_encode(['ok' => false, 'error' => $message], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

function require_array_field(array $report, string $name): array {
    $value = $report[$name] ?? null;
    if (!is_array($value)) fail_response(400, "report.$name must be an object or array");
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
    $report = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
    if (!is_array($report) || ($report['format'] ?? null) !== LMTS_REPORT_FORMAT || ($report['version'] ?? null) !== LMTS_REPORT_VERSION) {
        fail_response(400, 'unsupported benchmark report format');
    }

    $meta = require_array_field($report, 'report');
    $source = require_array_field($report, 'source');
    $dimensions = require_array_field($report, 'dimensions');
    require_array_field($report, 'entities');
    require_array_field($report, 'metric_definitions');
    $records = require_array_field($report, 'records');
    $summary = require_array_field($report, 'summary');
    $views = require_array_field($report, 'views');

    if ($dimensions === []) fail_response(400, 'report.dimensions must not be empty');
    if (!array_is_list($records)) fail_response(400, 'report.records must be an array');
    if (!array_is_list($views)) fail_response(400, 'report.views must be an array');
    if (!isset($summary['records']) || !is_int($summary['records'])) fail_response(400, 'report.summary.records must be an integer');
    if (!isset($summary['outcomes']) || !is_array($summary['outcomes'])) fail_response(400, 'report.summary.outcomes must be an object');

    $reportId = trim((string)($meta['id'] ?? ''));
    $reportType = trim((string)($meta['type'] ?? ''));
    $createdAtRaw = trim((string)($meta['created_at'] ?? ''));
    $sourceType = trim((string)($source['type'] ?? ''));
    $sourceId = trim((string)($source['id'] ?? ''));
    if ($reportId === '' || $reportType === '' || $createdAtRaw === '' || $sourceType === '' || $sourceId === '') {
        fail_response(400, 'report identity fields are missing');
    }

    $createdAt = new DateTimeImmutable($createdAtRaw);
    $createdAtSql = $createdAt->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s.u');
    $reportJson = json_encode($report, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);

    $pdo->beginTransaction();
    $existingStmt = $pdo->prepare('SELECT report_json FROM reports WHERE report_id = ? FOR UPDATE');
    $existingStmt->execute([$reportId]);
    $existingJson = $existingStmt->fetchColumn();

    if ($existingJson !== false) {
        $same = hash_equals(hash('sha256', (string)$existingJson), hash('sha256', $reportJson));
        $pdo->commit();
        if (!$same) fail_response(409, 'report id already exists with different content');
        echo json_encode(['ok' => true, 'id' => $reportId, 'version' => LMTS_REPORT_VERSION, 'created' => false], JSON_UNESCAPED_SLASHES);
        exit;
    }

    $insert = $pdo->prepare(
        'INSERT INTO reports (report_id, report_type, created_at, source_type, source_id, report_json)
         VALUES (?, ?, ?, ?, ?, ?)'
    );
    $insert->execute([$reportId, $reportType, $createdAtSql, $sourceType, $sourceId, $reportJson]);
    $pdo->commit();
    http_response_code(201);
    echo json_encode(['ok' => true, 'id' => $reportId, 'version' => LMTS_REPORT_VERSION, 'created' => true], JSON_UNESCAPED_SLASHES);
} catch (JsonException | DateException $e) {
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
$config = require dirname(__DIR__, 2) . '/config/db.php';

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


def web_root_files() -> dict[str, str]:
    package_root = Path(__file__).resolve().parent.parent
    db_config = (package_root / 'config' / 'db.php').read_text(encoding='utf-8')
    report_contract = (package_root / 'reporting' / REPORT_CONTRACT_NAME).read_text(encoding='utf-8')
    return {
        'public/index.html': INDEX_HTML,
        'public/app.js': APP_JS,
        'public/assets/lmts.css': CSS,
        'public/api/report.php': REPORT_PHP,
        'public/api/reports.php': REPORTS_PHP,
        f'public/contracts/{REPORT_CONTRACT_NAME}': report_contract,
        'config/db.php': db_config,
    }


def deploy_web_root(target: OutputTarget) -> list[str]:
    return write_files(target, web_root_files())
