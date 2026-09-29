<?php

declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

function lmts_provision_fail(int $status, string $message): never {
    http_response_code($status);
    echo json_encode(['ok' => false, 'error' => $message], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

try {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        header('Allow: POST');
        lmts_provision_fail(405, 'POST required');
    }

    $config = require __DIR__ . '/config.php';
    require_once __DIR__ . '/storage/lib/publish_auth.php';
    require_once __DIR__ . '/storage/lib/report_projection.php';

    $iam = lmts_auth_require_iam_user($config);
    if ($iam['ok'] !== true) {
        lmts_provision_fail((int)$iam['status'], (string)$iam['error']);
    }
    /** @var PDO $pdo */
    $pdo = $iam['pdo'];
    $userId = (string)$iam['user_id'];

    $raw = file_get_contents('php://input');
    if ($raw === false || trim($raw) === '') lmts_provision_fail(400, 'empty request body');
    $request = json_decode($raw, true, 64, JSON_THROW_ON_ERROR);
    if (!is_array($request)) lmts_provision_fail(400, 'request must be a JSON object');

    $systemId = trim((string)($request['system_id'] ?? ''));
    $context = $request['system_context'] ?? null;
    if ($systemId === '' || !is_array($context)) {
        lmts_provision_fail(400, 'system_id and system_context are required');
    }

    $pdo->beginTransaction();
    try {
        // This validates deterministic system identity and ownership. It also
        // bootstraps a never-before-published machine, avoiding a first-publish
        // authentication deadlock.
        lmts_projection_ensure_system_identity($pdo, $userId, $systemId, $context);
        $profile = $context['profile'] ?? null;
        if (!is_array($profile)) {
            throw new InvalidArgumentException('system_context.profile is required');
        }
        lmts_projection_project_system_profile($pdo, $systemId, $profile);

        $lock = $pdo->prepare(
            'SELECT system_id FROM LMTS_systems WHERE system_id = ? AND user_id = ? FOR UPDATE'
        );
        $lock->execute([$systemId, $userId]);
        if ($lock->fetchColumn() === false) {
            throw new RuntimeException('system ownership validation failed');
        }

        // Exactly one current credential per user + system. Reprovisioning is
        // rotation: previous credentials for only this machine are revoked.
        $revoke = $pdo->prepare(
            'UPDATE LMTS_publish_keys
             SET revoked_at = CURRENT_TIMESTAMP(6)
             WHERE user_id = ? AND system_id = ? AND revoked_at IS NULL'
        );
        $revoke->execute([$userId, $systemId]);

        $keyId = 'pk_' . bin2hex(random_bytes(20));
        $secret = bin2hex(random_bytes(32));
        $insert = $pdo->prepare(
            'INSERT INTO LMTS_publish_keys (key_id, user_id, system_id, key_hash)
             VALUES (?, ?, ?, ?)'
        );
        $insert->execute([$keyId, $userId, $systemId, hash('sha256', $secret)]);
        $pdo->commit();

        http_response_code(201);
        echo json_encode([
            'ok' => true,
            'key_id' => $keyId,
            'secret' => $secret,
            'system_id' => $systemId,
        ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    } catch (Throwable $error) {
        if ($pdo->inTransaction()) $pdo->rollBack();
        throw $error;
    }
} catch (InvalidArgumentException | JsonException | DateException $error) {
    lmts_provision_fail(400, $error->getMessage());
} catch (Throwable $error) {
    $errorId = substr(hash('sha256', microtime(true) . '|' . getmypid() . '|' . $error->getMessage()), 0, 12);
    error_log('[LMTS provision ' . $errorId . '] ' . get_class($error) . ': ' . $error->getMessage());
    lmts_provision_fail(500, 'server error [' . $errorId . ']');
}
