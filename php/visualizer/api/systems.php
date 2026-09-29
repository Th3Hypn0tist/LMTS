<?php

declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

$config = require dirname(__DIR__, 2) . '/lmts-report/config.php';

function systems_fail(int $status, string $message): never {
    http_response_code($status);
    echo json_encode(['ok' => false, 'error' => $message], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

try {
    if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
        header('Allow: GET');
        systems_fail(405, 'method not allowed');
    }

    $pdo = new PDO($config['dsn'], $config['user'], $config['password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);

    $systemId = trim((string)($_GET['system_id'] ?? ''));

    $systemSql = "SELECT
        s.system_id,
        s.label,
        s.user_id,
        COALESCE(u.username, s.user_id) AS username,
        u.display_name,
        s.system_class,
        s.probe_version,
        DATE_FORMAT(s.last_probed_at, '%Y-%m-%dT%H:%i:%s.%fZ') AS last_probed_at,
        COUNT(DISTINCT CASE WHEN rri.outcome IN ('pass','fail') THEN rri.record_id END) AS test_executions,
        COUNT(DISTINCT CASE WHEN rri.outcome IN ('pass','fail') THEN rri.test_version_id END) AS unique_tests,
        COUNT(DISTINCT CASE WHEN rri.outcome IN ('pass','fail') THEN CONCAT(rri.target_kind, ':', rri.target_ref) END) AS unique_targets,
        COUNT(DISTINCT CASE WHEN rri.outcome IN ('pass','fail') THEN rri.tester_user_id END) AS contributors
     FROM LMTS_systems s
     LEFT JOIN IAM_users u ON u.user_id = s.user_id
     LEFT JOIN LMTS_report_record_index rri ON rri.system_id = s.system_id";

    $params = [];
    if ($systemId !== '') {
        $systemSql .= " WHERE s.system_id = ?";
        $params[] = $systemId;
    }

    $systemSql .= "
     GROUP BY s.system_id, s.label, s.user_id, u.username, u.display_name,
              s.system_class, s.probe_version, s.last_probed_at
     ORDER BY test_executions DESC, s.label, s.system_id";

    $stmt = $pdo->prepare($systemSql);
    $stmt->execute($params);
    $systems = $stmt->fetchAll();

    $resourceSql = "SELECT
        sr.system_id,
        sr.system_resource_id,
        sr.local_key,
        sr.resource_kind,
        sr.resolution_status,
        hn.hardware_id,
        hn.category,
        hn.label,
        hn.vendor
     FROM LMTS_system_resources sr
     JOIN LMTS_hardware_nodes hn ON hn.hardware_id = sr.hardware_id";
    $resourceParams = [];

    if ($systemId !== '') {
        $resourceSql .= " WHERE sr.system_id = ?";
        $resourceParams[] = $systemId;
    }

    $resourceSql .= " ORDER BY sr.system_id, sr.resource_kind, sr.local_key";
    $stmt = $pdo->prepare($resourceSql);
    $stmt->execute($resourceParams);
    $resources = $stmt->fetchAll();

    $resourceMap = [];
    foreach ($resources as $resource) {
        $id = (string)$resource['system_id'];
        if (!isset($resourceMap[$id])) $resourceMap[$id] = [];
        $resourceMap[$id][] = $resource;
    }

    foreach ($systems as &$system) {
        $system['test_executions'] = (int)$system['test_executions'];
        $system['unique_tests'] = (int)$system['unique_tests'];
        $system['unique_targets'] = (int)$system['unique_targets'];
        $system['contributors'] = (int)$system['contributors'];
        $system['resources'] = $resourceMap[(string)$system['system_id']] ?? [];
    }
    unset($system);

    $details = [];
    if ($systemId !== '') {
        $detail = $pdo->prepare(
            "SELECT
                rri.test_version_id,
                td.namespace AS test_namespace,
                td.name AS test_name,
                tv.version AS test_version,
                rri.target_kind,
                rri.target_ref,
                COALESCE(MAX(rri.target_label), rri.target_ref, rri.target_kind) AS target_label,
                rri.tester_user_id,
                COALESCE(iu.username, rri.tester_user_id) AS username,
                COUNT(*) AS runs,
                SUM(CASE WHEN rri.outcome = 'pass' THEN 1 ELSE 0 END) AS pass,
                SUM(CASE WHEN rri.outcome = 'fail' THEN 1 ELSE 0 END) AS fail,
                MAX(COALESCE(rri.started_at, r.created_at)) AS latest_at
             FROM LMTS_report_record_index rri
             JOIN LMTS_reports r ON r.report_id = rri.report_id
             LEFT JOIN LMTS_test_versions tv ON tv.test_version_id = rri.test_version_id
             LEFT JOIN LMTS_test_definitions td ON td.test_definition_id = tv.test_definition_id
             LEFT JOIN IAM_users iu ON iu.user_id = rri.tester_user_id
             WHERE rri.system_id = ?
               AND rri.outcome IN ('pass','fail')
             GROUP BY
                rri.test_version_id, td.namespace, td.name, tv.version,
                rri.target_kind, rri.target_ref,
                rri.tester_user_id, iu.username
             ORDER BY latest_at DESC, test_name, target_label"
        );
        $detail->execute([$systemId]);
        $details = $detail->fetchAll();

        foreach ($details as &$row) {
            $row['runs'] = (int)$row['runs'];
            $row['pass'] = (int)$row['pass'];
            $row['fail'] = (int)$row['fail'];
        }
        unset($row);
    }

    echo json_encode([
        'format' => 'lmts.systems',
        'version' => 1,
        'systems' => $systems,
        'details' => $details,
    ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
} catch (JsonException $e) {
    systems_fail(500, 'systems serialization failed');
} catch (Throwable $e) {
    error_log('[LMTS systems] ' . get_class($e) . ': ' . $e->getMessage());
    systems_fail(500, 'server error');
}
