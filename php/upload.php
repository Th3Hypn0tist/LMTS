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

try {
    $config = require __DIR__ . '/config.php';
    require_once __DIR__ . '/storage/lib/report_contract.php';
    require_once __DIR__ . '/storage/lib/report_projection.php';
    require_once __DIR__ . '/storage/lib/report_store.php';
    require_once __DIR__ . '/storage/lib/report_upload.php';

    if (!hash_equals(
        (string)$config['publish_key'],
        (string)($_SERVER['HTTP_X_LMTS_KEY'] ?? ''),
    )) {
        lmts_upload_fail(403, 'invalid publish key');
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

        $dir = null;
        try {
            [$dir, $meta, $rawReport] = lmts_upload_assemble($config, $uploadId);

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
