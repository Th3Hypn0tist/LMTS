<?php

declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
$config = require dirname(__DIR__, 2) . '/config.php';

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
         FROM LMTS_report_record_index rri
         JOIN LMTS_reports r ON r.report_id = rri.report_id
         $where",
        $params,
    )->fetch() ?: [];

    $telemetryCount = stats_query(
        $pdo,
        "SELECT COUNT(*)
         FROM LMTS_telemetry_values tv
         JOIN LMTS_report_record_index rri
           ON rri.report_id = tv.report_id AND rri.record_id = tv.record_id
         JOIN LMTS_reports r ON r.report_id = rri.report_id
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
            FROM LMTS_telemetry_values input_tv
            WHERE input_tv.report_id = rri.report_id
              AND input_tv.record_id = rri.record_id
              AND input_tv.telemetry_type_id = 'input_tokens'
            ORDER BY input_tv.sample_ordinal, input_tv.telemetry_value_id
            LIMIT 1
        ) AS input_tokens,
        (
            SELECT output_tv.value_number
            FROM LMTS_telemetry_values output_tv
            WHERE output_tv.report_id = rri.report_id
              AND output_tv.record_id = rri.record_id
              AND output_tv.telemetry_type_id = 'output_tokens'
            ORDER BY output_tv.sample_ordinal, output_tv.telemetry_value_id
            LIMIT 1
        ) AS output_tokens
     FROM LMTS_report_record_index rri
     JOIN LMTS_reports r ON r.report_id = rri.report_id
     LEFT JOIN LMTS_model_nodes mn ON mn.model_node_id = rri.model_node_id
     LEFT JOIN LMTS_compositions c ON c.composition_id = rri.composition_id
     LEFT JOIN LMTS_test_versions tv ON tv.test_version_id = rri.test_version_id
     LEFT JOIN LMTS_test_definitions td ON td.test_definition_id = tv.test_definition_id
     LEFT JOIN LMTS_systems s ON s.system_id = rri.system_id
     $where
     ORDER BY COALESCE(rri.started_at, r.created_at) DESC, rri.report_id, rri.record_id
     LIMIT $limit";

    $records = stats_query($pdo, $recordSql, $params)->fetchAll();

    $selectedSql = "SELECT rri.report_id, rri.record_id
        FROM LMTS_report_record_index rri
        JOIN LMTS_reports r ON r.report_id = rri.report_id
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
     FROM LMTS_telemetry_values tv
     JOIN LMTS_telemetry_types tt ON tt.telemetry_type_id = tv.telemetry_type_id
     JOIN ($selectedSql) selected
       ON selected.report_id = tv.report_id AND selected.record_id = tv.record_id
     ORDER BY tt.canonical_key, COALESCE(tv.unit_snapshot, tt.unit), tv.report_id, tv.record_id,
              tv.sample_ordinal, tv.telemetry_value_id";

    $telemetry = stats_query($pdo, $telemetrySql, $params)->fetchAll();

    $users = $pdo->query(
        "SELECT DISTINCT tester_user_id AS user_id
         FROM LMTS_report_record_index
         WHERE tester_user_id IS NOT NULL
         ORDER BY tester_user_id"
    )->fetchAll();

    $systems = $pdo->query(
        "SELECT DISTINCT rri.system_id, COALESCE(s.label, rri.system_id) AS label
         FROM LMTS_report_record_index rri
         LEFT JOIN LMTS_systems s ON s.system_id = rri.system_id
         WHERE rri.system_id IS NOT NULL
         ORDER BY label, rri.system_id"
    )->fetchAll();

    $tests = $pdo->query(
        "SELECT DISTINCT rri.test_version_id,
                CONCAT(COALESCE(td.name, td.namespace, rri.test_version_id),
                       CASE WHEN tv.version IS NULL THEN '' ELSE CONCAT(' @ ', tv.version) END) AS label
         FROM LMTS_report_record_index rri
         LEFT JOIN LMTS_test_versions tv ON tv.test_version_id = rri.test_version_id
         LEFT JOIN LMTS_test_definitions td ON td.test_definition_id = tv.test_definition_id
         WHERE rri.test_version_id IS NOT NULL
         ORDER BY label, rri.test_version_id"
    )->fetchAll();

    $reports = $pdo->query(
        "SELECT report_id, DATE_FORMAT(created_at, '%Y-%m-%dT%H:%i:%s.%fZ') AS created_at
         FROM LMTS_reports
         ORDER BY created_at DESC, imported_at DESC
         LIMIT 500"
    )->fetchAll();

    $outcomes = array_map(
        static fn(array $row): string => (string)$row['outcome'],
        $pdo->query(
            "SELECT DISTINCT COALESCE(outcome, 'unknown') AS outcome
             FROM LMTS_report_record_index
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
         FROM LMTS_report_record_index rri
         LEFT JOIN LMTS_model_nodes mn ON mn.model_node_id = rri.model_node_id
         LEFT JOIN LMTS_compositions c ON c.composition_id = rri.composition_id
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
