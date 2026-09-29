<?php

declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

$config = require dirname(__DIR__, 2) . '/lmts-report/config.php';

function rankings_fail(int $status, string $message): never {
    http_response_code($status);
    echo json_encode(['ok' => false, 'error' => $message], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

try {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
        header('Allow: GET');
        rankings_fail(405, 'method not allowed');
    }

    $pdo = new PDO($config['dsn'], $config['user'], $config['password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);

    $rows = $pdo->query(
        "SELECT
            rri.tester_user_id AS user_id,
            COALESCE(u.username, rri.tester_user_id) AS username,
            u.display_name,
            COUNT(*) AS test_executions,
            COUNT(DISTINCT rri.report_id) AS reports,
            COUNT(DISTINCT rri.test_version_id) AS unique_tests,
            COUNT(DISTINCT CASE
                WHEN rri.target_ref IS NULL THEN NULL
                ELSE CONCAT(rri.target_kind, ':', rri.target_ref)
            END) AS unique_targets,
            COUNT(DISTINCT rri.system_id) AS systems,
            SUM(CASE WHEN rri.outcome = 'pass' THEN 1 ELSE 0 END) AS pass,
            SUM(CASE WHEN rri.outcome = 'fail' THEN 1 ELSE 0 END) AS fail,
            MAX(COALESCE(rri.started_at, r.created_at)) AS latest_at
         FROM LMTS_report_record_index rri
         JOIN LMTS_reports r ON r.report_id = rri.report_id
         LEFT JOIN IAM_users u ON u.user_id = rri.tester_user_id
         WHERE rri.outcome IN ('pass','fail')
           AND rri.tester_user_id IS NOT NULL
         GROUP BY rri.tester_user_id, u.username, u.display_name
         ORDER BY test_executions DESC, unique_tests DESC, username"
    )->fetchAll();

    foreach ($rows as &$row) {
        foreach (['test_executions','reports','unique_tests','unique_targets','systems','pass','fail'] as $key) {
            $row[$key] = (int)$row[$key];
        }
    }
    unset($row);

    echo json_encode([
        'format' => 'lmts.rankings',
        'version' => 1,
        'rows' => $rows,
    ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
} catch (JsonException $e) {
    rankings_fail(500, 'rankings serialization failed');
} catch (Throwable $e) {
    error_log('[LMTS rankings] ' . get_class($e) . ': ' . $e->getMessage());
    rankings_fail(500, 'server error');
}
