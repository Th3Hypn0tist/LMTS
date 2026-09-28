<?php

declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
$config = require dirname(__DIR__, 2) . '/lmts-report/config.php';

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

function stats_scope(bool $includeConfiguration = true): array {
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

    $configurationId = stats_param('configuration_id');
    if ($includeConfiguration && $configurationId !== null) {
        $conditions[] = 'rri.system_id IN (
            SELECT system_id
            FROM LMTS_systems
            WHERE configuration_id = ?
        )';
        $params[] = $configurationId;
    }

    $outcome = stats_param('outcome');
    if ($outcome !== null) {
        if (!in_array($outcome, ['pass', 'fail'], true)) {
            stats_fail(400, 'outcome must be pass or fail');
        }
        $conditions[] = 'rri.outcome = ?';
        $params[] = $outcome;
    }

    $targetId = stats_param('target_id');
    $targetKind = stats_param('target_kind');
    if ($targetId !== null) {
        if ($targetKind === null) {
            stats_fail(400, 'target_id requires target_kind');
        }
        $conditions[] = 'rri.target_ref = ?';
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

function stats_add_condition(string $where, string $condition): string {
    return $where === '' ? 'WHERE ' . $condition : $where . ' AND ' . $condition;
}

function stats_positive_number(mixed $value): ?float {
    if (!is_int($value) && !is_float($value)) return null;
    $number = (float)$value;
    return $number > 0 ? $number : null;
}

function stats_gpu_device_dominates(array $higher, array $lower): array {
    $highVram = stats_positive_number($higher['vram_bytes'] ?? null);
    $lowVram = stats_positive_number($lower['vram_bytes'] ?? null);
    if ($highVram === null || $lowVram === null || $highVram < $lowVram) {
        return [false, false];
    }
    $strict = $highVram > $lowVram;
    $required = [
        'lmts.reference.gpu.d2d',
        'lmts.reference.gpu.h2d_pinned',
        'lmts.reference.gpu.d2h_pinned',
        'lmts.reference.gpu.fma_fp32',
    ];
    $highMetrics = isset($higher['metrics']) && is_array($higher['metrics']) ? $higher['metrics'] : [];
    $lowMetrics = isset($lower['metrics']) && is_array($lower['metrics']) ? $lower['metrics'] : [];
    foreach ($required as $metric) {
        $high = stats_positive_number($highMetrics[$metric] ?? null);
        $low = stats_positive_number($lowMetrics[$metric] ?? null);
        if ($high === null || $low === null || $high < $low) {
            return [false, false];
        }
        $strict = $strict || $high > $low;
    }
    return [true, $strict];
}

function stats_match_gpu_devices(array $higher, array $lower): array {
    if (count($higher) < count($lower)) return [false, false];
    $used = [];

    $search = function(int $position, bool $strictSoFar) use (&$search, &$used, $higher, $lower): array {
        if ($position >= count($lower)) {
            return [true, $strictSoFar || count($higher) > count($lower)];
        }
        $low = $lower[$position];
        if (!is_array($low)) return [false, false];
        foreach ($higher as $index => $high) {
            if (isset($used[$index]) || !is_array($high)) continue;
            [$dominates, $strict] = stats_gpu_device_dominates($high, $low);
            if (!$dominates) continue;
            $used[$index] = true;
            [$ok, $finalStrict] = $search($position + 1, $strictSoFar || $strict);
            unset($used[$index]);
            if ($ok) return [true, $finalStrict];
        }
        return [false, false];
    };

    return $search(0, false);
}

function stats_hardware_order_relation(array $lower, array $higher): array {
    if (($lower['schema_version'] ?? null) !== 1 || ($higher['schema_version'] ?? null) !== 1) {
        return ['comparable' => false, 'lower_or_equal' => false, 'strict' => false];
    }
    if (($lower['status'] ?? null) !== 'complete' || ($higher['status'] ?? null) !== 'complete') {
        return ['comparable' => false, 'lower_or_equal' => false, 'strict' => false];
    }
    if (($lower['architecture'] ?? null) !== ($higher['architecture'] ?? null)) {
        return ['comparable' => false, 'lower_or_equal' => false, 'strict' => false];
    }

    $lowAxes = isset($lower['scalar_axes']) && is_array($lower['scalar_axes']) ? $lower['scalar_axes'] : [];
    $highAxes = isset($higher['scalar_axes']) && is_array($higher['scalar_axes']) ? $higher['scalar_axes'] : [];
    $keys = array_values(array_unique(array_merge(array_keys($lowAxes), array_keys($highAxes))));
    sort($keys, SORT_STRING);
    $strict = false;
    foreach ($keys as $key) {
        $low = stats_positive_number($lowAxes[$key] ?? null);
        $high = stats_positive_number($highAxes[$key] ?? null);
        if ($low === null || $high === null) {
            return ['comparable' => false, 'lower_or_equal' => false, 'strict' => false];
        }
        if ($high < $low) {
            return ['comparable' => true, 'lower_or_equal' => false, 'strict' => false];
        }
        $strict = $strict || $high > $low;
    }

    $lowGpu = isset($lower['gpu_devices']) && is_array($lower['gpu_devices']) ? $lower['gpu_devices'] : [];
    $highGpu = isset($higher['gpu_devices']) && is_array($higher['gpu_devices']) ? $higher['gpu_devices'] : [];
    [$gpuOk, $gpuStrict] = stats_match_gpu_devices($highGpu, $lowGpu);
    if (!$gpuOk) {
        return ['comparable' => true, 'lower_or_equal' => false, 'strict' => false];
    }
    return [
        'comparable' => true,
        'lower_or_equal' => true,
        'strict' => $strict || $gpuStrict,
    ];
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
            COUNT(DISTINCT rri.test_version_id) AS tests,
            COUNT(DISTINCT CASE
                WHEN rri.target_ref IS NULL THEN NULL
                ELSE CONCAT(rri.target_kind, ':', rri.target_ref)
            END) AS targets,
            COUNT(DISTINCT rri.system_id) AS systems,
            COUNT(DISTINCT s.configuration_id) AS configurations,
            COALESCE(SUM(CASE WHEN rri.outcome = 'pass' THEN 1 ELSE 0 END), 0) AS pass,
            COALESCE(SUM(CASE WHEN rri.outcome = 'fail' THEN 1 ELSE 0 END), 0) AS fail
         FROM LMTS_report_record_index rri
         JOIN LMTS_reports r ON r.report_id = rri.report_id
         LEFT JOIN LMTS_systems s ON s.system_id = rri.system_id
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
        rri.target_ref,
        rri.target_label,
        rri.model_node_id,
        rri.composition_id,
        rri.target_ref AS target_id,
        rri.test_version_id,
        td.test_definition_id,
        td.namespace AS test_namespace,
        td.name AS test_name,
        tv.version AS test_version,
        rri.system_id,
        s.label AS system_label,
        s.configuration_id,
        hc.label AS configuration_label,
        hc.fingerprint AS configuration_fingerprint,
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
     LEFT JOIN LMTS_test_versions tv ON tv.test_version_id = rri.test_version_id
     LEFT JOIN LMTS_test_definitions td ON td.test_definition_id = tv.test_definition_id
     LEFT JOIN LMTS_systems s ON s.system_id = rri.system_id
     LEFT JOIN LMTS_hardware_configurations hc ON hc.configuration_id = s.configuration_id
     $where
     ORDER BY COALESCE(rri.started_at, r.created_at) DESC, rri.report_id, rri.record_id
     LIMIT $limit";

    $records = stats_query($pdo, $recordSql, $params)->fetchAll();

    $overviewWhere = $where === ''
        ? "WHERE rri.target_kind = 'model'"
        : $where . " AND rri.target_kind = 'model'";
    $configurationOverviewSql = "SELECT
        hc.configuration_id,
        hc.label AS configuration_name,
        hc.fingerprint AS configuration_fingerprint,
        COUNT(DISTINCT rri.target_ref) AS models_tested_count,
        NULL AS leading_model,
        NULL AS leading_model_pf_score,
        NULL AS leading_model_time_ms,
        'ranking_contract_unresolved' AS ranking_status
     FROM LMTS_report_record_index rri
     JOIN LMTS_reports r ON r.report_id = rri.report_id
     JOIN LMTS_systems s ON s.system_id = rri.system_id
     JOIN LMTS_hardware_configurations hc ON hc.configuration_id = s.configuration_id
     $overviewWhere
     GROUP BY hc.configuration_id, hc.label, hc.fingerprint
     ORDER BY hc.label, hc.configuration_id";
    $configurationOverview = stats_query($pdo, $configurationOverviewSql, $params)->fetchAll();

    $matrixSql = "SELECT
        rri.target_kind,
        rri.target_ref,
        COALESCE(MAX(rri.target_label), rri.target_ref, rri.target_kind) AS target_label,
        rri.test_version_id,
        CONCAT(COALESCE(td.name, td.namespace, rri.test_version_id),
               CASE WHEN tv.version IS NULL THEN '' ELSE CONCAT(' @ ', tv.version) END) AS test_label,
        COUNT(*) AS runs,
        COALESCE(SUM(CASE WHEN rri.outcome = 'pass' THEN 1 ELSE 0 END), 0) AS pass,
        COALESCE(SUM(CASE WHEN rri.outcome = 'fail' THEN 1 ELSE 0 END), 0) AS fail,
        MAX(COALESCE(rri.started_at, r.created_at)) AS latest_at
     FROM LMTS_report_record_index rri
     JOIN LMTS_reports r ON r.report_id = rri.report_id
     LEFT JOIN LMTS_test_versions tv ON tv.test_version_id = rri.test_version_id
     LEFT JOIN LMTS_test_definitions td ON td.test_definition_id = tv.test_definition_id
     $where
     GROUP BY rri.target_kind, rri.target_ref, rri.test_version_id, td.name, td.namespace, tv.version
     ORDER BY target_label, test_label";
    $matrix = stats_query($pdo, $matrixSql, $params)->fetchAll();

    $configurationMatrix = [];
    $lighterConfigurationIds = [];
    $ignoredIncompleteConfigurationIds = [];
    $hardwareCeilingStatus = null;
    $selectedConfigurationId = stats_param('configuration_id');
    if ($selectedConfigurationId !== null) {
        $configurationRows = $pdo->query(
            "SELECT configuration_id, order_status, order_json
             FROM LMTS_hardware_configurations
             ORDER BY configuration_id"
        )->fetchAll();
        $configurationOrders = [];
        foreach ($configurationRows as $configurationRow) {
            $configurationId = (string)$configurationRow['configuration_id'];
            $order = json_decode((string)$configurationRow['order_json'], true, 512, JSON_THROW_ON_ERROR);
            if (!is_array($order)) {
                throw new RuntimeException('invalid hardware order payload: ' . $configurationId);
            }
            $configurationOrders[$configurationId] = $order;
            if (($configurationRow['order_status'] ?? null) !== 'complete') {
                $ignoredIncompleteConfigurationIds[] = $configurationId;
            }
        }
        if (!array_key_exists($selectedConfigurationId, $configurationOrders)) {
            stats_fail(400, 'unknown configuration_id');
        }

        $selectedOrder = $configurationOrders[$selectedConfigurationId];
        if (($selectedOrder['status'] ?? null) !== 'complete') {
            $hardwareCeilingStatus = 'ordering_evidence_incomplete';
        } else {
            foreach ($configurationOrders as $candidateId => $candidateOrder) {
                if ($candidateId === $selectedConfigurationId || ($candidateOrder['status'] ?? null) !== 'complete') {
                    continue;
                }
                $relation = stats_hardware_order_relation($candidateOrder, $selectedOrder);
                if ($relation['comparable'] && $relation['lower_or_equal'] && $relation['strict']) {
                    $lighterConfigurationIds[] = $candidateId;
                }
            }
            sort($lighterConfigurationIds, SORT_STRING);
            $hardwareCeilingStatus = 'ready';
        }

        [$level2Where, $level2Params] = stats_scope(false);
        $level2Where = stats_add_condition($level2Where, 's.configuration_id = ?');
        $level2Where = stats_add_condition($level2Where, "rri.target_kind = 'model'");
        $level2Where = stats_add_condition($level2Where, "rri.outcome IN ('pass','fail')");
        $level2Params[] = $selectedConfigurationId;

        $configurationMatrixSql = "SELECT
            s.configuration_id,
            rri.target_kind,
            rri.target_ref,
            COALESCE(MAX(rri.target_label), rri.target_ref) AS target_label,
            rri.test_version_id,
            CONCAT(COALESCE(td.name, td.namespace, rri.test_version_id),
                   CASE WHEN tv.version IS NULL THEN '' ELSE CONCAT(' @ ', tv.version) END) AS test_label,
            JSON_ARRAYAGG(rri.duration_ms) AS total_time_samples_json
         FROM LMTS_report_record_index rri
         JOIN LMTS_reports r ON r.report_id = rri.report_id
         JOIN LMTS_systems s ON s.system_id = rri.system_id
         LEFT JOIN LMTS_test_versions tv ON tv.test_version_id = rri.test_version_id
         LEFT JOIN LMTS_test_definitions td ON td.test_definition_id = tv.test_definition_id
         $level2Where
         GROUP BY s.configuration_id, rri.target_kind, rri.target_ref,
                  rri.test_version_id, td.name, td.namespace, tv.version
         ORDER BY target_label, test_label";
        $configurationMatrix = stats_query(
            $pdo,
            $configurationMatrixSql,
            $level2Params,
        )->fetchAll();

        [$varianceWhere, $varianceParams] = stats_scope(false);
        $varianceWhere = stats_add_condition($varianceWhere, 'vs.configuration_id = ?');
        $varianceWhere = stats_add_condition($varianceWhere, "vs.target_kind = 'model'");
        $varianceParams[] = $selectedConfigurationId;
        $configurationVarianceSql = "SELECT
            vs.target_ref,
            vs.test_version_id,
            COUNT(*) AS sample_count,
            SUM(CASE WHEN vs.outcome = 'pass' THEN 1 ELSE 0 END) AS pass_count,
            SUM(CASE WHEN vs.outcome = 'fail' THEN 1 ELSE 0 END) AS fail_count,
            (100.0 * SUM(CASE WHEN vs.outcome = 'pass' THEN 1 ELSE 0 END) / COUNT(*)) AS pf_score
         FROM LMTS_variance_samples vs
         JOIN LMTS_report_record_index rri
           ON rri.report_id = vs.source_report_id AND rri.record_id = vs.source_record_id
         JOIN LMTS_reports r ON r.report_id = rri.report_id
         $varianceWhere
         GROUP BY vs.target_ref, vs.test_version_id";
        $configurationVarianceRows = stats_query(
            $pdo,
            $configurationVarianceSql,
            $varianceParams,
        )->fetchAll();
        $configurationVariance = [];
        foreach ($configurationVarianceRows as $varianceRow) {
            $varianceKey = (string)$varianceRow['target_ref'] . "\0" . (string)$varianceRow['test_version_id'];
            $configurationVariance[$varianceKey] = $varianceRow;
        }

        $cellIndex = [];
        foreach ($configurationMatrix as &$configurationCell) {
            $rawSamples = $configurationCell['total_time_samples_json'] ?? '[]';
            $decodedSamples = json_decode((string)$rawSamples, true);
            $configurationCell['total_time_samples_ms'] = is_array($decodedSamples)
                ? array_values(array_filter(
                    $decodedSamples,
                    static fn($value): bool => is_int($value) || is_float($value) || is_numeric($value)
                ))
                : [];
            unset($configurationCell['total_time_samples_json']);
            $key = (string)$configurationCell['target_ref'] . "\0" . (string)$configurationCell['test_version_id'];
            $varianceEvidence = $configurationVariance[$key] ?? null;
            $configurationCell['sample_count'] = $varianceEvidence === null ? 0 : (int)$varianceEvidence['sample_count'];
            $configurationCell['pass_count'] = $varianceEvidence === null ? 0 : (int)$varianceEvidence['pass_count'];
            $configurationCell['fail_count'] = $varianceEvidence === null ? 0 : (int)$varianceEvidence['fail_count'];
            $configurationCell['pf_score'] = $varianceEvidence === null ? null : (float)$varianceEvidence['pf_score'];
            $configurationCell['evidence_scope'] = 'exact';
            $configurationCell['compatibility_status'] =
                ((int)$configurationCell['pass_count']) > 0 ? 'pass' : 'fail';
            $configurationCell['source_configuration_ids'] = [$selectedConfigurationId];
            $configurationCell['performance_scope'] = 'exact';
            $cellIndex[$key] = true;
        }
        unset($configurationCell);

        if ($hardwareCeilingStatus === 'ready' && $lighterConfigurationIds !== []) {
            [$lighterWhere, $lighterParams] = stats_scope(false);
            $placeholders = implode(',', array_fill(0, count($lighterConfigurationIds), '?'));
            $lighterWhere = stats_add_condition($lighterWhere, "vs.configuration_id IN ($placeholders)");
            $lighterWhere = stats_add_condition($lighterWhere, "vs.target_kind = 'model'");
            $lighterWhere = stats_add_condition($lighterWhere, "vs.outcome IN ('pass','fail')");
            $lighterParams = array_merge($lighterParams, $lighterConfigurationIds);

            $lighterSql = "SELECT
                vs.target_kind,
                vs.target_ref,
                COALESCE(MAX(rri.target_label), vs.target_ref) AS target_label,
                vs.test_version_id,
                CONCAT(COALESCE(td.name, td.namespace, vs.test_version_id),
                       CASE WHEN tv.version IS NULL THEN '' ELSE CONCAT(' @ ', tv.version) END) AS test_label,
                SUM(CASE WHEN vs.outcome = 'pass' THEN 1 ELSE 0 END) AS source_pass_count,
                SUM(CASE WHEN vs.outcome = 'fail' THEN 1 ELSE 0 END) AS source_fail_count,
                GROUP_CONCAT(DISTINCT vs.configuration_id ORDER BY vs.configuration_id SEPARATOR ',') AS source_configuration_ids_csv
             FROM LMTS_variance_samples vs
             JOIN LMTS_report_record_index rri
               ON rri.report_id = vs.source_report_id AND rri.record_id = vs.source_record_id
             JOIN LMTS_reports r ON r.report_id = rri.report_id
             LEFT JOIN LMTS_test_versions tv ON tv.test_version_id = vs.test_version_id
             LEFT JOIN LMTS_test_definitions td ON td.test_definition_id = tv.test_definition_id
             $lighterWhere
             GROUP BY vs.target_kind, vs.target_ref, vs.test_version_id,
                      td.name, td.namespace, tv.version
             ORDER BY target_label, test_label";
            $lighterRows = stats_query($pdo, $lighterSql, $lighterParams)->fetchAll();

            foreach ($lighterRows as $lighterRow) {
                $key = (string)$lighterRow['target_ref'] . "\0" . (string)$lighterRow['test_version_id'];
                if (isset($cellIndex[$key])) {
                    continue;
                }
                $sourceIds = array_values(array_filter(
                    explode(',', (string)($lighterRow['source_configuration_ids_csv'] ?? '')),
                    static fn(string $value): bool => $value !== ''
                ));
                $sourcePassCount = (int)($lighterRow['source_pass_count'] ?? 0);
                $sourceFailCount = (int)($lighterRow['source_fail_count'] ?? 0);
                $inferredPass = $sourcePassCount > 0;
                $configurationMatrix[] = [
                    'configuration_id' => $selectedConfigurationId,
                    'target_kind' => (string)$lighterRow['target_kind'],
                    'target_ref' => (string)$lighterRow['target_ref'],
                    'target_label' => (string)$lighterRow['target_label'],
                    'test_version_id' => (string)$lighterRow['test_version_id'],
                    'test_label' => (string)$lighterRow['test_label'],
                    'sample_count' => null,
                    'pass_count' => null,
                    'fail_count' => null,
                    'pf_score' => null,
                    'total_time_samples_ms' => [],
                    'evidence_scope' => $inferredPass ? 'inferred_lighter_pass' : 'lower_fail_only',
                    'compatibility_status' => $inferredPass ? 'pass' : 'unknown',
                    'source_configuration_ids' => $sourceIds,
                    'source_pass_count' => $sourcePassCount,
                    'source_fail_count' => $sourceFailCount,
                    'performance_scope' => 'none',
                ];
                $cellIndex[$key] = true;
            }
        }
    }

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

    $varianceSql = "SELECT
        grouped.target_kind,
        grouped.target_ref,
        grouped.test_version_id,
        grouped.configuration_id,
        grouped.sample_count,
        grouped.pass_count,
        grouped.fail_count,
        CASE WHEN grouped.pass_count > 0 THEN 'pass' ELSE 'fail' END AS status,
        (100.0 * grouped.pass_count / grouped.sample_count) AS pf_score,
        (
            (grouped.pass_count / grouped.sample_count)
            * (1.0 - (grouped.pass_count / grouped.sample_count))
        ) AS variance
     FROM (
        SELECT
            vs.target_kind,
            vs.target_ref,
            vs.test_version_id,
            vs.configuration_id,
            COUNT(*) AS sample_count,
            SUM(CASE WHEN vs.outcome = 'pass' THEN 1 ELSE 0 END) AS pass_count,
            SUM(CASE WHEN vs.outcome = 'fail' THEN 1 ELSE 0 END) AS fail_count
        FROM LMTS_variance_samples vs
        GROUP BY vs.target_kind, vs.target_ref, vs.test_version_id, vs.configuration_id
     ) grouped
     ORDER BY grouped.target_kind, grouped.target_ref, grouped.test_version_id, grouped.configuration_id";
    $variance = stats_query($pdo, $varianceSql)->fetchAll();

    $users = $pdo->query(
        "SELECT DISTINCT tester_user_id AS user_id
         FROM LMTS_report_record_index
         WHERE tester_user_id IS NOT NULL
         ORDER BY tester_user_id"
    )->fetchAll();

    $systems = $pdo->query(
        "SELECT DISTINCT
            rri.system_id,
            COALESCE(s.label, rri.system_id) AS label,
            s.configuration_id
         FROM LMTS_report_record_index rri
         LEFT JOIN LMTS_systems s ON s.system_id = rri.system_id
         WHERE rri.system_id IS NOT NULL
         ORDER BY label, rri.system_id"
    )->fetchAll();

    $configurations = $pdo->query(
        "SELECT DISTINCT
            hc.configuration_id,
            hc.label,
            hc.fingerprint
         FROM LMTS_report_record_index rri
         JOIN LMTS_systems s ON s.system_id = rri.system_id
         JOIN LMTS_hardware_configurations hc ON hc.configuration_id = s.configuration_id
         ORDER BY hc.label, hc.configuration_id"
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
            "SELECT DISTINCT outcome
             FROM LMTS_report_record_index
             WHERE outcome IN ('pass','fail')
             ORDER BY outcome"
        )->fetchAll(),
    );

    $targets = $pdo->query(
        "SELECT DISTINCT
            rri.target_kind,
            rri.target_ref AS target_id,
            COALESCE(rri.target_label, rri.target_ref, CONCAT(rri.target_kind, ' (unresolved)')) AS label
         FROM LMTS_report_record_index rri
         ORDER BY label, rri.target_kind"
    )->fetchAll();
    foreach ($targets as &$target) {
        $target['value'] = (string)$target['target_kind'] . ':' . (string)($target['target_id'] ?? '');
    }
    unset($target);

    $selected = [
        'user_id' => stats_param('user_id'),
        'system_id' => stats_param('system_id'),
        'configuration_id' => stats_param('configuration_id'),
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
            'tests' => (int)($summary['tests'] ?? 0),
            'targets' => (int)($summary['targets'] ?? 0),
            'systems' => (int)($summary['systems'] ?? 0),
            'configurations' => (int)($summary['configurations'] ?? 0),
            'pass' => (int)($summary['pass'] ?? 0),
            'fail' => (int)($summary['fail'] ?? 0),
            'telemetry_values' => (int)$telemetryCount,
        ],
        'configuration_overview' => $configurationOverview,
        'configuration_matrix' => [
            'configuration_id' => $selectedConfigurationId,
            'evidence_scope' => $selectedConfigurationId === null ? null : 'exact_plus_compatibility',
            'hardware_ceiling_status' => $hardwareCeilingStatus,
            'lighter_configuration_ids' => $lighterConfigurationIds,
            'ignored_incomplete_configuration_ids' => $ignoredIncompleteConfigurationIds,
            'cells' => $configurationMatrix,
        ],
        'matrix' => $matrix,
        'records' => $records,
        'telemetry' => $telemetry,
        'variance' => $variance,
        'filters' => [
            'selected' => $selected,
            'options' => [
                'users' => $users,
                'systems' => $systems,
                'configurations' => $configurations,
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
