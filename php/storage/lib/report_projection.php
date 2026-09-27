<?php

declare(strict_types=1);

const LMTS_PROJECTION_TELEMETRY_UNITS = [
    'input_tokens' => 'tokens',
    'output_tokens' => 'tokens',
    'ttft' => 'ms',
    'total_time' => 'ms',
    'score_percent' => 'percent',
    'workspace_protocol_steps' => 'steps',
    'output_file_count' => 'files',
    'exact_output_match' => null,
    'cpu_util_percent' => 'percent',
    'memory_used_bytes' => 'bytes',
    'gpu_util_percent' => 'percent',
    'gpu_memory_util_percent' => 'percent',
    'gpu_memory_used_mib' => 'MiB',
    'gpu_temperature_c' => 'C',
    'gpu_power_w' => 'W',
];

function lmts_projection_canonicalize(mixed $value): mixed {
    if (!is_array($value)) return $value;
    if (array_is_list($value)) {
        return array_map('lmts_projection_canonicalize', $value);
    }
    ksort($value, SORT_STRING);
    foreach ($value as $key => $item) {
        $value[$key] = lmts_projection_canonicalize($item);
    }
    return $value;
}

function lmts_projection_json(mixed $value): string {
    return json_encode(
        lmts_projection_canonicalize($value),
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR,
    );
}

function lmts_projection_stable_id(string $prefix, string ...$parts): string {
    return $prefix . substr(hash('sha256', implode("\0", $parts)), 0, 40);
}

function lmts_projection_test_identity(string $testRef): array {
    if (preg_match('/^([A-Za-z0-9_.-]+)@([^#\\s]+)(?:#([^#\\s]+))?$/', trim($testRef), $match) !== 1) {
        throw new InvalidArgumentException("invalid canonical test_ref: $testRef");
    }
    return [
        'type_id' => $match[1],
        'version' => $match[2],
        'instance_id' => $match[3] ?? null,
    ];
}

function lmts_projection_test_spec(string $testRef, array $entity): array {
    $identity = lmts_projection_test_identity($testRef);
    $props = isset($entity['properties']) && is_array($entity['properties']) ? $entity['properties'] : [];

    $namespace = trim((string)($props['namespace'] ?? $identity['type_id']));
    $version = trim((string)($props['version'] ?? $identity['version']));
    $title = trim((string)($props['title'] ?? $entity['label'] ?? $namespace));
    $description = array_key_exists('description', $props) && $props['description'] !== null
        ? (string)$props['description']
        : null;

    if ($namespace === '' || $version === '' || $title === '') {
        throw new InvalidArgumentException("test projection requires namespace, version and title: $testRef");
    }

    $rawTelemetry = $props['telemetry_types'] ?? [];
    if (!is_array($rawTelemetry)) {
        throw new InvalidArgumentException("test telemetry_types must be an array: $testRef");
    }
    $telemetryTypes = [];
    foreach ($rawTelemetry as $item) {
        if (!is_string($item)) continue;
        $item = trim($item);
        if ($item !== '') $telemetryTypes[] = $item;
    }

    $definition = [
        'namespace' => $namespace,
        'version' => $version,
        'title' => $title,
        'description' => $description,
        'minimum_level' => $props['minimum_level'] ?? null,
        'mandatory' => $props['mandatory'] ?? null,
        'taxonomy' => $props['taxonomy'] ?? null,
        'telemetry_types' => $telemetryTypes,
    ];
    $definitionJson = lmts_projection_json($definition);
    $fingerprint = hash('sha256', $definitionJson);

    return [
        'test_definition_id' => lmts_projection_stable_id('testdef_', $namespace),
        'test_version_id' => lmts_projection_stable_id('testver_', $namespace, $version, $fingerprint),
        'namespace' => $namespace,
        'version' => $version,
        'title' => $title,
        'description' => $description,
        'telemetry_types' => $telemetryTypes,
        'definition_json' => $definitionJson,
        'fingerprint' => $fingerprint,
    ];
}

function lmts_projection_mysql_datetime(mixed $value): ?string {
    if (!is_string($value) || trim($value) === '') return null;
    $date = new DateTimeImmutable($value);
    return $date->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s.u');
}

function lmts_projection_duration_ms(mixed $started, mixed $completed): ?float {
    if (!is_string($started) || !is_string($completed) || trim($started) === '' || trim($completed) === '') {
        return null;
    }
    $start = new DateTimeImmutable($started);
    $end = new DateTimeImmutable($completed);
    return max(0.0, ((float)$end->format('U.u') - (float)$start->format('U.u')) * 1000.0);
}

function lmts_projection_metric_value(array $record, string $name): mixed {
    $metrics = isset($record['metrics']) && is_array($record['metrics']) ? $record['metrics'] : [];
    $metric = $metrics[$name] ?? null;
    return is_array($metric) ? ($metric['value'] ?? null) : null;
}

function lmts_projection_context_json(string $source, array $values = []): string {
    return lmts_projection_json(['source' => $source, ...$values]);
}

function lmts_projection_has_identity_value(mixed $value): bool {
    if ($value === null) return false;
    if (is_string($value)) return trim($value) !== '';
    if (is_array($value)) return $value !== [];
    return true;
}

function lmts_projection_identity_resolution(array $identity, array $requiredKeys): string {
    $requiredPresent = 0;
    foreach ($requiredKeys as $key) {
        if (array_key_exists($key, $identity) && lmts_projection_has_identity_value($identity[$key])) {
            $requiredPresent++;
        }
    }
    if ($requiredPresent === count($requiredKeys)) return 'exact';
    foreach ($identity as $value) {
        if (lmts_projection_has_identity_value($value)) return 'partial';
    }
    return 'unknown';
}

function lmts_projection_hardware_spec(string $category, array $probe): ?array {
    if ($category === 'cpu') {
        $identity = [
            'architecture' => $probe['architecture'] ?? null,
            'vendor_id' => $probe['vendor_id'] ?? null,
            'model_name' => $probe['model_name'] ?? null,
        ];
        $required = ['architecture', 'vendor_id', 'model_name'];
        $label = trim((string)($probe['model_name'] ?? '')) ?: 'Unknown CPU';
        $vendor = trim((string)($probe['vendor_id'] ?? '')) ?: null;
    } elseif ($category === 'gpu') {
        $identity = [
            'vendor' => $probe['vendor'] ?? null,
            'model' => $probe['model'] ?? null,
            'vram_bytes' => $probe['vram_bytes'] ?? null,
        ];
        $required = ['vendor', 'model', 'vram_bytes'];
        $label = trim((string)($probe['model'] ?? ''))
            ?: (trim((string)($probe['vendor'] ?? '')) ?: 'Unknown GPU');
        $vendor = trim((string)($probe['vendor'] ?? '')) ?: null;
    } elseif ($category === 'npu') {
        $identity = [
            'class' => $probe['class'] ?? null,
            'vendor_id' => $probe['vendor_id'] ?? null,
            'device_id' => $probe['device_id'] ?? null,
            'subsystem_vendor_id' => $probe['subsystem_vendor_id'] ?? null,
            'subsystem_device_id' => $probe['subsystem_device_id'] ?? null,
            'modalias' => $probe['modalias'] ?? null,
        ];
        $required = ['vendor_id', 'device_id'];
        $label = trim((string)($probe['name'] ?? ''));
        if ($label === '') {
            $vendorId = trim((string)($probe['vendor_id'] ?? ''));
            $deviceId = trim((string)($probe['device_id'] ?? ''));
            $label = trim($vendorId . ($vendorId !== '' && $deviceId !== '' ? ':' : '') . $deviceId);
        }
        if ($label === '') $label = 'Unknown NPU';
        $vendor = trim((string)($probe['vendor_id'] ?? '')) ?: null;
    } else {
        throw new InvalidArgumentException("unsupported hardware category: $category");
    }

    $hasIdentity = false;
    foreach ($identity as $value) {
        if (lmts_projection_has_identity_value($value)) {
            $hasIdentity = true;
            break;
        }
    }
    if (!$hasIdentity) return null;

    $identityJson = lmts_projection_json($identity);
    $digest = hash('sha256', $category . "\0" . $identityJson);

    return [
        'hardware_id' => 'hw_' . substr($digest, 0, 40),
        'category' => $category,
        'canonical_key' => $category . ':' . $digest,
        'label' => $label,
        'vendor' => $vendor,
        'resolution_type' => lmts_projection_identity_resolution($identity, $required),
        'identity_json' => $identityJson,
        'profile_json' => lmts_projection_json($probe),
    ];
}

function lmts_projection_upsert_hardware(PDO $pdo, array $hardware): void {
    $stmt = $pdo->prepare(
        'INSERT INTO LMTS_hardware_nodes (
            hardware_id, category, level, parent_id, canonical_key,
            label, vendor, resolution_type, identity_json, profile_json
         ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
         ON DUPLICATE KEY UPDATE
            label = VALUES(label),
            vendor = VALUES(vendor),
            resolution_type = VALUES(resolution_type),
            profile_json = VALUES(profile_json)'
    );
    $stmt->execute([
        $hardware['hardware_id'],
        $hardware['category'],
        'component',
        $hardware['canonical_key'],
        $hardware['label'],
        $hardware['vendor'],
        $hardware['resolution_type'],
        $hardware['identity_json'],
        $hardware['profile_json'],
    ]);

    $check = $pdo->prepare(
        'SELECT hardware_id, identity_json
         FROM LMTS_hardware_nodes
         WHERE canonical_key = ?
         LIMIT 1'
    );
    $check->execute([$hardware['canonical_key']]);
    $row = $check->fetch();
    if (!is_array($row)
        || !hash_equals((string)$row['hardware_id'], (string)$hardware['hardware_id'])
        || !hash_equals((string)$row['identity_json'], (string)$hardware['identity_json'])) {
        throw new RuntimeException(
            'canonical hardware identity conflict: ' . $hardware['canonical_key']
        );
    }
}

function lmts_projection_upsert_system_resource(
    PDO $pdo,
    string $systemId,
    string $localKey,
    string $resourceKind,
    array $hardware,
    array $probe,
): void {
    $resourceId = lmts_projection_stable_id('sysres_', $systemId, $localKey);
    $stmt = $pdo->prepare(
        'INSERT INTO LMTS_system_resources (
            system_resource_id, system_id, local_key, resource_kind,
            hardware_id, resolution_status, probe_data_json
         ) VALUES (?, ?, ?, ?, ?, ?, ?)
         ON DUPLICATE KEY UPDATE
            hardware_id = VALUES(hardware_id),
            resolution_status = VALUES(resolution_status),
            probe_data_json = VALUES(probe_data_json),
            updated_at = CURRENT_TIMESTAMP(6)'
    );
    $stmt->execute([
        $resourceId,
        $systemId,
        $localKey,
        $resourceKind,
        $hardware['hardware_id'],
        $hardware['resolution_type'],
        lmts_projection_json($probe),
    ]);
}

function lmts_projection_project_memory_pool(PDO $pdo, string $systemId, array $memory): void {
    $capacity = $memory['total_bytes'] ?? null;
    if (is_string($capacity) && ctype_digit($capacity)) $capacity = (int)$capacity;
    if (!is_int($capacity) || $capacity <= 0) return;

    $poolKind = 'system';
    $poolId = lmts_projection_stable_id('mempool_', $systemId, $poolKind);
    $stmt = $pdo->prepare(
        'INSERT INTO LMTS_system_memory_pools (
            memory_pool_id, system_id, pool_kind, capacity_bytes, properties_json
         ) VALUES (?, ?, ?, ?, ?)
         ON DUPLICATE KEY UPDATE
            capacity_bytes = VALUES(capacity_bytes),
            properties_json = VALUES(properties_json)'
    );
    $stmt->execute([
        $poolId,
        $systemId,
        $poolKind,
        $capacity,
        lmts_projection_json($memory),
    ]);
}

function lmts_projection_project_system_profile(PDO $pdo, string $systemId, array $profile): void {
    $cpu = isset($profile['cpu']) && is_array($profile['cpu']) ? $profile['cpu'] : [];
    if ($cpu !== []) {
        $hardware = lmts_projection_hardware_spec('cpu', $cpu);
        if ($hardware !== null) {
            lmts_projection_upsert_hardware($pdo, $hardware);
            lmts_projection_upsert_system_resource(
                $pdo,
                $systemId,
                'cpu:0',
                'cpu',
                $hardware,
                $cpu,
            );
        }
    }

    $gpus = isset($profile['gpu']) && is_array($profile['gpu']) ? $profile['gpu'] : [];
    foreach ($gpus as $index => $gpu) {
        if (!is_array($gpu)) continue;
        $hardware = lmts_projection_hardware_spec('gpu', $gpu);
        if ($hardware === null) continue;
        lmts_projection_upsert_hardware($pdo, $hardware);
        lmts_projection_upsert_system_resource(
            $pdo,
            $systemId,
            'gpu:' . (int)$index,
            'gpu',
            $hardware,
            $gpu,
        );
    }

    $npus = isset($profile['npu']) && is_array($profile['npu']) ? $profile['npu'] : [];
    foreach ($npus as $index => $npu) {
        if (!is_array($npu)) continue;
        $hardware = lmts_projection_hardware_spec('npu', $npu);
        if ($hardware === null) continue;
        lmts_projection_upsert_hardware($pdo, $hardware);
        lmts_projection_upsert_system_resource(
            $pdo,
            $systemId,
            'npu:' . (int)$index,
            'npu',
            $hardware,
            $npu,
        );
    }

    $memory = isset($profile['memory']) && is_array($profile['memory']) ? $profile['memory'] : [];
    if ($memory !== []) {
        lmts_projection_project_memory_pool($pdo, $systemId, $memory);
    }
}

function lmts_projection_ensure_system_identity(
    PDO $pdo,
    string $userId,
    string $systemId,
    array $context,
): void {
    $fingerprint = trim((string)($context['fingerprint'] ?? ''));
    $schemaVersion = $context['schema_version'] ?? null;
    $profile = $context['profile'] ?? null;

    if ($fingerprint === '' || !is_int($schemaVersion) || !is_array($profile)) {
        throw new RuntimeException("system_context for $systemId has invalid canonical identity");
    }

    $expectedId = lmts_projection_stable_id('sys_', $userId, $fingerprint);
    if (!hash_equals($expectedId, $systemId)) {
        throw new RuntimeException("system_id $systemId does not match report system_context fingerprint");
    }

    $check = $pdo->prepare(
        'SELECT user_id
         FROM LMTS_systems
         WHERE system_id = ?
         LIMIT 1'
    );
    $check->execute([$systemId]);
    $existingUser = $check->fetchColumn();

    $label = 'System ' . substr($fingerprint, 0, 12);
    $probeVersion = 'profile-v' . $schemaVersion;
    $profiledAt = lmts_projection_mysql_datetime($context['profiled_at'] ?? null);

    if ($existingUser === false) {
        $insert = $pdo->prepare(
            'INSERT INTO LMTS_systems (
                system_id, user_id, label, system_class, probe_version, last_probed_at
             ) VALUES (?, ?, ?, ?, ?, ?)'
        );
        $insert->execute([
            $systemId,
            $userId,
            $label,
            'local',
            $probeVersion,
            $profiledAt,
        ]);
        return;
    }

    if (!hash_equals((string)$existingUser, $userId)) {
        throw new RuntimeException("system $systemId is owned by a different user");
    }

    if ($profiledAt === null) {
        $update = $pdo->prepare(
            'UPDATE LMTS_systems
             SET probe_version = ?
             WHERE system_id = ?'
        );
        $update->execute([$probeVersion, $systemId]);
    } else {
        $update = $pdo->prepare(
            'UPDATE LMTS_systems
             SET probe_version = ?,
                 last_probed_at = CASE
                     WHEN last_probed_at IS NULL OR last_probed_at < ? THEN ?
                     ELSE last_probed_at
                 END
             WHERE system_id = ?'
        );
        $update->execute([$probeVersion, $profiledAt, $profiledAt, $systemId]);
    }
}

function lmts_projection_ensure_system(PDO $pdo, array $record): void {
    $provenance = isset($record['provenance']) && is_array($record['provenance'])
        ? $record['provenance']
        : [];
    $userId = trim((string)($provenance['tester_user_id'] ?? ''));
    $systemId = trim((string)($provenance['system_id'] ?? ''));
    if ($userId === '' || $systemId === '') return;

    $evidence = isset($record['evidence']) && is_array($record['evidence'])
        ? $record['evidence']
        : [];
    $context = isset($evidence['system_context']) && is_array($evidence['system_context'])
        ? $evidence['system_context']
        : null;

    if ($context === null) {
        throw new RuntimeException(
            "report references system $systemId without system_context evidence"
        );
    }

    $profile = $context['profile'] ?? null;
    if (!is_array($profile)) {
        throw new RuntimeException("system_context for $systemId has no profile");
    }

    lmts_projection_ensure_system_identity($pdo, $userId, $systemId, $context);
    lmts_projection_project_system_profile($pdo, $systemId, $profile);
}

function lmts_projection_assert_compute_profile(PDO $pdo, array $record): void {
    $provenance = isset($record['provenance']) && is_array($record['provenance']) ? $record['provenance'] : [];
    $computeProfileId = trim((string)($provenance['compute_profile_id'] ?? ''));
    if ($computeProfileId === '') return;

    $userId = trim((string)($provenance['tester_user_id'] ?? ''));
    $systemId = trim((string)($provenance['system_id'] ?? ''));
    $stmt = $pdo->prepare(
        'SELECT 1
         FROM LMTS_compute_profiles
         WHERE compute_profile_id = ? AND user_id = ? AND system_id = ?
         LIMIT 1'
    );
    $stmt->execute([$computeProfileId, $userId, $systemId]);
    if ($stmt->fetchColumn() === false) {
        throw new RuntimeException("report references unknown compute profile $computeProfileId");
    }
}

function lmts_projection_ensure_test(PDO $pdo, array $test): void {
    $definition = $pdo->prepare(
        'INSERT INTO LMTS_test_definitions (
            test_definition_id, namespace, name, description, category
         ) VALUES (?, ?, ?, ?, NULL)
         ON DUPLICATE KEY UPDATE test_definition_id = test_definition_id'
    );
    $definition->execute([
        $test['test_definition_id'],
        $test['namespace'],
        $test['title'],
        $test['description'],
    ]);

    $existing = $pdo->prepare(
        'SELECT test_version_id, fingerprint
         FROM LMTS_test_versions
         WHERE test_definition_id = ? AND version = ?
         LIMIT 1'
    );
    $existing->execute([$test['test_definition_id'], $test['version']]);
    $row = $existing->fetch();
    if (is_array($row)) {
        if (!hash_equals((string)$row['fingerprint'], $test['fingerprint'])
            || !hash_equals((string)$row['test_version_id'], $test['test_version_id'])) {
            throw new RuntimeException(
                'immutable test version conflict: ' . $test['namespace'] . '@' . $test['version']
            );
        }
    } else {
        $version = $pdo->prepare(
            'INSERT INTO LMTS_test_versions (
                test_version_id, test_definition_id, version, kind,
                definition_json, fingerprint, status
             ) VALUES (?, ?, ?, ?, ?, ?, ?)'
        );
        $version->execute([
            $test['test_version_id'],
            $test['test_definition_id'],
            $test['version'],
            'standard',
            $test['definition_json'],
            $test['fingerprint'],
            'candidate',
        ]);
    }

    $telemetry = $pdo->prepare(
        'INSERT INTO LMTS_test_version_telemetry_types (
            test_version_id, telemetry_type_id, required, ordinal
         ) VALUES (?, ?, ?, ?)
         ON DUPLICATE KEY UPDATE test_version_id = test_version_id'
    );
    foreach ($test['telemetry_types'] as $ordinal => $telemetryType) {
        $telemetry->execute([$test['test_version_id'], $telemetryType, 0, (int)$ordinal]);
    }
}

function lmts_projection_insert_telemetry(
    PDO $pdo,
    string $reportId,
    string $recordId,
    string $userId,
    string $systemId,
    ?string $computeProfileId,
    array $test,
    string $telemetryTypeId,
    int $sampleOrdinal,
    mixed $value,
    ?string $observedAt,
    string $contextJson,
): void {
    if ($value === null || !in_array($telemetryTypeId, $test['telemetry_types'], true)) return;

    $valueNumber = null;
    $valueText = null;
    $valueBoolean = null;
    $valueJson = null;
    if (is_bool($value)) {
        $valueBoolean = $value ? 1 : 0;
    } elseif (is_int($value) || is_float($value)) {
        $valueNumber = $value;
    } elseif (is_string($value)) {
        $valueText = $value;
    } else {
        $valueJson = lmts_projection_json($value);
    }

    $unit = LMTS_PROJECTION_TELEMETRY_UNITS[$telemetryTypeId] ?? null;
    $stmt = $pdo->prepare(
        'INSERT INTO LMTS_telemetry_values (
            report_id, record_id, user_id, system_id, compute_profile_id,
            test_definition_id, test_version_id, telemetry_type_id,
            sample_ordinal, observed_at,
            value_number, value_text, value_boolean, value_json,
            unit_snapshot, context_json
         )
         SELECT ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
         WHERE NOT EXISTS (
            SELECT 1
            FROM LMTS_telemetry_values
            WHERE report_id = ?
              AND record_id = ?
              AND telemetry_type_id = ?
              AND sample_ordinal = ?
              AND context_json = ?
         )'
    );
    $stmt->execute([
        $reportId,
        $recordId,
        $userId,
        $systemId,
        $computeProfileId,
        $test['test_definition_id'],
        $test['test_version_id'],
        $telemetryTypeId,
        $sampleOrdinal,
        lmts_projection_mysql_datetime($observedAt),
        $valueNumber,
        $valueText,
        $valueBoolean,
        $valueJson,
        $unit,
        $contextJson,
        $reportId,
        $recordId,
        $telemetryTypeId,
        $sampleOrdinal,
        $contextJson,
    ]);
}

function lmts_projection_record_telemetry(PDO $pdo, string $reportId, array $record, array $test): void {
    $provenance = isset($record['provenance']) && is_array($record['provenance']) ? $record['provenance'] : [];
    $userId = trim((string)($provenance['tester_user_id'] ?? ''));
    $systemId = trim((string)($provenance['system_id'] ?? ''));
    $computeProfileId = trim((string)($provenance['compute_profile_id'] ?? '')) ?: null;
    if ($userId === '' || $systemId === '') return;

    $recordId = trim((string)($record['id'] ?? ''));
    if ($recordId === '') return;

    $evidence = isset($record['evidence']) && is_array($record['evidence']) ? $record['evidence'] : [];
    $responses = isset($evidence['responses']) && is_array($evidence['responses']) ? $evidence['responses'] : [];
    foreach ($responses as $index => $response) {
        if (!is_array($response)) continue;
        $usage = isset($response['usage']) && is_array($response['usage']) ? $response['usage'] : [];
        $timing = isset($response['timing']) && is_array($response['timing']) ? $response['timing'] : [];
        foreach ([
            'input_tokens' => $usage['input_tokens'] ?? null,
            'output_tokens' => $usage['output_tokens'] ?? null,
            'ttft' => $timing['ttft_ms'] ?? null,
            'total_time' => $timing['total_ms'] ?? null,
        ] as $type => $value) {
            lmts_projection_insert_telemetry(
                $pdo, $reportId, $recordId, $userId, $systemId, $computeProfileId,
                $test, $type, (int)$index, $value, null,
                lmts_projection_context_json('response', ['response_index' => (int)$index]),
            );
        }
    }

    foreach (['score_percent', 'workspace_protocol_steps', 'output_file_count', 'exact_output_match'] as $type) {
        lmts_projection_insert_telemetry(
            $pdo, $reportId, $recordId, $userId, $systemId, $computeProfileId,
            $test, $type, 0, lmts_projection_metric_value($record, $type), null,
            lmts_projection_context_json('record_metric'),
        );
    }

    $telemetry = isset($evidence['telemetry']) && is_array($evidence['telemetry']) ? $evidence['telemetry'] : [];
    $samples = isset($telemetry['samples']) && is_array($telemetry['samples']) ? $telemetry['samples'] : [];
    foreach ($samples as $sampleIndex => $sample) {
        if (!is_array($sample)) continue;
        $observedAt = isset($sample['measured_at']) && is_string($sample['measured_at'])
            ? (trim($sample['measured_at']) ?: null)
            : null;
        $memory = isset($sample['memory']) && is_array($sample['memory']) ? $sample['memory'] : [];

        foreach ([
            'cpu_util_percent' => $sample['cpu_util_percent'] ?? null,
            'memory_used_bytes' => $memory['used_bytes'] ?? null,
        ] as $type => $value) {
            lmts_projection_insert_telemetry(
                $pdo, $reportId, $recordId, $userId, $systemId, $computeProfileId,
                $test, $type, (int)$sampleIndex, $value, $observedAt,
                lmts_projection_context_json('tester_system'),
            );
        }

        $gpus = isset($sample['gpus']) && is_array($sample['gpus']) ? $sample['gpus'] : [];
        foreach ($gpus as $gpuIndex => $gpu) {
            if (!is_array($gpu)) continue;
            $gpuContext = lmts_projection_context_json('tester_system_gpu', [
                'gpu_index' => $gpu['index'] ?? $gpuIndex,
                'gpu_uuid' => $gpu['uuid'] ?? null,
                'gpu_name' => $gpu['name'] ?? null,
            ]);
            foreach ([
                'gpu_util_percent' => $gpu['gpu_util_percent'] ?? null,
                'gpu_memory_util_percent' => $gpu['memory_util_percent'] ?? null,
                'gpu_memory_used_mib' => $gpu['memory_used_mib'] ?? null,
                'gpu_temperature_c' => $gpu['temperature_c'] ?? null,
                'gpu_power_w' => $gpu['power_w'] ?? null,
            ] as $type => $value) {
                lmts_projection_insert_telemetry(
                    $pdo, $reportId, $recordId, $userId, $systemId, $computeProfileId,
                    $test, $type, (int)$sampleIndex, $value, $observedAt, $gpuContext,
                );
            }
        }
    }
}

function lmts_project_report(PDO $pdo, array $report): void {
    $reportMeta = isset($report['report']) && is_array($report['report']) ? $report['report'] : [];
    $reportId = trim((string)($reportMeta['id'] ?? ''));
    $records = $report['records'] ?? [];
    $entities = isset($report['entities']) && is_array($report['entities']) ? $report['entities'] : [];
    $testEntities = isset($entities['test']) && is_array($entities['test']) ? $entities['test'] : [];

    if ($reportId === '' || !is_array($records)) {
        throw new InvalidArgumentException('report projection requires report.id and records array');
    }

    $tests = [];
    foreach ($testEntities as $testRef => $entity) {
        if (!is_string($testRef) || !is_array($entity)) continue;
        $tests[$testRef] = lmts_projection_test_spec($testRef, $entity);
    }
    foreach ($tests as $test) {
        lmts_projection_ensure_test($pdo, $test);
    }

    $targets = isset($entities['target']) && is_array($entities['target']) ? $entities['target'] : [];
    $insertRecord = $pdo->prepare(
        'INSERT INTO LMTS_report_record_index (
            report_id, record_id, tester_user_id, target_kind, target_ref, target_label,
            test_version_id, system_id, compute_profile_id,
            started_at, completed_at, duration_ms, ttft_ms,
            outcome, passed, score_percent, runtime_configuration_json
         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON DUPLICATE KEY UPDATE
            target_kind = VALUES(target_kind),
            target_ref = VALUES(target_ref),
            target_label = VALUES(target_label),
            test_version_id = VALUES(test_version_id),
            system_id = VALUES(system_id),
            compute_profile_id = VALUES(compute_profile_id),
            started_at = VALUES(started_at),
            completed_at = VALUES(completed_at),
            duration_ms = VALUES(duration_ms),
            ttft_ms = VALUES(ttft_ms),
            outcome = VALUES(outcome),
            passed = VALUES(passed),
            score_percent = VALUES(score_percent),
            runtime_configuration_json = VALUES(runtime_configuration_json)'
    );

    foreach ($records as $record) {
        if (!is_array($record)) continue;
        $recordId = trim((string)($record['id'] ?? ''));
        if ($recordId === '') continue;

        $coordinates = isset($record['coordinates']) && is_array($record['coordinates']) ? $record['coordinates'] : [];
        $testRef = trim((string)($coordinates['test'] ?? ''));
        $test = $tests[$testRef] ?? null;

        $provenance = isset($record['provenance']) && is_array($record['provenance']) ? $record['provenance'] : [];
        $tester = trim((string)($provenance['tester_user_id'] ?? '')) ?: null;
        $systemId = trim((string)($provenance['system_id'] ?? '')) ?: null;
        $computeProfileId = trim((string)($provenance['compute_profile_id'] ?? '')) ?: null;

        lmts_projection_ensure_system($pdo, $record);
        lmts_projection_assert_compute_profile($pdo, $record);

        $timing = isset($record['timing']) && is_array($record['timing']) ? $record['timing'] : [];
        $outcome = isset($record['outcome']) && is_array($record['outcome']) ? $record['outcome'] : [];
        $targetId = trim((string)($coordinates['target'] ?? ''));
        $targetEntity = isset($targets[$targetId]) && is_array($targets[$targetId]) ? $targets[$targetId] : [];
        $targetProps = isset($targetEntity['properties']) && is_array($targetEntity['properties'])
            ? $targetEntity['properties']
            : [];
        $targetKind = trim((string)($targetProps['kind'] ?? '')) ?: 'unknown';
        $targetRef = $targetId !== '' ? $targetId : null;
        $targetLabel = trim((string)($targetEntity['label'] ?? '')) ?: $targetRef;

        $evidence = isset($record['evidence']) && is_array($record['evidence']) ? $record['evidence'] : [];
        $executionMetadata = isset($evidence['execution_metadata']) && is_array($evidence['execution_metadata'])
            ? $evidence['execution_metadata']
            : [];
        $runtimeConfiguration = $executionMetadata['runtime_configuration'] ?? null;
        $runtimeJson = $runtimeConfiguration === null ? null : lmts_projection_json($runtimeConfiguration);

        $insertRecord->execute([
            $reportId,
            $recordId,
            $tester,
            $targetKind,
            $targetRef,
            $targetLabel,
            $test['test_version_id'] ?? null,
            $systemId,
            $computeProfileId,
            lmts_projection_mysql_datetime($timing['started_at'] ?? null),
            lmts_projection_mysql_datetime($timing['completed_at'] ?? null),
            lmts_projection_duration_ms($timing['started_at'] ?? null, $timing['completed_at'] ?? null),
            lmts_projection_metric_value($record, 'ttft'),
            isset($outcome['result']) ? (string)$outcome['result'] : null,
            array_key_exists('passed', $outcome) && $outcome['passed'] !== null
                ? ($outcome['passed'] ? 1 : 0)
                : null,
            lmts_projection_metric_value($record, 'score_percent'),
            $runtimeJson,
        ]);

        if ($test !== null) {
            lmts_projection_record_telemetry($pdo, $reportId, $record, $test);
        }
    }
}
