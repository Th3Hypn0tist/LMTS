<?php

declare(strict_types=1);

function lmts_auth_pdo(array $config): PDO {
    return new PDO($config['dsn'], $config['user'], $config['password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
}

function lmts_auth_header(): string {
    foreach ([
        'HTTP_X_LMTS_AUTHORIZATION',
        'HTTP_AUTHORIZATION',
        'REDIRECT_HTTP_AUTHORIZATION',
    ] as $key) {
        $value = trim((string)($_SERVER[$key] ?? ''));
        if ($value !== '') return $value;
    }
    if (function_exists('getallheaders')) {
        $headers = getallheaders();
        if (is_array($headers)) {
            foreach ($headers as $name => $value) {
                if (
                    strcasecmp((string)$name, 'X-LMTS-Authorization') === 0
                    || strcasecmp((string)$name, 'Authorization') === 0
                ) {
                    $resolved = trim((string)$value);
                    if ($resolved !== '') return $resolved;
                }
            }
        }
    }
    return '';
}

function lmts_auth_log(string $reason, array $context = []): void {
    $safe = [];
    foreach ($context as $key => $value) {
        if ($value === null || is_scalar($value)) {
            $safe[(string)$key] = $value;
        }
    }
    error_log(
        '[LMTS auth] ' . $reason
        . ($safe === [] ? '' : ' ' . json_encode(
            $safe,
            JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE
        ))
    );
}

function lmts_auth_reject(string $reason, array $context = []): false {
    $GLOBALS['LMTS_AUTH_FAILURE_REASON'] = $reason;
    lmts_auth_log($reason, $context);
    return false;
}

function lmts_auth_failure_reason(): string {
    $reason = $GLOBALS['LMTS_AUTH_FAILURE_REASON'] ?? '';
    return is_string($reason) ? $reason : '';
}

function lmts_auth_bearer_token(): ?string {
    $header = lmts_auth_header();
    if (preg_match('/^Bearer\s+(.+)$/i', $header, $match) !== 1) return null;
    $token = trim($match[1]);
    return $token === '' ? null : $token;
}

function lmts_auth_iam_user(PDO $pdo, string $bearer): ?string {
    $stmt = $pdo->prepare(
        "SELECT s.user_id
         FROM IAM_sessions s
         JOIN IAM_users u ON u.user_id = s.user_id
         JOIN IAM_user_accounts a ON a.user_id = s.user_id
         JOIN IAM_domain_memberships m
           ON m.user_id = s.user_id
          AND m.domain_id = 'lmts'
          AND m.status = 'active'
         WHERE s.token_hash = ?
           AND s.revoked_at IS NULL
           AND s.expires_at > CURRENT_TIMESTAMP(6)
           AND u.status = 'active'
           AND a.account_status = 'active'
         LIMIT 1"
    );
    $stmt->execute([hash('sha256', $bearer)]);
    $userId = $stmt->fetchColumn();
    return $userId === false ? null : (string)$userId;
}

function lmts_auth_require_iam_user(array $config): array {
    $bearer = lmts_auth_bearer_token();
    if ($bearer === null) {
        return ['ok' => false, 'status' => 401, 'error' => 'IAM bearer authentication required'];
    }
    $pdo = lmts_auth_pdo($config);
    $userId = lmts_auth_iam_user($pdo, $bearer);
    if ($userId === null) {
        return ['ok' => false, 'status' => 403, 'error' => 'invalid or expired IAM session'];
    }
    return ['ok' => true, 'pdo' => $pdo, 'user_id' => $userId];
}

function lmts_auth_machine_credential(PDO $pdo): ?array {
    $header = lmts_auth_header();
    if (preg_match('/^LMTS-Key\s+([A-Za-z0-9_-]+)\.([A-Fa-f0-9]{64})$/', $header, $match) !== 1) {
        return null;
    }
    $keyId = $match[1];
    $secret = strtolower($match[2]);

    $stmt = $pdo->prepare(
        "SELECT k.key_id, k.user_id, k.system_id, k.key_hash
         FROM LMTS_publish_keys k
         JOIN IAM_users u ON u.user_id = k.user_id
         JOIN IAM_user_accounts a ON a.user_id = k.user_id
         JOIN IAM_domain_memberships m
           ON m.user_id = k.user_id
          AND m.domain_id = 'lmts'
          AND m.status = 'active'
         JOIN LMTS_systems s
           ON s.system_id = k.system_id
          AND s.user_id = k.user_id
         WHERE k.key_id = ?
           AND k.revoked_at IS NULL
           AND u.status = 'active'
           AND a.account_status = 'active'
         LIMIT 1"
    );
    $stmt->execute([$keyId]);
    $row = $stmt->fetch();
    if (!is_array($row)) {
        lmts_auth_log('machine_key_not_found_or_inactive', ['key_id' => $keyId]);
        return null;
    }
    if (!hash_equals((string)$row['key_hash'], hash('sha256', $secret))) {
        lmts_auth_log('machine_key_secret_mismatch', ['key_id' => $keyId]);
        return null;
    }

    $touch = $pdo->prepare(
        'UPDATE LMTS_publish_keys SET last_used_at = CURRENT_TIMESTAMP(6) WHERE key_id = ?'
    );
    $touch->execute([$keyId]);

    return [
        'mode' => 'machine_key',
        'user_id' => (string)$row['user_id'],
        'system_id' => (string)$row['system_id'],
        'key_id' => (string)$row['key_id'],
    ];
}

function lmts_auth_upload(array $config): array|false {
    $pdo = lmts_auth_pdo($config);
    $header = lmts_auth_header();

    if (preg_match('/^LMTS-Key\\s+/i', $header) !== 1) {
        return lmts_auth_reject(
            $header === '' ? 'machine_key_required' : 'unsupported_authorization_scheme',
            $header === '' ? [] : ['scheme' => strtok($header, " \t") ?: 'unknown'],
        );
    }

    $machine = lmts_auth_machine_credential($pdo);
    if ($machine === null) {
        return lmts_auth_reject('machine_key_rejected');
    }
    return $machine;
}

function lmts_auth_binding(array $auth): array {
    return [
        'mode' => (string)$auth['mode'],
        'user_id' => $auth['user_id'] ?? null,
        'system_id' => $auth['system_id'] ?? null,
        'key_id' => $auth['key_id'] ?? null,
    ];
}

function lmts_auth_binding_matches(array $expected, array $actual): bool {
    return hash_equals(
        json_encode(lmts_auth_binding($expected), JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR),
        json_encode(lmts_auth_binding($actual), JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR),
    );
}

function lmts_report_provenance(array $report): array {
    $records = $report['records'] ?? null;
    if (!is_array($records) || $records === []) {
        throw new InvalidArgumentException('report contains no records');
    }

    $userId = null;
    $systemId = null;
    foreach ($records as $record) {
        if (!is_array($record)) continue;
        $provenance = isset($record['provenance']) && is_array($record['provenance'])
            ? $record['provenance']
            : [];
        $recordUser = trim((string)($provenance['tester_user_id'] ?? ''));
        $recordSystem = trim((string)($provenance['system_id'] ?? ''));
        if ($recordUser === '' || $recordSystem === '') {
            throw new InvalidArgumentException('report record is missing tester_user_id or system_id provenance');
        }
        if ($userId === null) {
            $userId = $recordUser;
            $systemId = $recordSystem;
            continue;
        }
        if (!hash_equals($userId, $recordUser) || !hash_equals((string)$systemId, $recordSystem)) {
            throw new InvalidArgumentException('report mixes multiple user or system provenance identities');
        }
    }

    if ($userId === null || $systemId === null) {
        throw new InvalidArgumentException('report contains no usable provenance');
    }
    return ['user_id' => $userId, 'system_id' => $systemId];
}

function lmts_auth_validate_report(array $auth, array $report): array {
    $provenance = lmts_report_provenance($report);

    if ($auth['mode'] === 'machine_key') {
        if (!hash_equals((string)$auth['user_id'], $provenance['user_id'])) {
            throw new InvalidArgumentException('machine key user does not match report provenance');
        }
        if (!hash_equals((string)$auth['system_id'], $provenance['system_id'])) {
            throw new InvalidArgumentException('machine key system does not match report provenance');
        }
    } elseif ($auth['mode'] === 'iam_bearer') {
        if (!hash_equals((string)$auth['user_id'], $provenance['user_id'])) {
            throw new InvalidArgumentException('IAM user does not match report provenance');
        }
    }

    return $provenance;
}
