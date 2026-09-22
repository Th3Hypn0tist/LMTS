<?php

declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
$config = require dirname(__DIR__) . '/config.php';
require_once __DIR__ . '/lib/report_contract.php';

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
        __DIR__ . '/contracts/' . LMTS_REPORT_CONTRACT_FILE,
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
