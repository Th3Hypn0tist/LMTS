<?php

declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

$config = require dirname(__DIR__, 2) . '/config.php';

function visualizer_fail(int $status, string $message): never {
    http_response_code($status);
    echo json_encode(['ok' => false, 'error' => $message], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

try {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
        header('Allow: GET');
        visualizer_fail(405, 'method not allowed');
    }
    $pdo = new PDO($config['dsn'], $config['user'], $config['password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    $id = trim((string)($_GET['id'] ?? ''));
    if ($id !== '') {
        $stmt = $pdo->prepare('SELECT report_json FROM reports WHERE report_id = ? LIMIT 1');
        $stmt->execute([$id]);
    } else {
        $stmt = $pdo->query('SELECT report_json FROM reports ORDER BY created_at DESC, imported_at DESC LIMIT 1');
    }
    $json = $stmt->fetchColumn();
    if ($json === false) visualizer_fail(404, 'report not found');
    echo $json;
} catch (Throwable $e) {
    visualizer_fail(500, 'server error');
}
