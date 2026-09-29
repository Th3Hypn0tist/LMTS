<?php

declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

function lmts_revoke_fail(int $status, string $message): never {
    http_response_code($status);
    echo json_encode(['ok' => false, 'error' => $message], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
    exit;
}

try {
    if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
        header('Allow: POST');
        lmts_revoke_fail(405, 'POST required');
    }

    $config = require __DIR__ . '/config.php';
    require_once __DIR__ . '/storage/lib/publish_auth.php';

    $iam = lmts_auth_require_iam_user($config);
    if ($iam['ok'] !== true) {
        lmts_revoke_fail((int)$iam['status'], (string)$iam['error']);
    }
    /** @var PDO $pdo */
    $pdo = $iam['pdo'];
    $userId = (string)$iam['user_id'];

    $raw = file_get_contents('php://input');
    if ($raw === false || trim($raw) === '') lmts_revoke_fail(400, 'empty request body');
    $request = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
    if (!is_array($request)) lmts_revoke_fail(400, 'request must be a JSON object');

    $systemId = trim((string)($request['system_id'] ?? ''));
    if ($systemId === '') lmts_revoke_fail(400, 'system_id is required');

    $owned = $pdo->prepare(
        'SELECT 1 FROM LMTS_systems WHERE system_id = ? AND user_id = ? LIMIT 1'
    );
    $owned->execute([$systemId, $userId]);
    if ($owned->fetchColumn() === false) {
        lmts_revoke_fail(404, 'system not found');
    }

    $stmt = $pdo->prepare(
        'UPDATE LMTS_publish_keys
         SET revoked_at = CURRENT_TIMESTAMP(6)
         WHERE user_id = ? AND system_id = ? AND revoked_at IS NULL'
    );
    $stmt->execute([$userId, $systemId]);

    echo json_encode([
        'ok' => true,
        'system_id' => $systemId,
        'revoked' => $stmt->rowCount(),
    ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
} catch (JsonException $error) {
    lmts_revoke_fail(400, $error->getMessage());
} catch (Throwable $error) {
    $errorId = substr(hash('sha256', microtime(true) . '|' . getmypid() . '|' . $error->getMessage()), 0, 12);
    error_log('[LMTS revoke ' . $errorId . '] ' . get_class($error) . ': ' . $error->getMessage());
    lmts_revoke_fail(500, 'server error [' . $errorId . ']');
}
