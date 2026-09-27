<?php

declare(strict_types=1);

final class LMTSReportConflict extends RuntimeException {}

function lmts_store_canonicalize(mixed $value): mixed {
    if (!is_array($value)) return $value;
    if (array_is_list($value)) {
        return array_map('lmts_store_canonicalize', $value);
    }
    ksort($value, SORT_STRING);
    foreach ($value as $key => $item) {
        $value[$key] = lmts_store_canonicalize($item);
    }
    return $value;
}

function lmts_store_report(PDO $pdo, array $report): array {
    $meta = $report['report'] ?? null;
    $source = $report['source'] ?? null;
    if (!is_array($meta) || !is_array($source)) {
        throw new InvalidArgumentException('report metadata is missing');
    }

    $reportId = trim((string)($meta['id'] ?? ''));
    $reportType = trim((string)($meta['type'] ?? ''));
    $createdAtRaw = trim((string)($meta['created_at'] ?? ''));
    $sourceType = trim((string)($source['type'] ?? ''));
    $sourceId = trim((string)($source['id'] ?? ''));
    $version = trim((string)($report['version'] ?? ''));

    if ($reportId === '' || $reportType === '' || $createdAtRaw === '' || $sourceType === '' || $sourceId === '') {
        throw new InvalidArgumentException('report metadata is incomplete');
    }

    $createdAt = new DateTimeImmutable($createdAtRaw);
    $createdAtSql = $createdAt
        ->setTimezone(new DateTimeZone('UTC'))
        ->format('Y-m-d H:i:s.u');

    $canonical = lmts_store_canonicalize($report);
    $reportJson = json_encode(
        $canonical,
        JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR,
    );

    $pdo->beginTransaction();
    try {
        $existingStmt = $pdo->prepare(
            'SELECT report_json
             FROM LMTS_reports
             WHERE report_id = ?
             FOR UPDATE'
        );
        $existingStmt->execute([$reportId]);
        $existingJson = $existingStmt->fetchColumn();

        $created = false;
        if ($existingJson !== false) {
            $existingReport = json_decode(
                (string)$existingJson,
                true,
                512,
                JSON_THROW_ON_ERROR,
            );
            $existingCanonical = json_encode(
                lmts_store_canonicalize($existingReport),
                JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR,
            );
            if (!hash_equals(hash('sha256', $existingCanonical), hash('sha256', $reportJson))) {
                throw new LMTSReportConflict('report id already exists with different content');
            }
        } else {
            $insert = $pdo->prepare(
                'INSERT INTO LMTS_reports (
                    report_id, report_type, created_at,
                    source_type, source_id, report_json
                 ) VALUES (?, ?, ?, ?, ?, ?)'
            );
            $insert->execute([
                $reportId,
                $reportType,
                $createdAtSql,
                $sourceType,
                $sourceId,
                $reportJson,
            ]);
            $created = true;
        }

        $pdo->commit();
        return [
            'id' => $reportId,
            'version' => $version,
            'created' => $created,
        ];
    } catch (Throwable $error) {
        if ($pdo->inTransaction()) $pdo->rollBack();
        throw $error;
    }
}
