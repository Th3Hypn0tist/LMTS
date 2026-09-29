<?php

declare(strict_types=1);

header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');

function lmts_upload_fail(int $status, string $message): never {
    http_response_code($status);
    echo json_encode(
        ['ok' => false, 'error' => $message],
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE,
    );
    exit;
}

function lmts_upload_bearer_token(): ?string {
    $header = trim((string)($_SERVER['HTTP_AUTHORIZATION'] ?? ''));
    if (preg_match('/^Bearer\s+(.+)$/i', $header, $match) !== 1) return null;
    $token = trim($match[1]);
    return $token === '' ? null : $token;
}

function lmts_upload_authenticated_user_id(array $config): string|false|null {
    $bearer = lmts_upload_bearer_token();
    if ($bearer !== null) {
        $pdo = new PDO($config['dsn'], $config['user'], $config['password'], [
            PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
            PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
            PDO::ATTR_EMULATE_PREPARES => false,
        ]);
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
        if ($userId !== false) return (string)$userId;
    }

    $configuredKey = trim((string)($config['publish_key'] ?? ''));
    $suppliedKey = trim((string)($_SERVER['HTTP_X_LMTS_KEY'] ?? ''));
    if (
        $configuredKey !== ''
        && $suppliedKey !== ''
        && hash_equals($configuredKey, $suppliedKey)
    ) {
        return null;
    }
    return false;
}

try {
    $config = require __DIR__ . '/config.php';
    require_once __DIR__ . '/storage/lib/report_contract.php';
    require_once __DIR__ . '/storage/lib/report_projection.php';
    require_once __DIR__ . '/storage/lib/report_store.php';
    require_once __DIR__ . '/storage/lib/report_upload.php';

    $authenticatedUserId = lmts_upload_authenticated_user_id($config);
    if ($authenticatedUserId === false) {
        lmts_upload_fail(403, 'authentication required');
    }

    $action = trim((string)($_GET['action'] ?? ''));

    if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'init') {
        $raw = file_get_contents('php://input');
        if ($raw === false || trim($raw) === '') {
            lmts_upload_fail(400, 'empty init request body');
        }
        $request = json_decode($raw, true, 32, JSON_THROW_ON_ERROR);
        if (!is_array($request)) {
            lmts_upload_fail(400, 'init request must be a JSON object');
        }
        http_response_code(201);
        echo json_encode(
            lmts_upload_init($config, $request),
            JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE,
        );
        exit;
    }

    if ($_SERVER['REQUEST_METHOD'] === 'PUT' && $action === 'chunk') {
        $uploadId = trim((string)($_GET['id'] ?? ''));
        $rawIndex = $_GET['chunk'] ?? null;
        if ($uploadId === '' || $rawIndex === null || filter_var($rawIndex, FILTER_VALIDATE_INT) === false) {
            lmts_upload_fail(400, 'upload id and integer chunk index are required');
        }
        $bytes = file_get_contents('php://input');
        if ($bytes === false) {
            lmts_upload_fail(400, 'cannot read chunk body');
        }
        echo json_encode(
            lmts_upload_put_chunk($config, $uploadId, (int)$rawIndex, $bytes),
            JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE,
        );
        exit;
    }

    if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'abort') {
        $uploadId = trim((string)($_GET['id'] ?? ''));
        if ($uploadId === '') lmts_upload_fail(400, 'upload id is required');
        $dir = lmts_upload_dir($config, $uploadId);
        lmts_upload_delete_tree($dir);
        echo json_encode(['ok' => true, 'upload_id' => $uploadId], JSON_UNESCAPED_SLASHES);
        exit;
    }

    if ($_SERVER['REQUEST_METHOD'] === 'POST' && $action === 'commit') {
        $uploadId = trim((string)($_GET['id'] ?? ''));
        if ($uploadId === '') lmts_upload_fail(400, 'upload id is required');

        $dir = lmts_upload_dir($config, $uploadId);
        try {
            [, $meta, $rawReport] = lmts_upload_assemble($config, $uploadId);

            $document = json_decode($rawReport, false, 512, JSON_THROW_ON_ERROR);
            if (!($document instanceof stdClass)) {
                throw new InvalidArgumentException('benchmark report root must be an object');
            }
            lmts_validate_report_document(
                $document,
                __DIR__ . '/storage/contracts/' . LMTS_REPORT_CONTRACT_FILE,
            );

            $report = json_decode($rawReport, true, 512, JSON_THROW_ON_ERROR);
            if (!is_array($report)) {
                throw new InvalidArgumentException('benchmark report root must be an object');
            }

            $reportId = trim((string)($report['report']['id'] ?? ''));
            if ($reportId === '' || !hash_equals((string)$meta['report_id'], $reportId)) {
                throw new InvalidArgumentException('report_id does not match upload metadata');
            }

            $pdo = new PDO($config['dsn'], $config['user'], $config['password'], [
                PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                PDO::ATTR_EMULATE_PREPARES => false,
            ]);

            $stored = lmts_store_report($pdo, $report);

            $pdo->beginTransaction();
            try {
                lmts_project_report($pdo, $report);
                $pdo->commit();
            } catch (Throwable $projectionError) {
                if ($pdo->inTransaction()) $pdo->rollBack();
                throw $projectionError;
            }

            $submissionId = 'sub_' . substr(hash('sha256', $uploadId), 0, 40);
            $submission = $pdo->prepare(
                'INSERT INTO LMTS_report_submissions (
                    submission_id, report_id, submitter_user_id, source, verification_status
                 ) VALUES (?, ?, ?, ?, ?)
                 ON DUPLICATE KEY UPDATE
                    submitter_user_id = VALUES(submitter_user_id),
                    source = VALUES(source),
                    verification_status = VALUES(verification_status)'
            );
            $submission->execute([
                $submissionId,
                $reportId,
                $authenticatedUserId,
                'php_api',
                $authenticatedUserId === null ? 'shared_key' : 'authenticated',
            ]);

            http_response_code($stored['created'] ? 201 : 200);
            echo json_encode([
                'ok' => true,
                'id' => $stored['id'],
                'version' => $stored['version'],
                'created' => $stored['created'],
                'projected' => true,
            ], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
        } finally {
            if (is_string($dir) && $dir !== '') {
                lmts_upload_delete_tree($dir);
            }
        }
        exit;
    }

    header('Allow: POST, PUT');
    lmts_upload_fail(405, 'unsupported upload operation');
} catch (LMTSReportConflict $error) {
    lmts_upload_fail(409, $error->getMessage());
} catch (InvalidArgumentException | JsonException | DateException $error) {
    lmts_upload_fail(400, $error->getMessage());
} catch (Throwable $error) {
    $errorId = substr(
        hash('sha256', microtime(true) . '|' . getmypid() . '|' . $error->getMessage()),
        0,
        12,
    );
    error_log(
        '[LMTS upload ' . $errorId . '] '
        . get_class($error) . ': '
        . $error->getMessage()
    );
    lmts_upload_fail(500, 'server error [' . $errorId . ']');
}
